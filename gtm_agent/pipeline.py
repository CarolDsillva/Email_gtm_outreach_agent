"""Retrieval-first outreach pipeline.

Every stage searches first and then asks the model to reason only over what was
retrieved. The output is checked against the sources afterwards:

* companies must come from the search results (no invented companies)
* insights must cite a URL that was actually retrieved
* an email is only marked "found" if it appears verbatim in a source;
  otherwise it is downgraded to "pattern" (inferred from the email format)
* drafts are linted for length and leftover placeholders
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional
from urllib.parse import urlparse

from .clients import Doc, LLMClient, SearchClient
from .schemas import (CompanyPick, CompanyResult, CompanyShortlist, ContactOut,
                      ContactsOut, EmailDraft, EmailResult, ResearchOut,
                      RunResult)

ProgressFn = Callable[[str], None]

DEFAULT_ROLES = [
    "Founder", "CEO", "Founder's Office", "Head of Growth", "VP Sales",
    "Head of Partnerships", "Business Development", "Product Marketing",
]

EMAIL_STYLES = {
    "Professional": "Clear, respectful and businesslike. Short paragraphs, no slang.",
    "Casual": "Friendly and human, first-name basis. No slang or emojis.",
    "Cold": "A strong hook in the first two lines, a tight value proposition, "
            "minimal fluff and a direct call to action.",
    "Consultative": "Insight-led: name an observed problem, offer a tailored "
                    "hypothesis for solving it, and close with a soft call to action.",
}


@dataclass
class Settings:
    num_companies: int = 5
    contacts_per_company: int = 2
    style: str = "Professional"
    max_words: int = 140
    sender_name: str = "Sales Team"
    sender_company: str = "Our Company"
    calendar_link: Optional[str] = None
    target_roles: List[str] = field(default_factory=lambda: list(DEFAULT_ROLES))
    max_workers: int = 4


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def domain_of(url: str) -> str:
    """'https://www.Acme.com/about' -> 'acme.com'"""
    if not url:
        return ""
    netloc = urlparse(url if "//" in url else f"//{url}").netloc.lower()
    return netloc.split(":")[0].removeprefix("www.")


def normalise_url(url: str) -> str:
    return url.strip().rstrip("/").lower().replace("://www.", "://")


def dedupe_docs(docs: Iterable[Doc]) -> List[Doc]:
    seen, out = set(), []
    for d in docs:
        key = normalise_url(d.url)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def format_docs(docs: List[Doc]) -> str:
    return "\n\n".join(f"[{i}] {d.title}\nURL: {d.url}\n{d.text}"
                       for i, d in enumerate(docs, 1)) or "(no sources found)"


PLACEHOLDER = re.compile(r"\[[A-Z][^\]]{1,30}\]|\{[a-z_ ]{2,30}\}|<[A-Z][^>]{1,30}>")


def lint_email(body: str, max_words: int) -> List[str]:
    warnings = []
    words = len(body.split())
    if words > max_words * 1.15:
        warnings.append(f"{words} words (target {max_words})")
    if PLACEHOLDER.search(body):
        warnings.append("contains a placeholder like [Name]")
    return warnings


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def find_companies(search: SearchClient, llm: LLMClient, target: str,
                   offering: str, n: int) -> List[CompanyPick]:
    candidates = dedupe_docs(search.search(
        f"{target}. Companies that would benefit from: {offering}",
        num_results=min(max(n * 3, 10), 25), category="company", max_chars=1200))
    if not candidates:
        return []

    shortlist = llm.structured(
        "You are a B2B market researcher. Choose companies ONLY from the "
        "candidate list provided; never invent companies or URLs.",
        f"Target profile: {target}\nOur offering: {offering}\n\n"
        f"Pick the {n} best-fit companies from these candidates and score them.\n\n"
        f"{format_docs(candidates)}",
        CompanyShortlist,
    )

    allowed = {domain_of(d.url) for d in candidates}
    picks, seen = [], set()
    for pick in sorted(shortlist.companies, key=lambda p: -p.fit_score):
        dom = domain_of(pick.website)
        if dom in allowed and dom not in seen:  # grounding check + dedupe
            seen.add(dom)
            pick.fit_score = max(1, min(10, pick.fit_score))
            picks.append(pick)
    return picks[:n]


def research_company(search: SearchClient, llm: LLMClient,
                     company: CompanyPick, offering: str) -> ResearchOut:
    dom = domain_of(company.website)
    docs = dedupe_docs([
        *search.search(f"{company.name} product customers announcements",
                       num_results=4, include_domains=[dom], max_chars=1500),
        *search.search(f'"{company.name}" {dom}', num_results=3,
                       include_domains=["reddit.com"], max_chars=1000),
        *search.search(f"{company.name} {dom}", num_results=3,
                       category="news", max_chars=1000),
    ])

    research = llm.structured(
        "You research companies so a salesperson can write a genuinely "
        "personal email. Use ONLY the sources given and cite each insight's URL.",
        f"Company: {company.name} ({company.website})\nOur offering: {offering}\n\n"
        "Give a one-line summary, 2-4 specific insights (recent launches, "
        "hiring, customer complaints, strategy shifts...) each with its "
        "source_url, and the pain points our offering could address.\n\n"
        f"{format_docs(docs)}",
        ResearchOut,
    )

    retrieved = {normalise_url(d.url) for d in docs}
    research.insights = [i for i in research.insights
                         if normalise_url(i.source_url) in retrieved][:4]
    return research


def find_contacts(search: SearchClient, llm: LLMClient, company: CompanyPick,
                  roles: List[str], k: int) -> ContactsOut:
    dom = domain_of(company.website)
    docs = dedupe_docs([
        *search.search(f"{company.name} {' OR '.join(roles)}", num_results=6,
                       category="people", max_chars=800),
        *search.search(f'"@{dom}" email format {company.name}', num_results=3,
                       max_chars=800),
    ])

    result = llm.structured(
        "You identify decision makers at a company from the sources given. "
        "Only list people who appear in the sources. Set email_status to "
        "'found' only if the exact email appears in a source; if you build it "
        "from the company's email format use 'pattern'; otherwise 'unknown'.",
        f"Company: {company.name} (domain: {dom})\n"
        f"Preferred roles, in priority order: {', '.join(roles)}\n"
        f"Return up to {k} people.\n\n{format_docs(docs)}",
        ContactsOut,
    )

    corpus = " ".join(d.text.lower() for d in docs)
    contacts, seen = [], set()
    for c in result.contacts:
        key = c.full_name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if c.email:
            c.email = c.email.strip().lower()
            if c.email_status == "found" and c.email not in corpus:
                c.email_status = "pattern"  # claimed found, but not in any source
        else:
            c.email_status = "unknown"
        contacts.append(c)
    result.contacts = contacts[:k]
    return result


def write_email(llm: LLMClient, settings: Settings, offering: str,
                company: CompanyPick, research: Optional[ResearchOut],
                contact: ContactOut) -> EmailResult:
    insights = "\n".join(f"- {i.insight}" for i in (research.insights if research else []))
    pains = "\n".join(f"- {p}" for p in (research.likely_pain_points if research else []))
    cta = (f"Suggest a short intro call and include this link: {settings.calendar_link}"
           if settings.calendar_link else "Suggest a short intro call.")

    draft = llm.structured(
        "You write concise, personal B2B outreach emails that people actually "
        f"reply to. Style: {EMAIL_STYLES.get(settings.style, EMAIL_STYLES['Professional'])}",
        f"Write one email from {settings.sender_name} at {settings.sender_company} "
        f"to {contact.full_name} ({contact.title}) at {company.name}.\n\n"
        f"Our offering: {offering}\nWhy they fit: {company.why_fit}\n"
        f"Research insights:\n{insights or '- (none)'}\n"
        f"Likely pain points:\n{pains or '- (none)'}\n\n"
        f"Rules: at most {settings.max_words} words; open with one specific "
        "insight, not flattery; no placeholders like [Name]; no invented facts "
        f"or metrics; sign off as {settings.sender_name}. {cta}",
        EmailDraft,
    )

    return EmailResult(
        contact_name=contact.full_name, contact_title=contact.title,
        to=contact.email, email_status=contact.email_status,
        subject=draft.subject.strip(), body=draft.body.strip(),
        word_count=len(draft.body.split()),
        warnings=lint_email(draft.body, settings.max_words),
    )


def process_company(search: SearchClient, llm: LLMClient, offering: str,
                    settings: Settings, pick: CompanyPick) -> CompanyResult:
    result = CompanyResult(**pick.model_dump())
    try:
        result.research = research_company(search, llm, pick, offering)
    except Exception as exc:
        result.errors.append(f"research: {exc}")
    try:
        contacts = find_contacts(search, llm, pick, settings.target_roles,
                                 settings.contacts_per_company)
        result.contacts, result.email_format = contacts.contacts, contacts.email_format
    except Exception as exc:
        result.errors.append(f"contacts: {exc}")
    for contact in result.contacts:
        try:
            result.emails.append(write_email(llm, settings, offering, pick,
                                             result.research, contact))
        except Exception as exc:
            result.errors.append(f"email to {contact.full_name}: {exc}")
    return result


def run_pipeline(search: SearchClient, llm: LLMClient, target: str,
                 offering: str, settings: Optional[Settings] = None,
                 progress: ProgressFn = lambda msg: None) -> RunResult:
    settings = settings or Settings()
    run = RunResult(target=target, offering=offering, style=settings.style,
                    model=llm.model,
                    generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    progress("Finding companies")
    picks = find_companies(search, llm, target, offering, settings.num_companies)
    progress(f"Shortlisted {len(picks)} companies; researching in parallel")

    by_name = {}
    with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
        futures = {pool.submit(process_company, search, llm, offering, settings, p): p
                   for p in picks}
        for future in as_completed(futures):
            company = future.result()
            by_name[company.name] = company
            progress(f"Done: {company.name} ({len(company.emails)} drafts)")

    run.companies = [by_name[p.name] for p in picks if p.name in by_name]
    return run
