"""End-to-end run: fetch → cluster → rank → optionally email."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from .cluster import Cluster, find_clusters, score_trade
from .edgar import fetch_recent_form4_filings
from .email_report import send_email


def _serialize(clusters: Sequence[Cluster]) -> list[dict]:
    out = []
    for c in clusters:
        out.append(
            {
                "ticker": c.ticker,
                "issuer_name": c.issuer_name,
                "insider_count": c.insider_count,
                "total_value": c.total_value,
                "avg_price": c.avg_price,
                "latest_filed": c.latest_filed.isoformat(),
                "trades": [
                    {
                        **{k: v for k, v in asdict(t).items() if not isinstance(v, (datetime, date))},
                        "transaction_date": t.transaction_date.isoformat(),
                        "filed_at": t.filed_at.isoformat(),
                    }
                    for t in c.trades
                ],
            }
        )
    return out


def run_scan(
    *,
    days: int = 1,
    max_market_cap: float | None = 500_000_000,
    min_insiders: int = 2,
    window_days: int = 5,
    min_increase_pct: float = 0.0,
    output_path: str | Path | None = None,
    email_to: str | None = None,
    user_agent: str | None = None,
) -> list[Cluster]:
    """Run the full pipeline matching the screenshot's 5-step flow.

    Steps mirror the dashboard:
      1. Filter for open-market purchases (handled in edgar.parse_form4)
      2. Filter for C-suite / 10%+ owners (filtered below)
      3. Filter by market cap (caller supplies; not implemented offline)
      4. Filter for >= `min_increase_pct` increase in position
      5. Find clusters with `min_insiders` distinct names
    """
    ua = user_agent or os.environ.get("EDGAR_USER_AGENT")
    trades = fetch_recent_form4_filings(days=days, user_agent=ua) if ua else fetch_recent_form4_filings(days=days)

    qualifying = []
    for t in trades:
        if not (t.is_officer or t.is_director):
            continue
        if t.shares_owned_after > 0 and min_increase_pct > 0:
            prior = t.shares_owned_after - t.shares
            if prior <= 0:
                pct = float("inf")
            else:
                pct = (t.shares / prior) * 100
            if pct < min_increase_pct:
                continue
        qualifying.append(t)

    clusters = find_clusters(qualifying, window_days=window_days, min_insiders=min_insiders)
    clusters.sort(key=score_trade, reverse=True)

    if output_path:
        Path(output_path).write_text(json.dumps(_serialize(clusters), indent=2))

    if email_to and clusters:
        send_email(clusters, to=email_to)

    return clusters
