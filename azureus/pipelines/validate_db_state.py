"""DB-state validation flow — defensive invariants across the data layer.

A weekly Prefect flow (per `docs/PHASE_1_CHECKLIST.md` §3.8) that runs a
suite of integrity checks against the populated database. Each check
returns a `CheckResult` with one of three severities:

- `info` — observation, never raises, lineage record only
- `warning` — surfaces a known limitation or expected gap; flow status
  becomes `partial`, never raises
- `error` — invariant breach; flow status becomes `failed`, raises after
  the lineage row is written

The flow writes one `ingestion_runs` row per invocation summarising all
results in `errors` JSONB. Phase 1 invokes this manually; Phase 2 brings
the Prefect server and scheduling.

What's checked:

1. **No future bar dates** in `prices` (`date > today` ⇒ error).
2. **No future `reported_date`** in `fundamentals_pit` and `macro_series`
   (when those tables have rows — skipped silently otherwise).
3. **Universe coverage** — every member of every active `universe_membership`
   row must have at least one price bar (`warning`, not error: known gaps
   like 0011.HK on the free-data path).
4. **Recent ingestion** — newest `prices.date` must be within 10 calendar
   days of today (`warning`; deployed instance hasn't been kept current).
5. **No orphan FKs** — defence-in-depth against migration accidents
   (FK constraint normally enforces, but a dropped/broken constraint is
   easy to miss otherwise).
"""

from __future__ import annotations

import datetime as dt
import logging
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any

from prefect import flow
from sqlalchemy import text

from azureus.data.db import sync_session
from azureus.data.models import IngestionRun
from azureus.utils.reproducibility import capture_reproducibility

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "validate_db_state"
_TABLE_NAME = "__validation__"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

_STALE_INGEST_DAYS = 10


@dataclass
class CheckResult:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


# ---- individual checks ---------------------------------------------------


def _check_no_future_price_dates() -> CheckResult | None:
    with sync_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM prices WHERE date > CURRENT_DATE")
        ).scalar_one()
    if count == 0:
        return None
    return CheckResult(
        name="no_future_price_dates",
        severity=SEVERITY_ERROR,
        message=f"{count} price rows with date > today — clock skew or bad ingestion",
        details={"violating_rows": count},
    )


def _check_no_future_reported_dates() -> list[CheckResult]:
    """Across `fundamentals_pit` and `macro_series` — error if any row has
    `reported_date > today` (would already poison any PIT query that picks
    a today-or-earlier `as_of_date`).
    """
    results: list[CheckResult] = []
    for table, col in (("fundamentals_pit", "reported_date"), ("macro_series", "reported_date")):
        with sync_session() as session:
            row_count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            if row_count == 0:
                continue
            count = session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} > CURRENT_DATE")
            ).scalar_one()
        if count > 0:
            results.append(
                CheckResult(
                    name=f"no_future_reported_dates_{table}",
                    severity=SEVERITY_ERROR,
                    message=f"{count} {table} rows with {col} > today",
                    details={"table": table, "violating_rows": count},
                )
            )
    return results


def _check_universe_coverage() -> CheckResult | None:
    """Every active universe member must have >= 1 price bar.

    Severity is `warning`, not `error`: free-data-path gaps like 0011.HK
    are known and documented. Strategies that touch those tickers will
    simply skip them.
    """
    with sync_session() as session:
        rows = session.execute(
            text(
                """
                SELECT u.ticker
                FROM universe_membership u
                LEFT JOIN prices p ON p.ticker = u.ticker
                WHERE u.end_date IS NULL  -- still a member
                GROUP BY u.ticker
                HAVING COUNT(p.ticker) = 0
                ORDER BY u.ticker
                """
            )
        ).all()
    missing = [r[0] for r in rows]
    if not missing:
        return None
    return CheckResult(
        name="universe_coverage",
        severity=SEVERITY_WARNING,
        message=f"{len(missing)} universe members have zero price rows",
        details={"missing_tickers": missing},
    )


def _check_recent_ingest() -> CheckResult | None:
    with sync_session() as session:
        latest = session.execute(text("SELECT MAX(date) FROM prices")).scalar_one()
    if latest is None:
        return CheckResult(
            name="recent_ingest",
            severity=SEVERITY_WARNING,
            message="prices table is empty — has the ingestion ever run?",
        )
    days_old = (dt.date.today() - latest).days
    if days_old <= _STALE_INGEST_DAYS:
        return None
    return CheckResult(
        name="recent_ingest",
        severity=SEVERITY_WARNING,
        message=(
            f"newest price bar is {days_old} calendar days old (threshold {_STALE_INGEST_DAYS})"
        ),
        details={"latest_bar": latest.isoformat(), "days_old": days_old},
    )


def _check_no_orphan_price_tickers() -> CheckResult | None:
    """Defence-in-depth — FK normally enforces this; we re-check explicitly."""
    with sync_session() as session:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT p.ticker
                FROM prices p
                LEFT JOIN tickers t ON t.ticker = p.ticker
                WHERE t.ticker IS NULL
                ORDER BY p.ticker
                """
            )
        ).all()
    orphans = [r[0] for r in rows]
    if not orphans:
        return None
    return CheckResult(
        name="no_orphan_price_tickers",
        severity=SEVERITY_ERROR,
        message=f"{len(orphans)} ticker(s) in prices have no row in tickers",
        details={"orphan_tickers": orphans},
    )


# ---- the flow ------------------------------------------------------------


_CHECKS_RETURNING_ONE: list[Any] = [
    _check_no_future_price_dates,
    _check_universe_coverage,
    _check_recent_ingest,
    _check_no_orphan_price_tickers,
]
_CHECKS_RETURNING_MANY: list[Any] = [
    _check_no_future_reported_dates,
]


def _run_all_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for check in _CHECKS_RETURNING_ONE:
        try:
            result = check()
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.exception("check %s raised", check.__name__)
            results.append(
                CheckResult(
                    name=check.__name__,
                    severity=SEVERITY_ERROR,
                    message=f"check raised: {type(exc).__name__}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
            )

    for check in _CHECKS_RETURNING_MANY:
        try:
            results.extend(check())
        except Exception as exc:
            logger.exception("check %s raised", check.__name__)
            results.append(
                CheckResult(
                    name=check.__name__,
                    severity=SEVERITY_ERROR,
                    message=f"check raised: {type(exc).__name__}: {exc}",
                    details={"traceback": traceback.format_exc()},
                )
            )
    return results


@flow(name=_PIPELINE_NAME, log_prints=False)
def validate_db_state() -> dict[str, Any]:
    """Run the full validation suite. Returns a summary dict.

    Raises `RuntimeError` after the lineage row is written if any check
    has severity `error`. Warnings and info results never raise; they
    set the flow status to `partial` and `success` respectively.
    """
    started_at = dt.datetime.now(tz=dt.UTC)
    results = _run_all_checks()

    errors = [r for r in results if r.severity == SEVERITY_ERROR]
    warnings_ = [r for r in results if r.severity == SEVERITY_WARNING]

    if errors:
        status = "failed"
    elif warnings_:
        status = "partial"
    else:
        status = "success"

    summary = {
        "status": status,
        "checks_total": len(_CHECKS_RETURNING_ONE) + len(_CHECKS_RETURNING_MANY),
        "errors": len(errors),
        "warnings": len(warnings_),
        "results": [asdict(r) for r in results],
    }

    _write_lineage(
        started_at=started_at,
        status=status,
        results=results,
    )

    logger.info(
        "validation done: status=%s, %d error(s), %d warning(s)",
        status,
        len(errors),
        len(warnings_),
    )

    if status == "failed":
        names = ", ".join(r.name for r in errors)
        raise RuntimeError(
            f"DB validation failed: {len(errors)} error-severity check(s): {names}. "
            "See ingestion_runs for details."
        )

    return summary


def _write_lineage(
    *,
    started_at: dt.datetime,
    status: str,
    results: list[CheckResult],
) -> None:
    """One `ingestion_runs` row summarising the full check suite."""
    errors = [r for r in results if r.severity == SEVERITY_ERROR]
    warnings_ = [r for r in results if r.severity == SEVERITY_WARNING]

    try:
        with sync_session() as session:
            session.add(
                IngestionRun(
                    pipeline_name=_PIPELINE_NAME,
                    provider="internal",
                    table_name=_TABLE_NAME,
                    status=status,
                    started_at=started_at,
                    completed_at=dt.datetime.now(tz=dt.UTC),
                    rows_inserted=0,
                    rows_updated=0,
                    rows_failed=len(errors),
                    errors=({"results": [asdict(r) for r in results]} if results else None),
                    config={
                        "checks_run": [
                            c.__name__ for c in _CHECKS_RETURNING_ONE + _CHECKS_RETURNING_MANY
                        ],
                        "errors": len(errors),
                        "warnings": len(warnings_),
                        "reproducibility": capture_reproducibility(),
                    },
                )
            )
    except Exception:
        logger.exception(
            "CRITICAL: failed to persist validate_db_state lineage row "
            "(status=%s, errors=%d) — lineage is incomplete",
            status,
            len(errors),
        )


def main() -> None:
    """CLI entry.

    Run: `uv run python -m azureus.pipelines.validate_db_state`
    Exits 0 on success, 1 on partial (warnings), 2 on failed (errors).
    """
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    try:
        summary = validate_db_state()
    except RuntimeError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"=== validate_db_state: {summary['status']} ===")
    print(
        f"checks_total={summary['checks_total']}  "
        f"errors={summary['errors']}  warnings={summary['warnings']}"
    )
    for result in summary["results"]:
        print(f"  [{result['severity']:8s}] {result['name']}: {result['message']}")

    sys.exit(1 if summary["status"] == "partial" else 0)


if __name__ == "__main__":
    main()
