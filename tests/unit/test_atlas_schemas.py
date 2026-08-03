"""Unit tests for reserved atlas schemas: unit identity and keep-map shapes.

These shapes are the data contract for dissected head/expert pruning topologies
(schemas/atlas.py). Nothing here executes a model; it validates the reserved
data model.
"""

from __future__ import annotations

from eval_lab.schemas.atlas import (
    EvidenceKind,
    KeepMapEntry,
    UnitIdentity,
    UnitKeepMap,
    UnitKind,
)


def test_unit_identity_defaults_to_expert_kind() -> None:
    unit = UnitIdentity(
        source_model_id="src-1",
        layer_index=3,
        source_unit_id=7,
    )
    assert unit.unit_kind == UnitKind.expert


def test_head_keep_map_roundtrips_and_counts() -> None:
    head0 = UnitIdentity(
        source_model_id="src-1", layer_index=0, unit_kind=UnitKind.head, source_unit_id=0
    )
    head1 = UnitIdentity(
        source_model_id="src-1", layer_index=0, unit_kind=UnitKind.head, source_unit_id=1
    )
    head2 = UnitIdentity(
        source_model_id="src-1", layer_index=0, unit_kind=UnitKind.head, source_unit_id=2
    )
    km = UnitKeepMap(
        layer_index=0,
        unit_kind=UnitKind.head,
        top_k=2,
        entries=[
            KeepMapEntry(
                unit=head0, kept=True, top_k=2, saliency=0.9, saliency_signal="activation_count"
            ),
            KeepMapEntry(
                unit=head1, kept=True, top_k=2, saliency=0.7, saliency_signal="activation_count"
            ),
            KeepMapEntry(
                unit=head2, kept=False, top_k=2, saliency=0.1, saliency_signal="activation_count"
            ),
        ],
    )
    assert km.kept_count == 2
    assert km.entries[0].evidence_kind == EvidenceKind.measured
    assert km.entries[0].unit.unit_kind == UnitKind.head


def test_keep_map_entry_forbids_extra_fields() -> None:
    import pytest
    from pydantic import ValidationError

    unit = UnitIdentity(source_model_id="src-1", layer_index=0, source_unit_id=0)
    with pytest.raises(ValidationError):
        KeepMapEntry(unit=unit, kept=True, top_k=4, bogus="x")
