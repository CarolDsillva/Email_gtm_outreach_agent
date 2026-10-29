"""Fictional sample run so the UI can be explored without API keys.
All companies, people and addresses below are invented (.example domains)."""

from .schemas import (CompanyResult, ContactOut, EmailResult, Insight,
                      ResearchOut, RunResult)


def _email(name, title, to, status, subject, body):
    return EmailResult(contact_name=name, contact_title=title, to=to,
                       email_status=status, subject=subject, body=body,
                       word_count=len(body.split()))


DEMO_RUN = RunResult(
    target="B2B SaaS companies in India, 50-500 employees, serving manufacturers",
    offering="AI automation for RFQ processing and quote generation that cuts "
             "manual processing time for procurement teams.",
    style="Consultative", model="demo", generated_at="2026-10-29T12:00:00+00:00",
    companies=[
        CompanyResult(
            name="Forgeline Systems", website="https://forgeline.example",
            why_fit="Sells MES software to mid-size Indian manufacturers whose "
                    "sales teams still build quotes by hand.",
            fit_score=9, email_format="first.last@forgeline.example",
            research=ResearchOut(
                summary="Manufacturing execution software for discrete manufacturers.",
                insights=[
                    Insight(insight="Launched a supplier portal in September aimed at auto-component makers.",
                            source_url="https://forgeline.example/blog/supplier-portal"),
                    Insight(insight="Hiring three pre-sales engineers in Pune, citing growing RFQ volume.",
                            source_url="https://forgeline.example/careers"),
                    Insight(insight="Users on r/manufacturing mention slow quote turnaround from partners.",
                            source_url="https://reddit.com/r/manufacturing/comments/demo1"),
                ],
                likely_pain_points=["Quote turnaround time", "Pre-sales bandwidth"]),
            contacts=[
                ContactOut(full_name="Meera Iyer", title="VP Sales",
                           email="meera.iyer@forgeline.example", email_status="found",
                           source_url="https://forgeline.example/team"),
                ContactOut(full_name="Arjun Menon", title="Head of Partnerships",
                           email="arjun.menon@forgeline.example", email_status="pattern",
                           source_url="https://forgeline.example/team"),
            ],
            emails=[
                _email("Meera Iyer", "VP Sales", "meera.iyer@forgeline.example", "found",
                       "Your new supplier portal + faster RFQs",
                       "Hi Meera,\n\nI saw Forgeline is hiring pre-sales engineers in Pune "
                       "because RFQ volume is growing — that usually means quotes are "
                       "queuing up behind a few experts.\n\nWe automate RFQ intake and "
                       "first-draft quote generation, so your engineers review rather than "
                       "build from scratch. It could pair well with the supplier portal you "
                       "launched in September.\n\nWould a 20-minute call next week be "
                       "useful? Here's my calendar: https://cal.example/carol\n\nCarol"),
                _email("Arjun Menon", "Head of Partnerships", "arjun.menon@forgeline.example",
                       "pattern", "A partnership idea for your supplier portal",
                       "Hi Arjun,\n\nForgeline's new supplier portal puts you right where "
                       "RFQs start. Partners on Reddit mention slow quote turnaround, and "
                       "that's the gap we close: AI that reads RFQs and drafts quotes in "
                       "minutes.\n\nAn integration could give your customers faster quotes "
                       "without adding headcount. Open to exploring it on a short call?"
                       "\n\nhttps://cal.example/carol\n\nCarol"),
            ]),
        CompanyResult(
            name="Tarang Procure", website="https://tarangprocure.example",
            why_fit="Procurement SaaS for SMB factories; RFQ handling is core to their product.",
            fit_score=8, email_format=None,
            research=ResearchOut(
                summary="Source-to-pay platform for small and mid-size factories.",
                insights=[
                    Insight(insight="Announced a Series A in August to expand into Tamil Nadu.",
                            source_url="https://news.example/tarang-series-a"),
                    Insight(insight="Their blog says buyers spend 6+ hours a week comparing supplier quotes.",
                            source_url="https://tarangprocure.example/blog/quote-comparison"),
                ],
                likely_pain_points=["Manual quote comparison", "Scaling onboarding"]),
            contacts=[
                ContactOut(full_name="Kavya Reddy", title="Co-founder & CEO", email=None,
                           email_status="unknown", source_url="https://news.example/tarang-series-a"),
            ],
            emails=[
                _email("Kavya Reddy", "Co-founder & CEO", None, "unknown",
                       "Those 6 hours a week on quote comparison",
                       "Hi Kavya,\n\nCongratulations on the Series A. Your post on buyers "
                       "spending 6+ hours a week comparing supplier quotes stuck with me — "
                       "that's exactly the work we automate.\n\nOur models read incoming "
                       "RFQs and quotes and line them up side by side, so your customers "
                       "decide in minutes. Embedding that could be a strong hook as you "
                       "expand into Tamil Nadu.\n\nWorth a quick call?\n\nCarol"),
            ]),
    ],
)
