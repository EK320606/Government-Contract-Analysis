"""SEC EDGAR client for Form 4 (insider transaction) filings.

Form 4 is filed by officers, directors, and 10%+ owners within two
business days of any transaction in their company's equity. We only
care about open-market purchases (transaction code "P") since those
signal genuine bullish conviction (option exercises, gifts, and
10b5-1 sales add noise).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator

import requests
from lxml import etree

EDGAR_BASE = "https://www.sec.gov"
EDGAR_ATOM = EDGAR_BASE + "/cgi-bin/browse-edgar"
EDGAR_FULL_INDEX = EDGAR_BASE + "/Archives/edgar/full-index"

# SEC requires a descriptive User-Agent identifying the requester.
DEFAULT_UA = "Xynth Insider Scanner contact@example.com"


@dataclass(frozen=True)
class InsiderTrade:
    accession: str
    filed_at: datetime
    issuer_cik: str
    issuer_name: str
    issuer_ticker: str
    insider_name: str
    insider_title: str
    is_officer: bool
    is_director: bool
    transaction_date: date
    transaction_code: str
    shares: float
    price: float
    shares_owned_after: float

    @property
    def dollar_value(self) -> float:
        return self.shares * self.price


class EdgarClient:
    def __init__(self, user_agent: str = DEFAULT_UA, min_interval: float = 0.12):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        self.min_interval = min_interval
        self._last_call = 0.0

    def _get(self, url: str, **kwargs) -> requests.Response:
        # SEC fair-use: cap at ~10 req/s. We default to ~8 r/s.
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        resp = self.session.get(url, timeout=30, **kwargs)
        self._last_call = time.monotonic()
        resp.raise_for_status()
        return resp

    def recent_form4_index(self, target_day: date) -> list[dict]:
        """Read the daily form index and return every Form 4 entry.

        EDGAR publishes a `form.idx` per day under
        `/Archives/edgar/daily-index/<year>/QTR<n>/`. Each line is
        fixed-width: form, company, CIK, date filed, filename.
        """
        quarter = (target_day.month - 1) // 3 + 1
        url = (
            f"{EDGAR_BASE}/Archives/edgar/daily-index/{target_day.year}/"
            f"QTR{quarter}/form.{target_day:%Y%m%d}.idx"
        )
        resp = self._get(url)
        out: list[dict] = []
        for line in resp.text.splitlines():
            if not line.startswith("4 "):
                continue
            # Form, Company Name, CIK, Date Filed, Filename
            parts = re.split(r"\s{2,}", line.strip(), maxsplit=4)
            if len(parts) < 5:
                continue
            form, company, cik, filed, filename = parts
            if form.strip() != "4":
                continue
            out.append(
                {
                    "company": company.strip(),
                    "cik": cik.strip(),
                    "filed": datetime.strptime(filed.strip(), "%Y-%m-%d"),
                    "path": filename.strip(),
                    "accession": filename.strip().rsplit("/", 1)[-1].replace(".txt", ""),
                }
            )
        return out

    def form4_xml(self, path: str) -> bytes:
        """Resolve a Form 4 submission to its primary XML document."""
        # form.idx returns the .txt submission wrapper. The structured
        # XML lives in the accession directory under a `*.xml` file.
        accession_no_dash = path.rsplit("/", 1)[-1].replace(".txt", "").replace("-", "")
        cik_part = path.split("/data/")[1].split("/")[0]
        index_url = (
            f"{EDGAR_BASE}/Archives/edgar/data/{cik_part}/{accession_no_dash}/"
        )
        listing = self._get(index_url + "index.json").json()
        xml_name = next(
            (
                f["name"]
                for f in listing["directory"]["item"]
                if f["name"].endswith(".xml") and "primary_doc" in f["name"].lower()
            ),
            None,
        )
        if not xml_name:
            xml_name = next(
                (f["name"] for f in listing["directory"]["item"] if f["name"].endswith(".xml")),
                None,
            )
        if not xml_name:
            raise ValueError(f"No XML doc in {index_url}")
        return self._get(index_url + xml_name).content


def _text(node, xpath: str, default: str = "") -> str:
    found = node.xpath(xpath)
    if not found:
        return default
    val = found[0]
    return val.text.strip() if hasattr(val, "text") and val.text else (str(val).strip() or default)


def parse_form4(xml_bytes: bytes, accession: str, filed_at: datetime) -> Iterator[InsiderTrade]:
    """Yield one InsiderTrade per non-derivative purchase in the filing."""
    root = etree.fromstring(xml_bytes)

    issuer_cik = _text(root, "issuer/issuerCik")
    issuer_name = _text(root, "issuer/issuerName")
    issuer_ticker = _text(root, "issuer/issuerTradingSymbol").upper()
    insider_name = _text(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    is_officer = _text(root, "reportingOwner/reportingOwnerRelationship/isOfficer") == "1"
    is_director = _text(root, "reportingOwner/reportingOwnerRelationship/isDirector") == "1"
    title = _text(root, "reportingOwner/reportingOwnerRelationship/officerTitle")

    for tx in root.xpath("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode")
        if code != "P":  # open-market purchase only
            continue
        try:
            shares = float(_text(tx, "transactionAmounts/transactionShares/value"))
            price = float(_text(tx, "transactionAmounts/transactionPricePerShare/value"))
            shares_after = float(
                _text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value", "0")
            )
        except ValueError:
            continue
        try:
            tx_date = datetime.strptime(
                _text(tx, "transactionDate/value"), "%Y-%m-%d"
            ).date()
        except ValueError:
            continue
        yield InsiderTrade(
            accession=accession,
            filed_at=filed_at,
            issuer_cik=issuer_cik,
            issuer_name=issuer_name,
            issuer_ticker=issuer_ticker,
            insider_name=insider_name,
            insider_title=title,
            is_officer=is_officer,
            is_director=is_director,
            transaction_date=tx_date,
            transaction_code=code,
            shares=shares,
            price=price,
            shares_owned_after=shares_after,
        )


def fetch_recent_form4_filings(
    days: int = 1,
    user_agent: str = DEFAULT_UA,
    end_date: date | None = None,
) -> Iterator[InsiderTrade]:
    """Stream every insider purchase filed in the last `days` business days."""
    client = EdgarClient(user_agent=user_agent)
    end_date = end_date or date.today()
    seen: set[str] = set()

    cursor = end_date
    collected = 0
    while collected < days:
        if cursor.weekday() >= 5:  # skip weekends
            cursor -= timedelta(days=1)
            continue
        try:
            entries = client.recent_form4_index(cursor)
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                # holiday or future date; skip
                cursor -= timedelta(days=1)
                continue
            raise

        for entry in entries:
            if entry["accession"] in seen:
                continue
            seen.add(entry["accession"])
            try:
                xml = client.form4_xml(entry["path"])
            except (requests.HTTPError, ValueError):
                continue
            try:
                yield from parse_form4(xml, entry["accession"], entry["filed"])
            except etree.XMLSyntaxError:
                continue

        collected += 1
        cursor -= timedelta(days=1)
