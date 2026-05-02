from datetime import date, datetime, timedelta

from scanner.cluster import find_clusters, score_trade
from scanner.edgar import InsiderTrade


def make_trade(ticker, name, day_offset, price=10.0, shares=1000, officer=True):
    return InsiderTrade(
        accession=f"acc-{name}-{day_offset}",
        filed_at=datetime(2026, 1, 1) + timedelta(days=day_offset),
        issuer_cik="1",
        issuer_name=f"{ticker} Inc",
        issuer_ticker=ticker,
        insider_name=name,
        insider_title="CEO",
        is_officer=officer,
        is_director=not officer,
        transaction_date=date(2026, 1, 1) + timedelta(days=day_offset),
        transaction_code="P",
        shares=shares,
        price=price,
        shares_owned_after=shares * 5,
    )


def test_finds_two_insider_cluster_within_window():
    trades = [
        make_trade("FOO", "Alice Officer", 0),
        make_trade("FOO", "Bob Director", 3, officer=False),
    ]
    clusters = find_clusters(trades, window_days=5, min_insiders=2)
    assert len(clusters) == 1
    assert clusters[0].ticker == "FOO"
    assert clusters[0].insider_count == 2


def test_ignores_solo_buyer():
    trades = [make_trade("BAR", "Solo Officer", 0)]
    assert find_clusters(trades, window_days=5, min_insiders=2) == []


def test_window_cutoff_excludes_far_apart_trades():
    trades = [
        make_trade("BAZ", "Alice", 0),
        make_trade("BAZ", "Bob", 30),
    ]
    assert find_clusters(trades, window_days=5, min_insiders=2) == []


def test_multiple_trades_same_insider_dont_count_as_cluster():
    trades = [
        make_trade("QUX", "Alice", 0),
        make_trade("QUX", "Alice", 1),
        make_trade("QUX", "Alice", 2),
    ]
    assert find_clusters(trades, window_days=5, min_insiders=2) == []


def test_score_prefers_more_insiders_then_dollars():
    small = [
        make_trade("A", "X", 0, shares=100),
        make_trade("A", "Y", 1, shares=100),
    ]
    big = [
        make_trade("B", "X", 0, shares=10_000),
        make_trade("B", "Y", 1, shares=10_000),
        make_trade("B", "Z", 2, shares=10_000),
    ]
    small_cluster = find_clusters(small)[0]
    big_cluster = find_clusters(big)[0]
    assert score_trade(big_cluster) > score_trade(small_cluster)
