"""Typed data models.

The ``*Out`` / ``*Shortlist`` models are the structured-output schemas the LLM
must fill in (every field is required, as OpenAI strict structured outputs
expects). The ``*Result`` models are what the pipeline returns and exports.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

EmailStatus = Literal["found", "pattern", "unknown"]


# --------------------------------------------------------------------------
# LLM output schemas
# --------------------------------------------------------------------------

class CompanyPick(BaseModel):
    name: str
    website: str = Field(description="Homepage URL, copied from the candidate list")
    why_fit: str = Field(description="One or two sentences on why the offering fits")
    fit_score: int = Field(description="1 (weak) to 10 (excellent) fit")


class CompanyShortlist(BaseModel):
    companies: List[CompanyPick]


class Insight(BaseModel):
    insight: str = Field(description="A specific, non-generic observation")
    source_url: str = Field(description="URL of the source document it came from")


class ResearchOut(BaseModel):
    summary: str = Field(description="What the company does, in one sentence")
    insights: List[Insight]
    likely_pain_points: List[str]


class ContactOut(BaseModel):
    full_name: str
    title: str
    email: Optional[str]
    email_status: EmailStatus = Field(
        description="found = email appears verbatim in a source; "
                    "pattern = built from the company's email format; "
                    "unknown = no email")
    source_url: Optional[str]


class ContactsOut(BaseModel):
    email_format: Optional[str] = Field(
        description="Company email pattern if evident, e.g. first.last@domain.com")
    contacts: List[ContactOut]


class EmailDraft(BaseModel):
    subject: str
    body: str


# --------------------------------------------------------------------------
# Pipeline results
# --------------------------------------------------------------------------

class EmailResult(BaseModel):
    contact_name: str
    contact_title: str
    to: Optional[str]
    email_status: EmailStatus
    subject: str
    body: str
    word_count: int
    warnings: List[str] = []


class CompanyResult(BaseModel):
    name: str
    website: str
    why_fit: str
    fit_score: int
    research: Optional[ResearchOut] = None
    email_format: Optional[str] = None
    contacts: List[ContactOut] = []
    emails: List[EmailResult] = []
    errors: List[str] = []


class RunResult(BaseModel):
    target: str
    offering: str
    style: str
    model: str
    generated_at: str
    companies: List[CompanyResult] = []

    @property
    def emails(self) -> List[tuple[CompanyResult, EmailResult]]:
        return [(c, e) for c in self.companies for e in c.emails]
