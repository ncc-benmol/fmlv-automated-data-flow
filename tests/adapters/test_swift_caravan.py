"""Swift's touring-caravan adapter — the second caravan adapter, and the first built on
a motorhome sibling's fetching rather than on `bailey_caravan.py`.

Fixtures were saved from the live site on 3 September 2026, trimmed the same way the
motorhome ones were: every `<script>` dropped **except** the `data-product-layouts-data`
block, plus `<style>` blocks and comments. The rest of the page is kept because the
headroom this adapter reads is in the range highlights prose, hundreds of KB away from
the JSON, and a fixture trimmed to "the spec data" would lose it.

Three of the seven range pages, chosen because each carries a trap:

* **Sprite** — the sub-1250kg micro trap (Alpine 4 is 1247kg), and prose stating
  `Overall body width 2.25m` where the JSON, the quick guide and FMLV all say 2.23m.
* **Conqueror Grande** — `560L`/`650L` model names, a range mixing single and twin axles,
  and the only duplicate MTPLM in the whole line-up (1886kg, twice).
* **Elegance Grande** — the payload the guide prints as one 201kg figure and FMLV splits
  into 160kg personal effects plus 41kg optional equipment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import ADAPTERS, adapter_for, adapters_for, swift, swift_caravan
from src.product_model.caravan import Caravan
from src.product_model.enums import CaravanBodyType
from src.vehicle_class import VehicleClass

FIXTURES_DIR = Path(__file__).parent / "fixtures"

INDEX = "swift_caravans_index.html"
SPRITE = "swift_caravan_sprite_layouts.html"
CONQUEROR_GRANDE = "swift_caravan_conqueror_grande_layouts.html"
ELEGANCE_GRANDE = "swift_caravan_elegance_grande_layouts.html"
GUIDE = "swift_caravan_quick_guide.txt"

#: Slug per fixture, since `range_and_model` needs the page's own slug to find the
#: boundary between the range name and the model.
SLUGS = {
    SPRITE: "swift-sprite",
    CONQUEROR_GRANDE: "swift-conqueror-grande",
    ELEGANCE_GRANDE: "swift-elegance-grande",
}

#: What the 2027 quick guide claims per range: Challenger 10 layouts, Elegance Grande 4,
#: Sprite 5, Conqueror 7. The base and Grande pages are counted together there, which is
#: why this is the total across seven pages rather than a per-page figure.
PUBLISHED_LAYOUT_COUNT = 26


def fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def parsed(name: str) -> list[swift_caravan.SwiftCaravan]:
    return swift_caravan.parse_range_page(fixture(name), slug=SLUGS[name])


def by_model(name: str, model: str) -> swift_caravan.SwiftCaravan:
    return next(product for product in parsed(name) if product.model == model)


@pytest.fixture
def guide() -> swift_caravan.GuideSpecs:
    return swift_caravan.parse_guide_specs(fixture(GUIDE))


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_the_two_swift_adapters_coexist() -> None:
    """Swift is the second manufacturer to hold both product areas."""
    assert adapter_for(swift_caravan.MANUFACTURER, VehicleClass.CARAVAN) is swift_caravan
    assert adapter_for(swift.MANUFACTURER, VehicleClass.MOTORHOME) is swift
    assert adapters_for("Swift Group Ltd") == {
        VehicleClass.MOTORHOME: swift,
        VehicleClass.CARAVAN: swift_caravan,
    }


def test_the_caravan_adapter_declares_its_product_area() -> None:
    """Omitting `VEHICLE_CLASS` would register this module over `swift.py`'s key."""
    assert swift_caravan.VEHICLE_CLASS is VehicleClass.CARAVAN
    assert ADAPTERS[("Swift Group Ltd", VehicleClass.CARAVAN)] is swift_caravan


def test_it_shares_the_manufacturer_string_with_the_motorhome_adapter() -> None:
    """The name is the join key back to FMLV, so the two modules must not drift."""
    assert swift_caravan.MANUFACTURER == swift.MANUFACTURER == "Swift Group Ltd"
    assert swift_caravan.MANUFACTURER_DISPLAY_NAME == swift.MANUFACTURER_DISPLAY_NAME


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_the_index_links_all_seven_range_pages() -> None:
    paths = swift_caravan.find_range_page_paths(fixture(INDEX))
    assert paths == [
        "/caravans/product/1303/swift-sprite/",
        "/caravans/product/1304/swift-sprite-grande/",
        "/caravans/product/1305/swift-challenger/",
        "/caravans/product/1306/swift-challenger-grande/",
        "/caravans/product/72924/swift-conqueror/",
        "/caravans/product/72943/swift-conqueror-grande/",
        "/caravans/product/1309/swift-elegance-grande/",
    ]


def test_every_default_range_slug_is_actually_on_the_index() -> None:
    """`--range` values have to match what the index links, or a run collects nothing."""
    for slug, _label in swift_caravan.DEFAULT_RANGES:
        assert swift_caravan.find_range_page_paths(fixture(INDEX), slug), slug


def test_a_range_filter_narrows_to_one_page() -> None:
    assert swift_caravan.find_range_page_paths(fixture(INDEX), "swift-sprite") == [
        "/caravans/product/1303/swift-sprite/"
    ]


def test_the_base_range_filter_does_not_also_match_its_grande() -> None:
    """`swift-sprite` is a prefix of `swift-sprite-grande`.

    Matching on the path's final segment rather than on a substring is what keeps
    `--range swift-sprite` from silently pulling in the Grande's layouts too.
    """
    assert swift_caravan.find_range_page_paths(fixture(INDEX), "swift-sprite") == [
        "/caravans/product/1303/swift-sprite/"
    ]
    assert swift_caravan.find_range_page_paths(fixture(INDEX), "swift-sprite-grande") == [
        "/caravans/product/1304/swift-sprite-grande/"
    ]


def test_the_index_does_not_offer_up_motorhome_ranges() -> None:
    """Swift's nav block is global, so this index links every motorhome range too.

    A pattern matching `/<anything>/product/` would hand nine motorhome ranges to a
    caravan parser. This is the same global-nav trap `swift.py` guards against by
    interpolating its category.
    """
    index = fixture(INDEX)
    assert "/motorhomes/product/" in index
    assert all("/caravans/product/" in path for path in swift_caravan.find_range_page_paths(index))


def test_the_quick_guide_is_linked_from_the_index() -> None:
    assert swift_caravan.find_quick_guide_url(fixture(INDEX)) == (
        "https://www.swiftgroup.co.uk/media/jcelqit3/2027-swift-caravan-quick-guide.pdf"
    )


def test_the_guide_pattern_would_not_match_the_retired_brochure() -> None:
    """`2026_swift_caravan_brochure.pdf` is still live and still linked from `/brochures/`.

    Anchoring on `quick-guide` rather than on `.pdf` is what stops a run parsing last
    season's range and proposing it as current — silent stale data, worse than none.
    """
    stale = 'href="/media/rs5dz3ji/2026_swift_caravan_brochure.pdf"'
    assert swift_caravan.find_quick_guide_url(stale) is None


# --------------------------------------------------------------------------- #
# Parsing one range page
# --------------------------------------------------------------------------- #


def test_sprite_yields_its_four_layouts() -> None:
    assert [product.label for product in parsed(SPRITE)] == [
        "Sprite Alpine 4",
        "Sprite Alpine 4 DB",
        "Sprite Major 4 SB",
        "Sprite Major 4 EB",
    ]


def test_a_layout_carries_every_field_the_site_publishes() -> None:
    alpine = by_model(SPRITE, "Alpine 4")
    assert alpine.manufacturer_range == "Sprite"
    assert alpine.berths == 4
    assert alpine.rrp_pounds == 22585
    assert alpine.mtplm_kilograms == 1247
    assert alpine.mro_kilograms == 1102
    assert alpine.shipping_length_mm == 6450
    assert alpine.overall_width_mm == 2230
    assert alpine.headroom_mm == 1950
    assert alpine.twin_axle is False


def test_the_published_length_is_the_shipping_length() -> None:
    """The single most consequential mapping in this adapter.

    Swift publish one length and never say which it is. The 2026 brochure's labelled
    table gives the Alpine 4 an *Internal Length* of 4.74m against an *Overall Length* of
    6.45m, and FMLV holds it as `internal_length_mm=4740, shipping_length_mm=6450`. So
    6.45m is the overall figure. Reading it as the internal one would overstate every
    caravan's habitable space by about 1.7m while looking plausible on any one product.
    """
    alpine = by_model(SPRITE, "Alpine 4")
    assert alpine.shipping_length_mm == 6450
    caravan = swift_caravan.build_extracted(alpine, "https://example.test").caravan
    assert caravan.shipping_length_mm == 6450
    assert caravan.internal_length_mm is None


def test_the_grande_slug_splits_a_two_word_range_from_its_model() -> None:
    """`Conqueror Grande 560L` is range `Conqueror Grande` + model `560L`.

    Both halves matter: FMLV holds them exactly this way, and Challenger, Conqueror and
    their Grandes all share model numbers, so a bare `580` is three different caravans.
    """
    assert [(p.manufacturer_range, p.model) for p in parsed(CONQUEROR_GRANDE)] == [
        ("Conqueror Grande", "560L"),
        ("Conqueror Grande", "580"),
        ("Conqueror Grande", "645"),
        ("Conqueror Grande", "650L"),
    ]


def test_axle_type_is_read_per_layout_not_per_range() -> None:
    """Conqueror Grande mixes both, so a range-level assumption would be wrong twice."""
    axles = {p.model: p.twin_axle for p in parsed(CONQUEROR_GRANDE)}
    assert axles == {"560L": False, "580": False, "645": True, "650L": True}


def test_an_unrecognised_axle_value_understates_rather_than_inventing_an_axle() -> None:
    """False is also FMLV's default, so a new Swift wording leaves the field alone."""
    assert swift_caravan._TWIN_AXLE.search("Caravan - Twin axle")
    assert not swift_caravan._TWIN_AXLE.search("Caravan - Single axle")
    assert not swift_caravan._TWIN_AXLE.search("Caravan - Tri-axle bogie")


def test_headroom_comes_from_the_range_page_prose() -> None:
    """Stated as `1.95m (6'5") headroom` on all seven pages; FMLV holds 1950 on all 26."""
    assert swift_caravan.find_headroom_mm(fixture(SPRITE)) == 1950
    assert swift_caravan.find_headroom_mm(fixture(ELEGANCE_GRANDE)) == 1950
    assert all(product.headroom_mm == 1950 for product in parsed(CONQUEROR_GRANDE))


def test_a_page_with_no_headroom_prose_leaves_the_field_unset() -> None:
    """Narrated by `collect` rather than defaulted, so FMLV's own figure survives."""
    assert swift_caravan.find_headroom_mm("<html><body>no dimensions here</body></html>") is None


def test_the_width_comes_from_the_json_not_the_construction_prose() -> None:
    """The Sprite page says `Overall body width 2.25m` and it is wrong.

    Its own JSON, the quick guide and FMLV's baseline all say 2.23m for all four Sprites.
    The prose figure is the one Swift use for the Challenger — a CMS copy-paste — so the
    per-layout JSON is the only source read here.
    """
    assert "Overall body width 2.25m" in fixture(SPRITE)
    assert {product.overall_width_mm for product in parsed(SPRITE)} == {2230}


def test_the_optional_weight_plate_upgrade_is_never_the_mtplm() -> None:
    """It sits in the same object, right beside `weightMtplm`, and is a dealer option.

    `docs/adapters/README.md`: record the base figure, not the optioned variant. The
    Alpine 4's upgrade is 1300kg against a real MTPLM of 1247kg — close enough to look
    right and wrong enough to matter.
    """
    assert '"optionalWeightPlateUpgrade":"1300kg"' in fixture(SPRITE).replace(", ", ",")
    alpine = by_model(SPRITE, "Alpine 4")
    assert alpine.mtplm_kilograms == 1247
    caravan = swift_caravan.build_extracted(alpine, "https://example.test").caravan
    assert caravan.mtplm_kilograms == 1247


def test_a_title_that_cannot_be_split_is_reported_and_dropped() -> None:
    """Without both halves of the identity there is nothing to match a baseline on."""
    page = (
        '<script type="application/json" data-product-layouts-data>'
        '[{"id":1,"title":"Some Other Caravan","weightMtplm":"1500kg"}]</script>'
    )
    assert swift_caravan.parse_range_page(page, slug="swift-sprite") == []
    assert swift_caravan.unsplittable_titles(page, slug="swift-sprite") == ["Some Other Caravan"]


def test_a_dead_cms_node_yields_nothing_rather_than_raising() -> None:
    """Swift leave placeholder range pages live — `swift.py` hit three on the van side."""
    assert swift_caravan.parse_range_page("<html><body></body></html>", slug="swift-sprite") == []


# --------------------------------------------------------------------------- #
# The cross-document self-check
# --------------------------------------------------------------------------- #


def test_the_guide_holds_one_block_per_published_layout(
    guide: swift_caravan.GuideSpecs,
) -> None:
    assert guide.entry_count == PUBLISHED_LAYOUT_COUNT


def test_only_one_mtplm_repeats_across_the_whole_line_up(
    guide: swift_caravan.GuideSpecs,
) -> None:
    """Which is what makes MTPLM safe to key the guide on.

    Conqueror Grande 645 and 650L are both 1886kg, and both carry the same 160kg payload,
    so even the one collision cannot misattribute a figure.
    """
    repeated = {mtplm: entries for mtplm, entries in guide.by_mtplm.items() if len(entries) > 1}
    assert list(repeated) == [1886]
    assert len({entry.payload_kilograms for entry in repeated[1886]}) == 1


def test_the_guide_corroborates_payload_length_and_width(
    guide: swift_caravan.GuideSpecs,
) -> None:
    """A real check: the JSON has MTPLM and MRO but no payload, the guide the reverse."""
    for name in (SPRITE, CONQUEROR_GRANDE, ELEGANCE_GRANDE):
        for product in parsed(name):
            reconciles, reason = guide.check(product)
            assert reconciles, f"{product.label}: {reason}"
            assert "agrees" in reason, f"{product.label}: {reason}"


def test_a_contradicted_layout_fails_the_check(guide: swift_caravan.GuideSpecs) -> None:
    """A wrong MRO changes the derived payload, which the guide then disagrees with."""
    alpine = by_model(SPRITE, "Alpine 4")
    wrong = swift_caravan.SwiftCaravan(
        manufacturer_range=alpine.manufacturer_range,
        model=alpine.model,
        mtplm_kilograms=alpine.mtplm_kilograms,
        mro_kilograms=1002,  # 100kg light, so the payload comes out 245 against 145
        shipping_length_mm=alpine.shipping_length_mm,
        overall_width_mm=alpine.overall_width_mm,
    )
    reconciles, reason = guide.check(wrong)
    assert reconciles is False
    assert "245kg" in reason and "145kg" in reason


def test_a_layout_the_guide_says_nothing_about_is_kept(
    guide: swift_caravan.GuideSpecs,
) -> None:
    """Soft on silence, hard on contradiction — `swift.py`'s asymmetry, deliberately.

    One JSON object is one vehicle, so there is no join here to misalign; losing a real
    caravan over a gap in a marketing leaflet's coverage would be the worse error.
    """
    unlisted = swift_caravan.SwiftCaravan(
        manufacturer_range="Sprite",
        model="Alpine 6",
        mtplm_kilograms=1301,
        mro_kilograms=1150,
    )
    reconciles, reason = guide.check(unlisted)
    assert reconciles is True
    assert "not in the quick guide" in reason


def test_no_guide_at_all_leaves_every_layout_standing() -> None:
    """The guide is the self-check, not the product source."""
    empty = swift_caravan.GuideSpecs()
    reconciles, reason = empty.check(by_model(SPRITE, "Alpine 4"))
    assert reconciles is True
    assert "no quick guide" in reason


def test_every_guide_entry_is_accounted_for_by_the_three_captured_pages(
    guide: swift_caravan.GuideSpecs,
) -> None:
    """The full run is a bijection; these fixtures cover 12 of the 26.

    What this asserts is the *bookkeeping*: an MTPLM a range page claimed is marked
    matched, and the twelve here are exactly the twelve left un-matched by nothing else.
    """
    for name in (SPRITE, CONQUEROR_GRANDE, ELEGANCE_GRANDE):
        for product in parsed(name):
            guide.check(product)
    # 1886kg is claimed by two Conqueror Grandes but is one key, so 12 products -> 11 keys.
    assert len(guide.matched) == 11
    assert len(guide.unmatched()) == len(guide.by_mtplm) - 11


# --------------------------------------------------------------------------- #
# Building the product
# --------------------------------------------------------------------------- #


def built(name: str, model: str) -> Caravan:
    return swift_caravan.build_extracted(by_model(name, model), "https://example.test").caravan


def test_a_built_caravan_carries_the_fields_swift_publish() -> None:
    caravan = built(ELEGANCE_GRANDE, "835")
    assert caravan.manufacturer == "Swift Group Ltd"
    assert caravan.manufacturer_display_name == "Swift"
    assert caravan.manufacturer_range == "Elegance Grande"
    assert caravan.model == "835"
    assert caravan.berths == 4
    assert caravan.rrp_pounds == 51935
    assert caravan.mtplm_kilograms == 2123
    assert caravan.mro_kilograms == 1922
    assert caravan.shipping_length_mm == 7980
    assert caravan.overall_width_mm == 2450
    assert caravan.headroom_mm == 1950
    assert caravan.twin_axle is True
    assert caravan.body_type is CaravanBodyType.RIGID


def test_payload_is_derived_from_the_two_published_masses() -> None:
    """The requester's instruction, 4 September 2026, and `swift.py`'s own arithmetic.

    Swift publish MTPLM and MRO on every layout, and those two determine the payload —
    so leaving the column blank showed a reviewer a gap beside the figures that fill it.
    Same subtraction and same provenance wording `swift.py` uses for
    `mh_payload_kilograms`.
    """
    alpine = by_model(SPRITE, "Alpine 4")
    assert (alpine.mtplm_kilograms, alpine.mro_kilograms) == (1247, 1102)
    assert alpine.derived_payload_kilograms == 145
    caravan = swift_caravan.build_extracted(alpine, "https://example.test").caravan
    assert caravan.personal_effects_payload_kilograms == 145


def test_the_payload_provenance_cites_the_guide_as_well_as_the_arithmetic() -> None:
    """A published figure beside the subtraction, not arithmetic on its own."""
    alpine = by_model(SPRITE, "Alpine 4")
    extracted = swift_caravan.build_extracted(
        alpine, "https://example.test", payload_basis="quick guide agrees: Max Payload 145kg"
    )
    snippet = extracted.provenance["personal_effects_payload_kilograms"].snippet
    assert "derived as MTPLM - MRO (1247 - 1102)" in snippet
    assert "Max Payload 145kg" in snippet


def test_the_payload_is_still_emitted_with_no_guide_to_corroborate_it() -> None:
    """The guide is the corroboration, not the source — two masses are enough."""
    alpine = by_model(SPRITE, "Alpine 4")
    extracted = swift_caravan.build_extracted(alpine, "https://example.test")
    caravan = extracted.caravan
    assert caravan.personal_effects_payload_kilograms == 145
    snippet = extracted.provenance["personal_effects_payload_kilograms"].snippet
    assert "derived as MTPLM - MRO" in snippet


def test_the_derived_payload_is_a_total_on_the_elegance_grande() -> None:
    """The one caveat, and it is FMLV's bookkeeping rather than a parse fault.

    FMLV holds the 835 as 160kg personal effects plus 41kg optional equipment — the 201kg
    the guide prints. The adapter proposes the 201kg total, because Swift publish no split
    and it cannot apportion one, so accepting it leaves the out-of-scope 41kg in place and
    the row reading 242kg against 201kg of real capacity. That is caught rather than
    silent: `validation` compares those two figures and warns, naming the product.
    """
    elegance = by_model(ELEGANCE_GRANDE, "835")
    caravan = swift_caravan.build_extracted(elegance, "https://example.test").caravan
    assert caravan.personal_effects_payload_kilograms == 201
    assert caravan.derived_payload_kilograms == 201
    # The adapter never supplies the optional half — out of scope, and unknowable here.
    assert caravan.optional_equipment_payload_kilograms is None

    from src.product_model import validation

    split = caravan.model_copy(
        update={
            "personal_effects_payload_kilograms": 201,
            "optional_equipment_payload_kilograms": 41,
        }
    )
    codes = [issue.code for issue in validation.validate_caravan(split)]
    assert "payload_mismatch" in codes


def test_the_withdrawn_dimensions_are_left_for_fmlv_to_keep() -> None:
    """All three were in the retired brochure and are published nowhere for 2027.

    Leaving them unset makes each arrive as a `MissingField`, which shows a reviewer the
    baseline figure beside "nothing scraped" and leaves the stored value alone.
    """
    caravan = built(SPRITE, "Major 4 SB")
    assert caravan.internal_length_mm is None
    assert caravan.exterior_body_length_mm is None
    assert caravan.height_mm is None
    assert caravan.awning_length_mm is None
    # Payload is *not* in this list any more — it is derived from the two masses.
    assert caravan.personal_effects_payload_kilograms == 156


def test_a_sub_1250kg_caravan_is_still_rigid() -> None:
    """The micro rule needs the manufacturer's own naming *as well as* the weight.

    The Alpine 4 is 1247kg, under the threshold, and FMLV holds it as rigid. Swift market
    nothing as a micro — their one genuinely small vehicle, Basecamp at 1043kg, was held
    as rigid too and is discontinued for 2027. Weight alone would mislabel this.
    """
    alpine = by_model(SPRITE, "Alpine 4")
    assert alpine.mtplm_kilograms is not None
    assert alpine.mtplm_kilograms <= 1250
    assert built(SPRITE, "Alpine 4").body_type is CaravanBodyType.RIGID


def test_both_halves_of_the_identity_get_provenance() -> None:
    """`compare_fields` walks only fields with provenance, and the missing-field check
    fires only where nothing was found — so an unrecorded `model` is invisible to both.
    Each snippet says the two belong together, so a reviewer accepting one accepts both.
    """
    extracted = swift_caravan.build_extracted(
        by_model(CONQUEROR_GRANDE, "560L"), "https://example.test"
    )
    for field_name in ("manufacturer_range", "model"):
        assert field_name in extracted.provenance
        assert "one name" in extracted.provenance[field_name].snippet


def test_the_axle_provenance_quotes_swift_s_own_wording() -> None:
    """Two of these disagree with FMLV's baseline, so the evidence has to be visible."""
    extracted = swift_caravan.build_extracted(
        by_model(CONQUEROR_GRANDE, "580"), "https://example.test"
    )
    assert extracted.provenance["twin_axle"].snippet.endswith("Caravan - Single axle")


def test_body_type_provenance_says_it_is_asserted_not_scraped() -> None:
    extracted = swift_caravan.build_extracted(
        by_model(SPRITE, "Alpine 4"), "https://example.test"
    )
    assert "rigid" in extracted.provenance["body_type"].snippet
    assert "micro" in extracted.provenance["body_type"].snippet


def test_no_provenance_is_recorded_for_a_field_that_was_not_found() -> None:
    """A field is only real if it has provenance — `docs/adapters/README.md`."""
    bare = swift_caravan.SwiftCaravan(manufacturer_range="Sprite", model="Alpine 4")
    extracted = swift_caravan.build_extracted(bare, "https://example.test")
    # No masses, so no derived payload either — the subtraction has nothing to work on.
    assert set(extracted.provenance) == {
        "manufacturer_range",
        "model",
        "twin_axle",
        "body_type",
    }
