# Insider Cluster Buy Scanner

An SEC Form 4 scanner that flags clusters of insider open-market purchases and
emails the top 3 candidates each morning before the open. Built to match the
6-step pipeline in the Xynth screenshot:

1. Filter for open-market purchases (`transactionCode == P`)
2. Filter for officers / directors / 10%+ owners
3. Filter by market cap (caller-supplied; default <$500M)
4. Filter for ≥10% increase in insider's position
5. Find clusters: 2+ distinct insiders within a 5-day window
6. Email top 3 ranked by `score_trade`

## Install

```bash
pip install -r requirements.txt
```

## Run once

```bash
python -m scanner --days 1 --user-agent "Your Name you@example.com"
```

Output to JSON for the dashboard:

```bash
python -m scanner --days 2 --out output.json
open dashboard.html
```

## Daily email (cron, 6:55 AM ET = 10:55 UTC)

```cron
55 10 * * 1-5 EDGAR_USER_AGENT="Your Name you@example.com" \
  SMTP_HOST=smtp.gmail.com SMTP_USER=you@gmail.com SMTP_PASS=app-password \
  /usr/bin/python -m scanner --days 1 --email me@example.com
```

## Project layout

```
scanner/
  edgar.py         # EDGAR client + Form 4 XML parser
  cluster.py       # cluster detection + ranking
  email_report.py  # SMTP renderer + sender
  pipeline.py      # end-to-end orchestration
  __main__.py      # CLI entrypoint
tests/             # offline unit tests (no network)
dashboard.html     # dark-theme UI matching the screenshot
```

## Notes

- The EDGAR `User-Agent` header is mandatory; SEC will return 403 without it.
- Requests are throttled to ~8 req/s to stay within fair-use limits.
- Market-cap filtering needs a price/share-count source — stub it with your
  own provider (e.g. yfinance, IEX) at the `pipeline.run_scan` call site.
- Not investment advice. The signal documented by Cohen, Malloy & Pomorski
  (2012) is real but noisy at the trade level.
