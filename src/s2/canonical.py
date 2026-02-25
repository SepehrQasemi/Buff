from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


FLOAT_SCALE = 8
_FLOAT_QUANT = Decimal("1").scaleb(-FLOAT_SCALE)
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
NUMERIC_POLICY = {
    "policy_id": "s2/numeric/fixed_decimal_8/v1",
    "format": "fixed_decimal",
    "decimals": 8,
    "rounding": "ROUND_HALF_EVEN",
    "notes": "All numeric fields serialized deterministically using this policy.",
}
NUMERIC_POLICY_ID = str(NUMERIC_POLICY["policy_id"])


def canonicalize_float(value: float | Decimal) -> str:
    dec = Decimal(str(value)).quantize(_FLOAT_QUANT, rounding=ROUND_HALF_EVEN)
    if dec == Decimal("-0").quantize(_FLOAT_QUANT):
        dec = Decimal("0").quantize(_FLOAT_QUANT)
    return format(dec, f".{FLOAT_SCALE}f")


def canonicalize_timestamp_utc(value: str | datetime) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    text = dt.isoformat(timespec="seconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def canonicalize_artifact_path(raw_path: str | Path, repo_root: Path | None = None) -> str:
    candidate = Path(raw_path).expanduser().resolve()
    root = (repo_root or Path.cwd()).resolve()
    try:
        rel = candidate.relative_to(root)
        return rel.as_posix()
    except ValueError:
        # Keep a stable logical identifier without OS-specific absolute components.
        return f"external/{candidate.name}"


def contains_forbidden_path_token(value: str) -> bool:
    text = str(value)
    if "\\" in text:
        return True
    if text.startswith("/"):
        return True
    if text.startswith("//"):
        return True
    if _WINDOWS_ABS_RE.match(text):
        return True
    return False


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non_finite_float")
        return canonicalize_float(value)
    if isinstance(value, Decimal):
        return canonicalize_float(value)
    if isinstance(value, datetime):
        return canonicalize_timestamp_utc(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize_for_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(child) for child in value]
    return value


def canonical_json_text(obj: object) -> str:
    normalized = _normalize_for_json(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_bytes(obj: object) -> bytes:
    return canonical_json_text(obj).encode("utf-8")


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_file(path: Path) -> str:
    return sha256_hex_bytes(path.read_bytes())


def write_canonical_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def write_canonical_jsonl(path: Path, rows: Iterable[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = [canonical_json_bytes(row) for row in rows]
    if not encoded:
        path.write_bytes(b"")
        return
    path.write_bytes(b"\n".join(encoded) + b"\n")


def stable_sort_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_fields: Sequence[str],
) -> list[dict[str, Any]]:
    def _stable_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        base = [row.get(field) for field in key_fields]
        # Tie-break deterministically on canonical serialized row bytes.
        return tuple(base + [canonical_json_text(dict(row))])

    return [dict(row) for row in sorted(rows, key=_stable_key)]


def validate_utf8_lf_bytes(data: bytes, *, artifact: str) -> None:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{artifact}:utf8_bom_forbidden")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{artifact}:invalid_utf8") from exc
    if b"\r" in data:
        raise ValueError(f"{artifact}:crlf_or_cr_forbidden")


def build_pack_root_hash(file_entries: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for row in file_entries:
        parts.append(f"{row['path']}\n{row['size_bytes']}\n{row['sha256']}\n")
    preimage = "".join(parts).encode("utf-8")
    return sha256_hex_bytes(preimage)


def numeric_policy_digest_sha256() -> str:
    return sha256_hex_bytes(canonical_json_bytes(NUMERIC_POLICY))


NUMERIC_POLICY_DIGEST_SHA256 = numeric_policy_digest_sha256()
