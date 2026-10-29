"""Export a run as CSV (one row per draft, ready for a mail-merge or CRM
import) or as full JSON."""

from __future__ import annotations

import csv
import io

from .schemas import RunResult

CSV_COLUMNS = ["company", "website", "fit_score", "contact_name", "contact_title",
               "email", "email_status", "subject", "body", "warnings"]


def to_csv(run: RunResult) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for company, email in run.emails:
        writer.writerow({
            "company": company.name, "website": company.website,
            "fit_score": company.fit_score,
            "contact_name": email.contact_name, "contact_title": email.contact_title,
            "email": email.to or "", "email_status": email.email_status,
            "subject": email.subject, "body": email.body,
            "warnings": "; ".join(email.warnings),
        })
    return buffer.getvalue()


def to_json(run: RunResult) -> str:
    return run.model_dump_json(indent=2)
