"""Offline tests: fake search + fake LLM, no API keys or network."""

import csv
import io
import json

from gtm_agent import Settings, run_pipeline
from gtm_agent.clients import Doc
from gtm_agent.export import to_csv, to_json
from gtm_agent.pipeline import domain_of, lint_email
from gtm_agent.schemas import (CompanyPick, CompanyShortlist, ContactOut,
                               ContactsOut, EmailDraft, Insight, ResearchOut)


class FakeSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, *, num_results=5, category=None,
               include_domains=None, max_chars=1500):
        self.calls.append((query, category, include_domains))
        if category == "company":
            return [Doc("https://www.alpha.example/", "Alpha", "Alpha makes ERP."),
                    Doc("https://beta.example", "Beta", "Beta does logistics."),
                    Doc("https://beta.example/", "Beta dup", "duplicate")]
        if category == "people":
            dom = "alpha.example" if "Alpha" in query else "beta.example"
            return [Doc(f"https://people.example/{dom}", "Team",
                        f"Asha Rao, VP Sales. Contact: asha@{dom}")]
        if include_domains == ["reddit.com"]:
            return [Doc("https://reddit.com/r/x/1", "thread", "Users say onboarding is slow")]
        dom = (include_domains or ["news.example"])[0]
        return [Doc(f"https://{dom}/blog/launch", "Launch", "We launched v2 last month.")]


class FakeLLM:
    model = "fake-model"

    def structured(self, system, user, schema):
        if schema is CompanyShortlist:
            return CompanyShortlist(companies=[
                CompanyPick(name="Beta", website="https://beta.example",
                            why_fit="Logistics pain", fit_score=7),
                CompanyPick(name="Alpha", website="https://alpha.example",
                            why_fit="ERP users", fit_score=12),          # clamp to 10
                CompanyPick(name="Ghost", website="https://ghost.example",
                            why_fit="invented", fit_score=9),            # not retrieved
            ])
        if schema is ResearchOut:
            dom = "alpha.example" if "Alpha" in user else "beta.example"
            return ResearchOut(summary="Does things", likely_pain_points=["manual work"],
                               insights=[
                                   Insight(insight="Launched v2", source_url=f"https://{dom}/blog/launch/"),
                                   Insight(insight="Made up", source_url="https://nowhere.example"),
                               ])
        if schema is ContactsOut:
            dom = "alpha.example" if "Alpha" in user else "beta.example"
            return ContactsOut(email_format=f"first@{dom}", contacts=[
                ContactOut(full_name="Asha Rao", title="VP Sales",
                           email=f"ASHA@{dom}", email_status="found", source_url=None),
                ContactOut(full_name="asha rao", title="dup", email=None,
                           email_status="found", source_url=None),
                ContactOut(full_name="Ravi K", title="CEO", email=f"ravi@{dom}",
                           email_status="found", source_url=None),   # not in sources
            ])
        if schema is EmailDraft:
            return EmailDraft(subject="Quick idea", body="Hi Asha, saw your v2 launch. " * 3)
        raise AssertionError(schema)


def run(**kw):
    return run_pipeline(FakeSearch(), FakeLLM(), "SaaS in India", "RFQ automation",
                        Settings(num_companies=5, contacts_per_company=3, **kw))


def test_companies_grounded_deduped_sorted_and_clamped():
    result = run()
    assert [c.name for c in result.companies] == ["Alpha", "Beta"]  # Ghost dropped
    assert result.companies[0].fit_score == 10


def test_insights_must_cite_retrieved_sources():
    for company in run().companies:
        assert [i.insight for i in company.research.insights] == ["Launched v2"]


def test_contact_email_verification_and_dedupe():
    alpha = run().companies[0]
    statuses = {c.full_name: (c.email, c.email_status) for c in alpha.contacts}
    assert statuses == {
        "Asha Rao": ("asha@alpha.example", "found"),      # verbatim in source
        "Ravi K": ("ravi@alpha.example", "pattern"),      # downgraded
    }


def test_emails_written_per_contact_with_metadata():
    result = run()
    assert len(result.emails) == 4
    _, email = result.emails[0]
    assert email.subject == "Quick idea" and email.word_count > 0
    assert result.model == "fake-model"


def test_failures_are_isolated_per_company():
    class FlakyLLM(FakeLLM):
        def structured(self, system, user, schema):
            if schema is ResearchOut and "Beta" in user:
                raise RuntimeError("rate limited")
            return super().structured(system, user, schema)

    result = run_pipeline(FakeSearch(), FlakyLLM(), "t", "o", Settings())
    beta = next(c for c in result.companies if c.name == "Beta")
    assert beta.research is None and "rate limited" in beta.errors[0]
    assert beta.emails  # still drafted without research


def test_exports():
    result = run()
    rows = list(csv.DictReader(io.StringIO(to_csv(result))))
    assert len(rows) == 4 and rows[0]["company"] == "Alpha"
    assert json.loads(to_json(result))["companies"][0]["name"] == "Alpha"


def test_helpers():
    assert domain_of("https://www.Acme.com:443/about") == "acme.com"
    assert domain_of("acme.io") == "acme.io"
    assert lint_email("Hi [First Name], " + "word " * 10, 140) == ["contains a placeholder like [Name]"]
    assert lint_email("word " * 200, 140)[0].startswith("200 words")
