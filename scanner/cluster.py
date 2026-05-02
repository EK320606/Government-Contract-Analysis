"""Detect cluster buys — multiple insiders at one issuer in a short window.

A "cluster" is the strongest insider-trading signal: when two or more
distinct C-suite or board members buy on the open market within a few
trading days of each other, the historical 12-month outperformance vs.
the S&P 500 has been documented in academic work (e.g. Cohen, Malloy &
Pomorski 2012). We don't try to reproduce those returns here — we just
surface the candidates.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable

from .edgar import InsiderTrade


@dataclass
class Cluster:
    ticker: str
    issuer_name: str
    trades: list[InsiderTrade] = field(default_factory=list)

    @property
    def insider_count(self) -> int:
        return len({t.insider_name for t in self.trades})

    @property
    def total_value(self) -> float:
        return sum(t.dollar_value for t in self.trades)

    @property
    def latest_filed(self):
        return max(t.filed_at for t in self.trades)

    @property
    def avg_price(self) -> float:
        total_shares = sum(t.shares for t in self.trades)
        return self.total_value / total_shares if total_shares else 0.0


def find_clusters(
    trades: Iterable[InsiderTrade],
    window_days: int = 5,
    min_insiders: int = 2,
) -> list[Cluster]:
    """Group purchases by issuer and return clusters meeting the threshold."""
    by_ticker: dict[str, list[InsiderTrade]] = defaultdict(list)
    for trade in trades:
        if not trade.issuer_ticker:
            continue
        by_ticker[trade.issuer_ticker].append(trade)

    clusters: list[Cluster] = []
    for ticker, ts in by_ticker.items():
        ts.sort(key=lambda t: t.transaction_date)
        # sliding window: any contiguous span of `window_days` with
        # `min_insiders` distinct names becomes a cluster.
        names_in_window: dict[str, list[InsiderTrade]] = defaultdict(list)
        window: list[InsiderTrade] = []
        for trade in ts:
            window.append(trade)
            names_in_window[trade.insider_name].append(trade)
            cutoff = trade.transaction_date - timedelta(days=window_days)
            while window and window[0].transaction_date < cutoff:
                evicted = window.pop(0)
                names_in_window[evicted.insider_name].remove(evicted)
                if not names_in_window[evicted.insider_name]:
                    del names_in_window[evicted.insider_name]
            if len(names_in_window) >= min_insiders:
                cluster_trades = [t for trades_ in names_in_window.values() for t in trades_]
                clusters.append(
                    Cluster(
                        ticker=ticker,
                        issuer_name=trade.issuer_name,
                        trades=sorted(set(cluster_trades), key=lambda t: t.transaction_date),
                    )
                )

    # Deduplicate: keep one cluster per ticker (the largest by insider count).
    best: dict[str, Cluster] = {}
    for c in clusters:
        prior = best.get(c.ticker)
        if prior is None or (c.insider_count, c.total_value) > (prior.insider_count, prior.total_value):
            best[c.ticker] = c
    return list(best.values())


def score_trade(cluster: Cluster) -> float:
    """Rank clusters: more insiders > more dollars > more recent."""
    seniority = sum(2 if t.is_officer else 1 for t in cluster.trades)
    recency_days = max((cluster.latest_filed.date() - cluster.trades[-1].transaction_date).days, 1)
    return (
        cluster.insider_count * 1000
        + seniority * 100
        + (cluster.total_value / 10_000)
        - recency_days
    )
