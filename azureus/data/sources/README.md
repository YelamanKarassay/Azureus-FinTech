# Data Sources — Free-Path Limitations & Known Issues

The deployed instance of Azureus runs on free-source data (yfinance + a
committed static universe CSV). The developer's research-grade runs use
Bloomberg locally (`BloombergDataSource`, Phase 5). Both implement the
same `DataSource` Protocol — strategies don't care which is in use.

This file documents the **honest, deliberate limitations** of the free path
so the methodology page can cite them and so contributors don't mistake
them for bugs.

## Universe membership (CSV)

`data/universe/hsi_members.csv` captures the v1 Hang Seng Index universe.
For Phase 1 (Option B per `docs/PHASE_1_CHECKLIST.md` Day 9):

- **Current members** are present with `start_date = 2014-01-01` (a
  conservative lower bound — they were definitely HSI members by that
  point, and most were members long before).
- **Known late additions** (post-2014 IPOs added to HSI in subsequent
  quarterly reviews) use the **HK listing date** as `start_date`. This
  is NOT the exact HSI inclusion date — that requires Bloomberg's
  `INDX_MWEIGHT_HIST` field. We use listing date because (a) the names
  weren't tradable before then anyway, and (b) HSI inclusion dates from
  public sources are inconsistent. Names affected: 1209.HK, 1810.HK,
  2015.HK, 3690.HK, 6098.HK, 6618.HK, 6862.HK, 9618.HK, 9633.HK,
  9888.HK, 9988.HK, 9999.HK.
- **Removed names** (companies that were in the HSI within our 10y window
  but have since been removed) are **NOT captured**. The CSV is built
  from current snapshot + public IPO records; no historical removal data
  is available without Bloomberg.

### Known coverage gaps found in Day 13 audit (2026-05-23)

A 12-year batch ingest (`--lookback-days 4500`) surfaced three classes of
issue. Run `uv run python -m scripts.audit_prices_coverage` for the live
report.

1. **`0011.HK` (Hang Seng Bank) — completely missing.** yfinance returns
   `404 Quote not found for symbol: 0011.HK`; we tried `0011.HK`,
   `11.HK`, `0011.HKG`, and `HSB.HK` — none resolve. This is a genuine
   yfinance gap for this specific name, not a code bug. Strategies will
   simply omit 0011.HK from rebalances on the free-data path. Bloomberg
   covers it in Phase 5.

2. **Late-listing corrections** — three names had Day 9 CSV entries
   with `start_date = 2014-01-01` but actually IPO'd after that date.
   Corrected on Day 13:

   | Ticker | Name | Old start_date | Corrected to |
   |---|---|---|---|
   | `1876.HK` | Budweiser Brewing Company APAC | 2014-01-01 | 2019-09-30 |
   | `1997.HK` | Wharf Real Estate Investment | 2014-01-01 | 2017-11-15 |
   | `2269.HK` | WuXi Biologics | 2014-01-01 | 2017-06-13 |

3. **Country Garden (`2007.HK`) 9-month suspension** in `prices` — 198
   consecutive zero-volume bars from 2024-04-02 to 2025-01-20. **This
   is a real corporate event** (Country Garden's debt restructuring;
   stock trading suspended on the exchange), not a data quality bug.
   Strategy code that uses turnover/liquidity filters will naturally
   exclude suspended names. Similar shorter runs exist for `1378.HK`,
   `2899.HK`, `2018.HK`, and a few others — all real suspensions.

### Residual survivorship bias

The missing removed names create survivorship bias in any backtest using
this universe. Academic estimates put the magnitude at **1–4% per year of
inflated returns** for equity strategies (Brown, Goetzmann, Ross, 1995;
Carhart, 1997). This is a known, documented limitation.

**Mitigation:** the `BloombergDataSource` path (research-only, not
deployed) uses `INDX_MWEIGHT_HIST` quarterly snapshots — full delisted-
name coverage. Deployment-grade backtests on `azureus.tech` are
explicitly labelled "demo-grade data with residual survivorship bias";
the methodology page (Phase 3+) will spell this out for visitors.

## Prices (yfinance)

- HK ticker format: `0700.HK` (zero-padded 4-digit + `.HK`). Internal
  canonical form is the yfinance form.
- `auto_adjust=False` — we keep raw OHLC and a separate `adjusted_close`
  column. Adjusted close is canonical for return calculations.
- Rows with `close = NaN` (holidays, pre-listing, suspensions) are
  dropped at the fetch layer. We never persist a bar without a close.
- yfinance is rate-limited and occasionally returns no rows for valid
  tickers (especially under load). The ingestion flow records every
  failure with full context in `ingestion_runs`; pipelines do not retry
  inside a single run.

### Known yfinance quirks for HK names

- Dividend/split events are reflected in `adjusted_close` but the raw
  OHLC columns are NOT adjusted. Use `adjusted_close` for any return-
  based calculation.
- Volume can be `0` on holidays or near-holidays — these rows pass
  validation (volume nullable, `>= 0`) but should be filtered in feature
  code that relies on liquidity.
- Some HK tickers' history starts later than their actual HK listing
  (yfinance source gap). This is what `tickers.listed_date` is for —
  caller can detect the mismatch.

## Fundamentals

**Not implemented in the free path yet** — Day 9–11 of
`docs/PHASE_1_CHECKLIST.md`. The yfinance API exposes a `Ticker.income_stmt`
endpoint but without point-in-time `reported_date` information — it gives
you the current view of historical statements, not what was known on each
historical date. This makes it unsuitable for PIT-correct backtests as-is.

Two paths under consideration:
1. Approximate `reported_date = period_end + 60 days` (HK regulatory
   convention) and document the approximation.
2. Stop short of fundamentals on the free path; require Bloomberg for
   Strategy 1 / 2. Document this clearly.

Decision will land with Day 9–11.

## Macro

**Not implemented in the free path yet** — late Phase 1. yfinance covers
some macro series (US 10Y via `^TNX`, VIX via `^VIX`, etc.); FRED is the
proper free source for US macro. HK-specific macro (HIBOR, USD/HKD)
likely needs HKMA's free API.

## Bloomberg

Research-grade, developer-only, never deployed. Bloomberg's license
prohibits redistribution and public deployment. Bloomberg-derived data
files are gitignored (`.gitignore` covers `data/bloomberg/`).

See ARCHITECTURE §1.8 for the two-source rationale.
