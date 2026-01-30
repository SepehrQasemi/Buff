from __future__ import annotations

import json
from hashlib import sha256


def stable_json_dumps(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def inputs_digest(payload: dict) -> str:
    return sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()
