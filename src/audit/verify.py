from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from audit.schema import canonical_json


class VerifyError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_path(path: str) -> str:
    clean = path.lstrip("./")
    if ".." in Path(clean).parts:
        raise VerifyError("invalid_path")
    return clean


def load_bundle_vfs(path: Path, fmt: str) -> dict[str, bytes]:
    if fmt == "auto":
        if path.suffix.lower() == ".zip":
            fmt = "zip"
        elif path.is_dir():
            fmt = "dir"
        else:
            raise VerifyError("unknown_bundle_format")
    vfs: dict[str, bytes] = {}
    if fmt == "dir":
        if not path.is_dir():
            raise VerifyError("bundle_not_directory")
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                rel = _normalize_path(file_path.relative_to(path).as_posix())
                vfs[rel] = file_path.read_bytes()
        return vfs
    if fmt == "zip":
        if not path.is_file():
            raise VerifyError("bundle_not_zip")
        with zipfile.ZipFile(path, "r") as zf:
            for info in sorted(zf.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                rel = _normalize_path(info.filename)
                vfs[rel] = zf.read(info)
        return vfs
    raise VerifyError("unknown_bundle_format")


def parse_checksums(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise VerifyError("invalid_checksums_format")
        entries.append((parts[0], parts[1]))
    return entries


def verify_checksums(
    vfs: dict[str, bytes], checksums: list[tuple[str, str]], strict: bool
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    paths = [path for _, path in checksums]
    if len(paths) != len(set(paths)):
        errors.append({"code": "checksums_duplicate_path", "message": "duplicate paths"})
    if paths != sorted(paths):
        item = {"code": "checksums_unsorted", "message": "checksums not sorted"}
        if strict:
            errors.append(item)
        else:
            warnings.append(item)
    for sha, path in checksums:
        if path not in vfs:
            errors.append({"code": "checksums_missing_file", "message": path, "path": path})
            continue
        actual = sha256_bytes(vfs[path])
        if actual != sha:
            errors.append({"code": "checksums_mismatch", "message": path, "path": path})
    required = {
        "metadata.json",
        "idempotency.jsonl",
        "decision_records_index.json",
    }
    for name in sorted(required):
        if name not in paths:
            errors.append({"code": "checksums_missing_required", "message": name, "path": name})
    extra = sorted(set(vfs.keys()) - set(paths) - {"checksums.txt"})
    if extra:
        item = {"code": "checksums_extra_files", "message": ",".join(extra)}
        if strict:
            errors.append(item)
        else:
            warnings.append(item)
    return len(errors) == 0, errors, warnings


def verify_decision_records_index(
    vfs: dict[str, bytes], strict: bool
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw = vfs.get("decision_records_index.json")
    if raw is None:
        errors.append({"code": "index_missing", "message": "decision_records_index.json"})
        return False, errors, warnings
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        errors.append({"code": "index_invalid_json", "message": "decision_records_index.json"})
        return False, errors, warnings
    entries = payload.get("files")
    if not isinstance(entries, list):
        errors.append({"code": "index_missing_files", "message": "files"})
        return False, errors, warnings
    paths = []
    for entry in entries:
        path = entry.get("path")
        sha = entry.get("sha256")
        line_count = entry.get("line_count")
        if not isinstance(path, str) or not isinstance(sha, str) or not isinstance(line_count, int):
            errors.append({"code": "index_invalid_entry", "message": str(entry)})
            continue
        paths.append(path)
        data = vfs.get(path)
        if data is None:
            file_path = Path(path)
            if file_path.exists() and file_path.is_file():
                try:
                    data = file_path.read_bytes()
                except OSError:
                    errors.append({"code": "index_read_error", "message": path, "path": path})
                    continue
            else:
                errors.append({"code": "index_missing_file", "message": path, "path": path})
                continue
        if sha256_bytes(data) != sha:
            errors.append({"code": "index_checksum_mismatch", "message": path, "path": path})
        actual_lines = sum(1 for line in data.decode("utf-8").splitlines() if line)
        if actual_lines != line_count:
            errors.append({"code": "index_line_count_mismatch", "message": path, "path": path})
    if paths != sorted(paths):
        item = {"code": "index_unsorted", "message": "files not sorted"}
        if strict:
            errors.append(item)
        else:
            warnings.append(item)
    return len(errors) == 0, errors, warnings


def verify_idempotency_jsonl(
    vfs: dict[str, bytes], strict: bool
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw = vfs.get("idempotency.jsonl")
    if raw is None:
        errors.append({"code": "idempotency_missing", "message": "idempotency.jsonl"})
        return False, errors, warnings
    keys: list[str] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            errors.append({"code": "idempotency_invalid_json", "message": "invalid jsonl"})
            continue
        key = payload.get("key")
        record = payload.get("record")
        if not isinstance(key, str) or not isinstance(record, dict):
            errors.append({"code": "idempotency_invalid_entry", "message": str(payload)})
            continue
        keys.append(key)
        status = record.get("status")
        if status not in {"INFLIGHT", "PROCESSED"}:
            errors.append({"code": "idempotency_invalid_status", "message": key})
            continue
        if status == "INFLIGHT":
            if "reserved_at_utc" not in record or "reservation_token" not in record:
                errors.append({"code": "idempotency_missing_fields", "message": key})
        if status == "PROCESSED":
            if "result" not in record:
                errors.append({"code": "idempotency_missing_result", "message": key})
    if len(keys) != len(set(keys)):
        item = {"code": "idempotency_duplicate_keys", "message": "duplicate keys"}
        if strict:
            errors.append(item)
        else:
            warnings.append(item)
    if keys != sorted(keys):
        item = {"code": "idempotency_unsorted", "message": "keys not sorted"}
        if strict:
            errors.append(item)
        else:
            warnings.append(item)
    return len(errors) == 0, errors, warnings


def verify_metadata_json(
    vfs: dict[str, bytes], strict: bool, as_of_utc: str | None
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw = vfs.get("metadata.json")
    if raw is None:
        errors.append({"code": "metadata_missing", "message": "metadata.json"})
        return False, errors, warnings
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        errors.append({"code": "metadata_invalid_json", "message": "metadata.json"})
        return False, errors, warnings
    if not isinstance(payload, dict):
        errors.append({"code": "metadata_invalid_type", "message": "metadata.json"})
        return False, errors, warnings
    if strict:
        normalized = canonical_json(payload).encode("utf-8")
        if raw not in {normalized, normalized + b"\n"}:
            errors.append({"code": "metadata_not_canonical", "message": "metadata.json"})
        if as_of_utc is not None:
            if payload.get("generated_at_utc") != as_of_utc:
                errors.append({"code": "metadata_asof_mismatch", "message": "generated_at_utc"})
    return len(errors) == 0, errors, warnings


def verify_bundle(
    *, path: Path, fmt: str = "auto", strict: bool = False, as_of_utc: str | None = None
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        vfs = load_bundle_vfs(path, fmt)
    except VerifyError as exc:
        return {
            "ok": False,
            "errors": [{"code": str(exc), "message": str(exc)}],
            "warnings": [],
            "verified_files": [],
            "checksums_verified": False,
            "index_verified": False,
            "idempotency_verified": False,
            "metadata_verified": False,
        }
    required = {
        "metadata.json",
        "idempotency.jsonl",
        "decision_records_index.json",
        "checksums.txt",
    }
    missing = sorted(required - set(vfs.keys()))
    if missing:
        for name in missing:
            errors.append({"code": "required_missing", "message": name, "path": name})
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "verified_files": sorted(vfs.keys()),
            "checksums_verified": False,
            "index_verified": False,
            "idempotency_verified": False,
            "metadata_verified": False,
        }

    checksums_entries = parse_checksums(vfs["checksums.txt"].decode("utf-8"))
    ok_checksums, err, warn = verify_checksums(vfs, checksums_entries, strict)
    errors.extend(err)
    warnings.extend(warn)

    ok_index, err, warn = verify_decision_records_index(vfs, strict)
    errors.extend(err)
    warnings.extend(warn)

    ok_idemp, err, warn = verify_idempotency_jsonl(vfs, strict)
    errors.extend(err)
    warnings.extend(warn)

    ok_meta, err, warn = verify_metadata_json(vfs, strict, as_of_utc)
    errors.extend(err)
    warnings.extend(warn)

    warnings.sort(key=lambda item: (item.get("code", ""), item.get("path", "")))
    errors.sort(key=lambda item: (item.get("code", ""), item.get("path", "")))

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "verified_files": sorted(vfs.keys()),
        "checksums_verified": ok_checksums,
        "index_verified": ok_index,
        "idempotency_verified": ok_idemp,
        "metadata_verified": ok_meta,
    }
