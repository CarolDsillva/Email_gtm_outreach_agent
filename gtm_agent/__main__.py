"""Command-line entry point.

    python -m gtm_agent --target "..." --offering "..." -n 3 -o output/run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .clients import ExaSearch, OpenAILLM
from .export import to_csv, to_json
from .pipeline import EMAIL_STYLES, Settings, run_pipeline


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gtm_agent", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, help="who to target")
    p.add_argument("--offering", required=True, help="what you sell, 1-3 sentences")
    p.add_argument("-n", "--num-companies", type=int, default=3)
    p.add_argument("--contacts", type=int, default=2, help="contacts per company")
    p.add_argument("--style", choices=list(EMAIL_STYLES), default="Professional")
    p.add_argument("--max-words", type=int, default=140)
    p.add_argument("--sender-name", default="Sales Team")
    p.add_argument("--sender-company", default="Our Company")
    p.add_argument("--calendar-link")
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5-mini"))
    p.add_argument("-o", "--output", default="output/run",
                   help="output path prefix; writes .json and .csv")
    args = p.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    missing = [k for k in ("OPENAI_API_KEY", "EXA_API_KEY") if not os.getenv(k)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    settings = Settings(num_companies=args.num_companies,
                        contacts_per_company=args.contacts, style=args.style,
                        max_words=args.max_words, sender_name=args.sender_name,
                        sender_company=args.sender_company,
                        calendar_link=args.calendar_link)
    run = run_pipeline(ExaSearch(os.environ["EXA_API_KEY"]),
                       OpenAILLM(os.environ["OPENAI_API_KEY"], args.model),
                       args.target, args.offering, settings,
                       progress=lambda m: print(f"• {m}"))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(to_json(run), encoding="utf-8")
    out.with_suffix(".csv").write_text(to_csv(run), encoding="utf-8")
    print(f"✓ {len(run.emails)} drafts for {len(run.companies)} companies → "
          f"{out.with_suffix('.json')}, {out.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
