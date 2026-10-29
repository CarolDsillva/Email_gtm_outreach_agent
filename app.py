"""Streamlit UI for the GTM outreach agent.

    streamlit run app.py
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from gtm_agent import EMAIL_STYLES, Settings, run_pipeline
from gtm_agent.clients import ExaSearch, OpenAILLM
from gtm_agent.demo import DEMO_RUN
from gtm_agent.export import to_csv, to_json
from gtm_agent.pipeline import DEFAULT_ROLES
from gtm_agent.schemas import RunResult

st.set_page_config(page_title="GTM Outreach Agent", page_icon="📬", layout="wide")

STATUS_BADGE = {"found": "✅ found in source", "pattern": "🟡 inferred from pattern",
                "unknown": "⚪ no email"}

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("🔑 API keys")
    openai_key = st.text_input("OpenAI API key", type="password",
                               value=os.getenv("OPENAI_API_KEY", ""))
    exa_key = st.text_input("Exa API key", type="password",
                            value=os.getenv("EXA_API_KEY", ""))
    model = st.text_input("OpenAI model", value=os.getenv("OPENAI_MODEL", "gpt-5-mini"))

    st.header("⚙️ Settings")
    num_companies = st.slider("Companies", 1, 10, 5)
    contacts_per_company = st.slider("Contacts per company", 1, 3, 2)
    max_words = st.slider("Max words per email", 60, 220, 140, step=10)
    roles = st.multiselect("Roles to target", DEFAULT_ROLES, default=DEFAULT_ROLES[:6])

    st.divider()
    if st.button("Load demo results", width="stretch"):
        st.session_state["run"] = DEMO_RUN.model_copy(deep=True)
        st.session_state["is_demo"] = True
        st.session_state["target"] = DEMO_RUN.target
        st.session_state["offering"] = DEMO_RUN.offering
    st.caption("Explore the UI with fictional sample data — no keys needed.")


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

st.title("📬 GTM Outreach Agent")
st.caption("Find best-fit companies → research them → identify decision makers → "
           "draft personal emails. Every insight is linked to its source, and every "
           "email address is labelled by how it was obtained.")

left, right = st.columns([3, 2])
with left:
    target = st.text_area("Who are you targeting?", height=90, key="target",
                          placeholder="e.g. B2B SaaS companies in India with 50-500 "
                                      "employees selling to manufacturers")
    offering = st.text_area("What are you offering?", height=90, key="offering",
                            placeholder="1-3 sentences on your product and the outcome it delivers")
with right:
    sender_name = st.text_input("Your name", "Sales Team")
    sender_company = st.text_input("Your company", "Our Company")
    calendar_link = st.text_input("Calendar link (optional)")
    style = st.selectbox("Email style", list(EMAIL_STYLES),
                         help="\n\n".join(f"**{k}** – {v}" for k, v in EMAIL_STYLES.items()))

if st.button("🚀 Run outreach", type="primary"):
    if not (openai_key and exa_key):
        st.error("Add both API keys in the sidebar, or click **Load demo results**.")
    elif not (target.strip() and offering.strip()):
        st.error("Describe your target and your offering.")
    else:
        settings = Settings(num_companies=num_companies,
                            contacts_per_company=contacts_per_company, style=style,
                            max_words=max_words, sender_name=sender_name.strip() or "Sales Team",
                            sender_company=sender_company.strip() or "Our Company",
                            calendar_link=calendar_link.strip() or None,
                            target_roles=roles or DEFAULT_ROLES)
        with st.status("Running pipeline…", expanded=True) as status:
            try:
                run = run_pipeline(ExaSearch(exa_key), OpenAILLM(openai_key, model),
                                   target.strip(), offering.strip(), settings,
                                   progress=st.write)
                st.session_state["run"], st.session_state["is_demo"] = run, False
                status.update(label=f"Done — {len(run.emails)} drafts for "
                                    f"{len(run.companies)} companies", state="complete")
            except Exception as exc:
                status.update(label="Pipeline failed", state="error")
                st.exception(exc)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

run: RunResult | None = st.session_state.get("run")
if not run:
    st.info("Results will appear here. No keys yet? Click **Load demo results** in the sidebar.")
    st.stop()

if st.session_state.get("is_demo"):
    st.warning("Showing **demo data** — all companies, people and emails are fictional.")

found = sum(1 for _, e in run.emails if e.email_status == "found")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Companies", len(run.companies))
m2.metric("Contacts", sum(len(c.contacts) for c in run.companies))
m3.metric("Drafts", len(run.emails))
m4.metric("Verified emails", f"{found}/{len(run.emails)}")

tab_emails, tab_companies, tab_contacts, tab_research = st.tabs(
    ["✉️ Emails", "🏢 Companies", "👤 Contacts", "🔎 Research"])

with tab_emails:
    st.caption("Edit drafts inline. Downloads include your edits.")
    for ci, company in enumerate(run.companies):
        for ei, email in enumerate(company.emails):
            label = f"{company.name} → {email.contact_name} ({email.contact_title})"
            with st.expander(label, expanded=(ci == 0 and ei == 0)):
                st.markdown(f"**To:** `{email.to or '—'}` · {STATUS_BADGE[email.email_status]}"
                            f" · {email.word_count} words")
                for w in email.warnings:
                    st.warning(w)
                email.subject = st.text_input("Subject", email.subject, key=f"s{ci}-{ei}")
                email.body = st.text_area("Body", email.body, height=260, key=f"b{ci}-{ei}")
                email.word_count = len(email.body.split())
    if not run.emails:
        st.info("No drafts were generated.")

with tab_companies:
    st.dataframe(
        pd.DataFrame([{"Company": c.name, "Website": c.website, "Fit": c.fit_score,
                       "Why they fit": c.why_fit,
                       "Summary": c.research.summary if c.research else ""}
                      for c in run.companies]),
        hide_index=True, width="stretch",
        column_config={"Website": st.column_config.LinkColumn(),
                       "Fit": st.column_config.ProgressColumn(min_value=0, max_value=10,
                                                              format="%d/10")})

with tab_contacts:
    st.dataframe(
        pd.DataFrame([{"Company": c.name, "Name": p.full_name, "Title": p.title,
                       "Email": p.email or "", "Status": STATUS_BADGE[p.email_status],
                       "Source": p.source_url or ""}
                      for c in run.companies for p in c.contacts]),
        hide_index=True, width="stretch",
        column_config={"Source": st.column_config.LinkColumn()})
    st.caption("✅ appears verbatim in a source · 🟡 built from the company's email "
               "format — verify before sending · ⚪ not found")

with tab_research:
    for company in run.companies:
        st.subheader(company.name)
        if company.research:
            st.write(company.research.summary)
            for ins in company.research.insights:
                st.markdown(f"- {ins.insight} [source]({ins.source_url})")
            if company.research.likely_pain_points:
                st.markdown("**Likely pain points:** " +
                            ", ".join(company.research.likely_pain_points))
        for err in company.errors:
            st.error(err)

st.divider()
d1, d2, _ = st.columns([1, 1, 3])
d1.download_button("⬇️ Emails (CSV)", to_csv(run), "outreach_emails.csv", "text/csv",
                   width="stretch")
d2.download_button("⬇️ Full run (JSON)", to_json(run), "outreach_run.json",
                   "application/json", width="stretch")
st.caption("Drafts are never sent automatically — review them, verify inferred "
           "addresses, and follow applicable email-outreach rules (e.g. CAN-SPAM, GDPR).")
