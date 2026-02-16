import re
from pathlib import Path

DOC_PATH = Path("docs/03_CONTRACTS_AND_SCHEMAS.md")
API_DIR = Path("apps/api")


def _extract_doc_codes() -> set[str]:
    text = DOC_PATH.read_text(encoding="utf-8")
    codes: set[str] = set()
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## error code registry"):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            for token in re.findall(r"`([A-Za-z0-9_]+)`", line):
                codes.add(token.lower())
    return codes


def _extract_api_codes() -> set[str]:
    codes: set[str] = set()
    for path in API_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        codes.update(re.findall(r"raise_api_error\(\s*\d+\s*,\s*['\"]([a-z0-9_]+)['\"]", text))
        codes.update(re.findall(r"build_error_payload\(\s*['\"]([a-z0-9_]+)['\"]", text))
    return codes


def test_phase1_error_codes_documented() -> None:
    doc_codes = _extract_doc_codes()
    assert doc_codes, "No error codes found in docs/03_CONTRACTS_AND_SCHEMAS.md"
    api_codes = _extract_api_codes()
    missing = sorted(api_codes - doc_codes)
    assert not missing, f"Undocumented error codes: {missing}"
