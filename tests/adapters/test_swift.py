"""Tests for the Swift adapter's pure parsing functions, against real page and PDF text.

The fixtures are Swift's own 2027 pages and quick guides, captured 2026-08-28 — see
`docs/adapters/swift.md`. Three shapes are exercised because all three bit during the
rewrite: the category index pages (which carry a *global* nav, so they link the other
category's ranges too), the range pages' embedded layout JSON, and the quick guides'
two different ways of printing a payload.

No network and no PDF parsing here; `fetch.pdf` is covered in `tests/fetch/test_pdf.py`.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.swift import (
    SwiftProduct,
    _reconciles,
    find_quick_guide_url,
    find_range_page_paths,
    parse_guide_payloads,
    parse_layouts_json,
    parse_range_page,
    range_and_model,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


MOTORHOMES_INDEX = _fixture("swift_motorhomes_index.html")
CAMPERVANS_INDEX = _fixture("swift_campervans_index.html")
KON_TIKI = _fixture("swift_kon_tiki_layouts.html")
TREKKER_VAN = _fixture("swift_trekker_campervan_layouts.html")
MERLIN = _fixture("swift_merlin_layouts.html")
MOTORHOME_GUIDE = _fixture("swift_motorhome_quick_guide.txt")
CAMPERVAN_GUIDE = _fixture("swift_campervan_quick_guide.txt")


# --------------------------------------------------------------------------- #
# The index pages
# --------------------------------------------------------------------------- #


def test_motorhome_index_lists_the_four_motorhome_ranges() -> None:
    paths = find_range_page_paths(MOTORHOMES_INDEX, "motorhomes")

    assert len(paths) == 4
    assert all(path.startswith("/motorhomes/product/") for path in paths)


def test_campervan_index_lists_the_five_campervan_range_paths() -> None:
    # Five linked, but only three carry data — the other two are dead `merlin` CMS
    # nodes, which `collect` drops on their HTTP status. See `find_range_page_paths`.
    paths = find_range_page_paths(CAMPERVANS_INDEX, "campervans")

    assert len(paths) == 5
    assert all(path.startswith("/campervans/product/") for path in paths)


def test_range_paths_are_scoped_to_their_own_category() -> None:
    """Swift's nav is global, so each index links the *other* category's ranges too.

    This is the bug the first live run of the rewrite hit: an unscoped pattern read all
    nine ranges from each index, emitting every product twice and — far worse — applying
    the motorhome `Trekker` -> `Trekker 500` correction to the campervan Trekker.
    """
    assert "/campervans/product/" in MOTORHOMES_INDEX  # the nav really is global
    assert "/motorhomes/product/" in CAMPERVANS_INDEX

    from_motorhomes = find_range_page_paths(MOTORHOMES_INDEX, "motorhomes")
    from_campervans = find_range_page_paths(CAMPERVANS_INDEX, "campervans")

    assert not any("campervans" in path for path in from_motorhomes)
    assert not any("motorhomes" in path for path in from_campervans)


def test_quick_guide_is_found_on_each_index() -> None:
    assert find_quick_guide_url(MOTORHOMES_INDEX) == (
        "https://www.swiftgroup.co.uk/media/0yxdkzhv/2027-swift-motorhome-quick-guide.pdf"
    )
    assert find_quick_guide_url(CAMPERVANS_INDEX) == (
        "https://www.swiftgroup.co.uk/media/mmsmraxk/2027-swift-campervan-quick-guide.pdf"
    )


def test_the_superseded_2026_brochure_is_never_matched_as_a_quick_guide() -> None:
    """The old full brochure is still live and still linked from `/brochures/`.

    Matching it would propose last season's range as current — a silent, plausible,
    entirely wrong diff. This is the single most important negative test in the file.
    """
    stale = (
        '<a href="/media/noeb4jei/2026_swift_motorhome_brochure.pdf">Brochure</a>'
        '<a href="/media/hztd1bki/2026_swift_campervan_brochure.pdf">Brochure</a>'
    )

    assert find_quick_guide_url(stale) is None


# --------------------------------------------------------------------------- #
# The range pages
# --------------------------------------------------------------------------- #


def test_kon_tiki_layouts_are_read_from_the_json_block() -> None:
    # Swift's own quick guide says the Kon-Tiki has "7 Layouts".
    layouts = parse_layouts_json(KON_TIKI)

    assert len(layouts) == 7
    assert [layout["title"] for layout in layouts][:2] == ["Kon-Tiki 774", "Kon-Tiki 784"]


def test_layout_json_is_identified_by_its_attribute_not_by_its_shape() -> None:
    """The block is found by `data-product-layouts-data`, as Swift's own JS finds it.

    The fixture keeps the preceding card markup — which carries prices, berths and seats
    as ordinary HTML — so a pattern that wandered into it, or stopped short of the real
    array, shows up here as a wrong count.
    """
    assert "product-layouts__card" in KON_TIKI  # the card markup really is present

    layouts = parse_layouts_json(KON_TIKI)

    assert len(layouts) == 7  # not a partial or duplicated read
    assert all("weightMtplm" in layout for layout in layouts)


def test_a_layouts_block_under_a_different_attribute_is_ignored() -> None:
    # Guards against loosening the anchor to any JSON array on the page.
    other = '<script type="application/json" data-gallery-data>[{"id":1,"title":"X 1"}]</script>'

    assert parse_layouts_json(other) == []


def test_a_page_without_a_layouts_block_yields_nothing() -> None:
    assert parse_layouts_json("<html><body>no layouts here</body></html>") == []


def test_kon_tiki_products_carry_every_field_the_site_publishes() -> None:
    products = {p.model: p for p in parse_range_page(KON_TIKI, slug="swift-kon-tiki", index_path="motorhomes")}

    assert set(products) == {"774", "784", "794", "874", "894", "894 (with drop down bed)", "740"}

    product = products["774"]
    assert product.range_label == "Kon-Tiki"
    assert product.berths == 6
    assert product.mh_passenger_seats_inc_driver == 5
    assert product.mh_length_mm == 8220
    assert product.mh_width_mm == 2390
    assert product.mtplm_kilograms == 4500
    assert product.mro_kilograms == 3638
    assert product.mh_payload_kilograms == 862  # derived: 4500 - 3638
    assert product.rrp_pounds == 114395


def test_height_is_never_emitted_because_swift_no_longer_publishes_one() -> None:
    """Neither the JSON nor the quick guide carries a height for 2027.

    `SwiftProduct` deliberately has no height field at all, so there is nothing to
    accidentally fill from a stale source — the value arrives at review as a
    `MissingField` against the baseline instead. See the module docstring.
    """
    assert not hasattr(SwiftProduct("Kon-Tiki", "774"), "mh_height_mm")

    # The JSON has no height key either.
    assert all("height" not in key.lower() for key in parse_layouts_json(KON_TIKI)[0])

    # The guides mention "height" only in prose ("full height GRP rear panel", "height
    # adjustable electric drop-down bed") — never as a spec row beside Length and Width.
    for guide in (MOTORHOME_GUIDE, CAMPERVAN_GUIDE):
        assert "Length" in guide and "Width" in guide
        assert "\nHeight" not in guide


# --------------------------------------------------------------------------- #
# Range and model splitting — the Trekker collision
# --------------------------------------------------------------------------- #


def test_motorhome_trekker_is_renamed_to_the_range_fmlv_holds() -> None:
    """Swift sells a `Trekker` coachbuilt range *and* a `Trekker` campervan range.

    FMLV distinguishes them as `Trekker 500` and `Trekker`, confirmed against the real
    export. Emitting the site's bare "Trekker" for both would merge two unrelated
    ranges.
    """
    vans = parse_range_page(TREKKER_VAN, slug="swift-trekker", index_path="campervans")

    assert {(p.range_label, p.model) for p in vans} == {("Trekker", "X"), ("Trekker", "XF")}


def test_the_same_page_read_as_a_motorhome_index_would_be_renamed() -> None:
    # Guards the correction itself: keyed on (index path, site range name).
    as_motorhomes = parse_range_page(TREKKER_VAN, slug="swift-trekker", index_path="motorhomes")

    assert {p.range_label for p in as_motorhomes} == {"Trekker 500"}


def test_model_names_are_not_always_numbers() -> None:
    """`Trekker X` and `Trekker XF` share the prefix `Trekker X`.

    So the model cannot be found by taking the common prefix of the titles on a page —
    that would make the second model `F`. The page slug supplies the boundary instead.
    """
    assert range_and_model("Trekker X", "swift-trekker") == ("Trekker", "X")
    assert range_and_model("Trekker XF", "swift-trekker") == ("Trekker", "XF")


def test_range_name_keeps_swifts_own_hyphenation() -> None:
    # The slug flattens the hyphen; the range must not.
    assert range_and_model("Kon-Tiki 774", "swift-kon-tiki") == ("Kon-Tiki", "774")


def test_a_title_that_does_not_match_its_slug_is_rejected() -> None:
    # Better to skip than to emit a vehicle under the wrong range.
    assert range_and_model("Voyager 505", "swift-kon-tiki") is None
    assert range_and_model("Kon-Tiki", "swift-kon-tiki") is None  # no model half


def test_merlin_models_keep_their_berth_variant_digit() -> None:
    """Merlin's five floorplans are sold as nine products.

    The leading digit is the variant (`112` 2-berth against `212` 4-berth) and the
    trailing pair is the floorplan, so the whole code is the model.
    """
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    assert len(products) == 9
    assert products["112"].berths == 2
    assert products["212"].berths == 4
    assert products["112"].mh_length_mm == products["212"].mh_length_mm == 5410


# --------------------------------------------------------------------------- #
# The quick guides, and the cross-document self-check
# --------------------------------------------------------------------------- #


def test_motorhome_guide_yields_one_payload_per_layout() -> None:
    payloads = parse_guide_payloads(MOTORHOME_GUIDE)

    total = sum(sum(group.values()) for group in payloads.by_floorplan.values())
    assert total + sum(payloads.loose.values()) == 22  # 22 motorhome products


def test_campervan_guide_reads_both_printed_forms() -> None:
    """Nine of the seventeen campervans appear only as `244 Max Payload / 470kg`.

    Reading full blocks alone would leave a third of the range unchecked.
    """
    payloads = parse_guide_payloads(CAMPERVAN_GUIDE)

    blocks = sum(sum(group.values()) for group in payloads.by_floorplan.values())
    assert blocks == 12
    assert sum(payloads.loose.values()) == 5
    assert blocks + sum(payloads.loose.values()) == 17


def test_dual_weight_plates_are_paired_positionally() -> None:
    """The Escape prints `270kg | 400kg` against `3500kg | 3700kg`.

    That is how the guide encodes what the site sells as separate 2-berth and 4-berth
    products, and pairing them the wrong way round attaches each payload to the other's
    weight plate.
    """
    payloads = parse_guide_payloads(MOTORHOME_GUIDE)

    assert 270 in payloads.by_floorplan[(7840, 3500)]
    assert 400 in payloads.by_floorplan[(7840, 3700)]


def test_every_scraped_payload_reconciles_against_the_guide() -> None:
    """The check that matters: 39 figures published, 39 products, all agreeing.

    The JSON publishes MRO and no payload; the guide publishes payload and no MRO. So
    `payload == MTPLM - MRO` is a genuine cross-document check rather than an
    arithmetic tautology.
    """
    guide = parse_guide_payloads(CAMPERVAN_GUIDE)
    products = [
        *parse_range_page(TREKKER_VAN, slug="swift-trekker", index_path="campervans"),
        *parse_range_page(MERLIN, slug="merlin", index_path="campervans"),
    ]

    for product in products:
        ok, basis = _reconciles(product, guide)
        assert ok, f"{product.label}: {basis}"
        assert basis.startswith("quick guide prints"), f"{product.label} went unchecked"


def test_a_contradicted_payload_is_rejected() -> None:
    """A wrong MRO must not survive the check.

    This is what the self-check exists for — Swift mis-stating a figure, since the JSON
    has no join to misalign.
    """
    guide = parse_guide_payloads(MOTORHOME_GUIDE)
    wrong = SwiftProduct(
        range_label="Kon-Tiki",
        model="740",
        mh_length_mm=6990,
        mtplm_kilograms=4500,
        mro_kilograms=3000,  # real MRO is 3280, so payload comes out 1500 not 1220
    )

    ok, basis = _reconciles(wrong, guide)

    assert not ok
    assert "1220" in basis


def test_a_floorplan_the_guide_does_not_cover_is_allowed_but_flagged() -> None:
    """A gap in the guide warns; only a contradiction drops.

    The brochure version dropped hard because its two tables were joined and a misjoin
    was the risk. There is no join here, so losing a real vehicle over a marketing
    leaflet's coverage would be the worse error.
    """
    guide = parse_guide_payloads(MOTORHOME_GUIDE)
    unlisted = SwiftProduct(
        range_label="Kon-Tiki",
        model="999",
        mh_length_mm=12345,
        mtplm_kilograms=9999,
        mro_kilograms=8888,
    )

    ok, basis = _reconciles(unlisted, guide)

    assert ok
    assert basis.startswith("quick guide prints no")


def test_a_product_with_no_weights_has_nothing_to_contradict() -> None:
    ok, basis = _reconciles(SwiftProduct("Merlin", "112"), parse_guide_payloads(CAMPERVAN_GUIDE))

    assert ok
    assert basis == "no weights to check"


# --------------------------------------------------------------------------- #
# Field parsing traps
# --------------------------------------------------------------------------- #


def test_footnote_marks_on_weights_are_tolerated() -> None:
    """Swift annotates figures with `*` and `**`, on MTPLM as well as payload."""
    products = {p.model: p for p in parse_range_page(KON_TIKI, slug="swift-kon-tiki", index_path="motorhomes")}

    assert all(product.mtplm_kilograms is not None for product in products.values())
    assert all(product.mro_kilograms is not None for product in products.values())


def test_price_is_the_on_the_road_figure_the_site_publishes() -> None:
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    # Merlin 112 is Swift's cheapest 2027 leisure vehicle.
    assert products["112"].rrp_pounds == 64685
    assert all(product.rrp_pounds is not None for product in products.values())
