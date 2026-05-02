"""CLI: `python -m scanner --days 1 --email me@example.com`."""

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import _serialize, run_scan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SEC Form 4 insider cluster scanner")
    p.add_argument("--days", type=int, default=1, help="business days back to scan")
    p.add_argument("--min-insiders", type=int, default=2)
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--min-increase-pct", type=float, default=10.0)
    p.add_argument("--email", help="recipient address; requires SMTP_* env vars")
    p.add_argument("--user-agent", help="EDGAR User-Agent (Name email@example.com)")
    p.add_argument("--out", help="write clusters as JSON to this path")
    p.add_argument("--print-json", action="store_true")
    args = p.parse_args(argv)

    clusters = run_scan(
        days=args.days,
        min_insiders=args.min_insiders,
        window_days=args.window_days,
        min_increase_pct=args.min_increase_pct,
        output_path=args.out,
        email_to=args.email,
        user_agent=args.user_agent,
    )

    if args.print_json:
        json.dump(_serialize(clusters), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if not clusters:
            print("No qualifying clusters found.")
            return 0
        for rank, c in enumerate(clusters[:10], start=1):
            print(
                f"#{rank} {c.ticker:<6} {c.issuer_name[:40]:<40} "
                f"insiders={c.insider_count} value=${c.total_value:,.0f} "
                f"avg=${c.avg_price:.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
