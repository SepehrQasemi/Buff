from __future__ import annotations

from buff.features.canonical import canonical_json_bytes
from buff.features.contract import FeatureSpec, sort_specs


def test_canonical_json_bytes_stable_for_param_order() -> None:
    params_a = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    params_b = {"nested": {"x": 1, "y": 2}, "a": 1, "b": 2}
    assert canonical_json_bytes(params_a) == canonical_json_bytes(params_b)


def test_feature_spec_ordering_deterministic() -> None:
    spec_b = FeatureSpec(
        feature_id="b_feature",
        params={"alpha": 1},
        lookback=0,
        requires=[],
        outputs=["b_feature"],
    )
    spec_a = FeatureSpec(
        feature_id="a_feature",
        params={"alpha": 1},
        lookback=0,
        requires=[],
        outputs=["a_feature"],
    )
    ordered = sort_specs([spec_b, spec_a])
    assert [spec.feature_id for spec in ordered] == ["a_feature", "b_feature"]
