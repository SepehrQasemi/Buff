from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

from audit.schema import canonical_json
from execution.clock import parse_utc, format_utc
from buff.features.metadata import get_git_sha, sha256_file
from execution.idempotency_inspect import (
    IdempotencyInspectError,
    fetch_all_records,
    open_idempotency_db,
)


class BundleError(RuntimeError):
    pass


def _git_sha_or_raise() -> str:
    env_sha = os.getenv("GITHUB_SHA") or os.getenv("GIT_SHA")
    if env_sha:
        return env_sha
    sha = get_git_sha()
    if sha is None:
        raise BundleError("git_sha_unavailable")
    return sha


def collect_metadata(
    *,
    as_of_utc: str | None,
    db_path: Path,
    decision_records_path: Path,
    include_logs: Iterable[Path],
) -> dict[str, Any]:
    if as_of_utc is not None:
        try:
            as_of_utc = format_utc(parse_utc(as_of_utc))
        except ValueError as exc:
            raise BundleError("invalid_as_of_utc") from exc
    env_vars = {key: os.environ[key] for key in sorted(os.environ) if key.startswith("BUFF_")}
    return {
        "schema_version": "1.0",
        "generated_at_utc": as_of_utc,
        "git_sha": _git_sha_or_raise(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "paths": {
            "idempotency_db": str(db_path),
            "decision_records": str(decision_records_path),
            "include_logs": [str(path) for path in include_logs],
        },
        "env": env_vars,
    }


def export_idempotency_jsonl(db_path: Path, out_path: Path) -> None:
    try:
        conn = open_idempotency_db(str(db_path))
    except (FileNotFoundError, IdempotencyInspectError) as exc:
        raise BundleError(str(exc)) from exc
    try:
        rows = fetch_all_records(conn)
    except IdempotencyInspectError as exc:
        raise BundleError(str(exc)) from exc
    finally:
        conn.close()
    lines = [canonical_json({"key": key, "record": record}) for key, record in rows]
    payload = "\n".join(lines) + ("\n" if lines else "")
    out_path.write_text(payload, encoding="utf-8")


def _iter_decision_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    raise BundleError(f"decision_records_path_not_found:{path}")


def build_decision_records_index(decision_records_path: Path, out_path: Path) -> None:
    files = _iter_decision_files(decision_records_path)
    entries: list[dict[str, Any]] = []
    for file_path in files:
        try:
            line_count = sum(
                1 for line in file_path.read_text(encoding="utf-8").splitlines() if line
            )
        except OSError as exc:
            raise BundleError(f"decision_records_read_error:{file_path}") from exc
        entries.append(
            {
                "path": file_path.as_posix(),
                "sha256": sha256_file(file_path),
                "line_count": line_count,
            }
        )
    payload = {
        "schema_version": "1.0",
        "files": entries,
    }
    out_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def write_checksums(bundle_dir: Path, rel_paths: list[Path], out_path: Path) -> None:
    lines: list[str] = []
    for rel_path in sorted(rel_paths, key=lambda path: path.as_posix()):
        file_path = bundle_dir / rel_path
        lines.append(f"{sha256_file(file_path)}  {rel_path.as_posix()}")
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _collect_extra_files(paths: Iterable[Path]) -> list[tuple[Path, Path]]:
    collected: list[tuple[Path, Path]] = []
    for path in paths:
        if path.is_file():
            collected.append((path, Path("logs") / path.name))
        elif path.is_dir():
            base = Path("logs") / path.name
            for file_path in sorted(path.rglob("*")):
                if file_path.is_file():
                    rel = file_path.relative_to(path)
                    collected.append((file_path, base / rel))
        else:
            raise BundleError(f"include_path_not_found:{path}")
    return collected


def _write_metadata(out_path: Path, metadata: dict[str, Any]) -> None:
    out_path.write_text(canonical_json(metadata) + "\n", encoding="utf-8")


def _create_zip(bundle_dir: Path, zip_path: Path, rel_paths: list[Path]) -> None:
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel_path in sorted(rel_paths, key=lambda path: path.as_posix()):
            file_path = bundle_dir / rel_path
            data = file_path.read_bytes()
            info = zipfile.ZipInfo(rel_path.as_posix(), date_time=fixed_time)
            info.create_system = 0
            info.external_attr = 0
            zf.writestr(info, data)


def build_bundle(
    *,
    out_path: Path,
    fmt: str,
    as_of_utc: str | None,
    db_path: Path,
    decision_records_path: Path,
    include_logs: Iterable[Path],
) -> Path:
    if out_path.exists():
        raise BundleError(f"output_exists:{out_path}")

    include_list = list(include_logs)
    metadata = collect_metadata(
        as_of_utc=as_of_utc,
        db_path=db_path,
        decision_records_path=decision_records_path,
        include_logs=include_list,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_dir = Path(temp_dir)
        idempotency_path = bundle_dir / "idempotency.jsonl"
        decision_index_path = bundle_dir / "decision_records_index.json"
        metadata_path = bundle_dir / "metadata.json"

        export_idempotency_jsonl(db_path, idempotency_path)
        build_decision_records_index(decision_records_path, decision_index_path)
        _write_metadata(metadata_path, metadata)

        extra_files = _collect_extra_files(include_list)
        for src_path, rel_path in extra_files:
            target = bundle_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, target)

        rel_paths = [
            Path("metadata.json"),
            Path("idempotency.jsonl"),
            Path("decision_records_index.json"),
        ] + [rel for _, rel in extra_files]

        checksums_path = bundle_dir / "checksums.txt"
        write_checksums(bundle_dir, rel_paths, checksums_path)
        rel_paths.append(Path("checksums.txt"))

        if fmt == "dir":
            shutil.copytree(bundle_dir, out_path)
            return out_path
        if fmt == "zip":
            _create_zip(bundle_dir, out_path, rel_paths)
            return out_path
        raise BundleError(f"invalid_format:{fmt}")
