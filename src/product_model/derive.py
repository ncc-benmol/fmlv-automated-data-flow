"""Fields FMLV keeps in step with another field rather than collecting separately.

Some in-scope columns are not independent facts about a vehicle — they are copies of
another column that FMLV maintains alongside it. An adapter has nothing extra to read
for these, but they still have to be *attempted*: `product_model.schema.IN_SCOPE`
requires every in-scope field to be either found or reported as missing, so a column
no adapter ever populates otherwise prompts the reviewer to confirm it by hand on every
matched product, on every run, for every manufacturer.

Deriving them centrally rather than in each adapter means no adapter can forget one,
and the derivation rule lives in one place where it can be checked against the export.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..adapters.base import ExtractedMotorhome, Provenance

#: `price_min_range_pounds` ("Min price guide") is a duplicate of `rrp_pounds` in FMLV's
#: own data: across all 179 active products in the six manufacturer exports held under
#: `data/exports/` on 20 August 2026 it equalled `rrp_pounds` on **every** row, never
#: differing and never blank where `rrp_pounds` was set. Its companion
#: `price_max_range_pounds` is blank throughout and is not in scope, so there is no
#: genuine price *range* being expressed — only one guide price, recorded twice.
#:
#: The NCC-side rule (20 August 2026) is that whatever price the manufacturer publishes
#: is the guide price, and it goes into `rrp_pounds`; this keeps the duplicate in step
#: with it rather than letting it hold last season's figure while `rrp_pounds` moves.
#: A stale price behind a site filter is worse than a visibly missing one.
#:
#: To stop maintaining this field instead, set its `automated_collection_scope_flag` to
#: something other than `in_scope` in `config/field_guide_motorhome.csv` and delete this
#: entry — no other code change is needed.
MIRRORED_FIELDS: dict[str, str] = {
    "price_min_range_pounds": "rrp_pounds",
}


def apply_mirrored_fields(extracted: Iterable[ExtractedMotorhome]) -> int:
    """Copy each mirrored field from its source, in place. Returns how many were set.

    A field is only mirrored where the source actually has a value: an adapter that
    found no price (Swift, Rimor and Chausson publish none at all) must not appear to
    have found a `price_min_range_pounds`, so the copy is skipped and the field is
    honestly reported as missing instead.

    An existing value is never overwritten, so an adapter that does read one of these
    directly keeps its own reading and its own provenance.
    """
    filled = 0
    for item in extracted:
        for target, source in MIRRORED_FIELDS.items():
            if getattr(item.motorhome, target, None) is not None:
                continue
            value = getattr(item.motorhome, source, None)
            if value is None:
                continue

            setattr(item.motorhome, target, value)
            source_provenance = item.provenance.get(source)
            item.provenance[target] = Provenance(
                source_url=source_provenance.source_url if source_provenance else "",
                snippet=(
                    f"mirrored from {source} ({value}), which FMLV holds this field equal "
                    f"to on every product in the baseline exports — not read separately "
                    f"from the manufacturer's site"
                ),
            )
            filled += 1
    return filled
