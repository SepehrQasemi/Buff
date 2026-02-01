from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from audit.bundle import BundleError, build_bundle
from audit.verify import verify_bundle
from execution.idempotency_sqlite import default_idempotency_db_path
from paper.paper_runner import PaperRunConfig, run_paper_smoke
import audit.decision_records as decision_records


class AuditRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditRunResult:
    ok: bool
    artifact: Path
    verified: bool
    seed: int
    as_of_utc: str | None


def _run_id(seed: int) -> str:
    return f"audit-{seed}"


def _cleanup_output(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def run_audit(
    *,
    seed: int,
    out_path: Path,
    as_of_utc: str | None,
    config_path: Path | None,
    decision_records_dir: Path | None,
    fmt: str,
    verify: bool,
    db_path: Path | None = None,
) -> AuditRunResult:
    if seed is None:
        raise AuditRunError("seed_required")
    if config_path is not None and not config_path.exists():
        raise AuditRunError(f"config_not_found:{config_path}")
    if out_path.exists():
        raise AuditRunError(f"output_exists:{out_path}")

    run_dir = decision_records_dir or Path("runs")
    run_id = _run_id(seed)
    config = PaperRunConfig(run_id=run_id, out_dir=str(run_dir))

    fixed_ts = as_of_utc or "1970-01-01T00:00:00Z"
    original_ts = decision_records._utc_timestamp
    decision_records._utc_timestamp = lambda: fixed_ts
    try:
        summary = run_paper_smoke(config)
    except RuntimeError as exc:
        raise AuditRunError("paper_run_failed") from exc
    finally:
        decision_records._utc_timestamp = original_ts

    records_path = Path(summary["records_path"])
    idempotency_db = db_path or default_idempotency_db_path()
    try:
        build_bundle(
            out_path=out_path,
            fmt=fmt,
            as_of_utc=as_of_utc,
            db_path=idempotency_db,
            decision_records_path=records_path,
            include_logs=[],
        )
    except BundleError as exc:
        _cleanup_output(out_path)
        raise AuditRunError(str(exc)) from exc

    verified = False
    if verify:
        report = verify_bundle(path=out_path, fmt="auto", strict=False, as_of_utc=as_of_utc)
        verified = report["ok"]
        if not report["ok"]:
            raise AuditRunError("bundle_verification_failed")

    return AuditRunResult(
        ok=True,
        artifact=out_path,
        verified=verified,
        seed=seed,
        as_of_utc=as_of_utc,
    )
