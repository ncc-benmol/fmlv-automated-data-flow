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
    HIGH_TOP_ABOVE_MM,
    SwiftProduct,
    _MARKUP,
    _reconciles,
    find_base_vehicle,
    find_body_type,
    find_elevating_roof_models,
    find_family_evidence,
    find_quick_guide_url,
    find_range_page_paths,
    parse_guide_payloads,
    parse_layouts_json,
    parse_range_page,
    range_and_model,
)
from src.product_model.enums import BodyType

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


def test_no_swift_document_publishes_a_height_for_2027() -> None:
    """The premise the whole height arrangement rests on.

    Nothing is scraped into `mh_height_mm`; the only values that reach it come from
    `_MANUALLY_SOURCED_HEIGHT_MM`. If this test ever fails, Swift have started publishing
    heights again and that constant should be retired in favour of the real thing.
    """
    # No height key in the layout JSON, on any range.
    for page in (KON_TIKI, MERLIN, TREKKER_VAN):
        for layout in parse_layouts_json(page):
            assert all("height" not in key.lower() for key in layout)

    # The guides mention "height" only in prose ("full height GRP rear panel", "height
    # adjustable electric drop-down bed") — never as a spec row beside Length and Width.
    for guide in (MOTORHOME_GUIDE, CAMPERVAN_GUIDE):
        assert "Length" in guide and "Width" in guide
        assert "\nHeight" not in guide


def test_a_range_with_no_sheet_figure_emits_no_height_at_all() -> None:
    """For the 30 non-Merlin products the field must stay unset.

    That is what routes it to review as a flagged no-op against the baseline, preserving
    the stored figure — the carry-over the requester asked for on 2026-08-28.
    """
    products = parse_range_page(KON_TIKI, slug="swift-kon-tiki", index_path="motorhomes")

    assert products  # guard against the assertion below passing on an empty list
    assert all(product.mh_height_mm is None for product in products)


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


def test_base_vehicle_is_read_from_each_range_page() -> None:
    """Swift name the chassis once per range, and every layout in it is built on that.

    Reading it on all seven live ranges reproduces FMLV's own Ford 17 / Fiat 14 split
    across all 31 baseline products, which is what makes it safe to emit.
    """
    assert find_base_vehicle(KON_TIKI) == "Fiat"  # "Fiat chassis cab in Black Metallic"
    assert find_base_vehicle(MERLIN) == "Fiat"  # "Fiat Ducato panel van"
    assert find_base_vehicle(TREKKER_VAN) == "Ford"  # "Ford Transit panel van"


def test_base_vehicle_needs_the_make_and_the_body_phrase_together() -> None:
    """The Carrera page titles itself "Swift Carrera panel van" — with no make in it.

    Anchoring on `panel van` alone lands on that heading. Two words are allowed between
    the make and the phrase so `Transit Skeletal` still passes.
    """
    assert find_base_vehicle("<h1>Award-winning Swift Carrera panel van, 2026</h1>") is None
    assert find_base_vehicle("<li>Ford Transit Skeletal chassis cab in Grey</li>") == "Ford"
    assert find_base_vehicle("<p>no chassis named here</p>") is None


def test_merlin_heights_come_from_the_supplied_sheet_and_only_where_supplied() -> None:
    """Swift publish no height for 2027; six Merlins have one from a spec sheet.

    Merlin's products are all new, so the flagged-no-op route that preserves a height for
    an existing product has nothing to preserve — without this they would stay blank on
    every run. The three not on the sheet stay blank rather than being inferred.
    """
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    assert {m: p.mh_height_mm for m, p in products.items()} == {
        "144": 2720, "164": 2720, "174": 2720,
        "244": 2790, "264": 2790, "274": 2790,
        "112": None, "122": None, "212": None,
    }


def test_no_other_range_gets_a_hand_sourced_height() -> None:
    # The constant is keyed on (range, model), so a shared layout number must not leak.
    for page, slug, index in (
        (KON_TIKI, "swift-kon-tiki", "motorhomes"),
        (TREKKER_VAN, "swift-trekker", "campervans"),
    ):
        assert all(p.mh_height_mm is None for p in parse_range_page(page, slug=slug, index_path=index))


# --------------------------------------------------------------------------- #
# Body type
# --------------------------------------------------------------------------- #


def test_every_coachbuilt_range_is_low_profile() -> None:
    """All four 2027 motorhome ranges state `low line` in their construction list."""
    products = parse_range_page(KON_TIKI, slug="swift-kon-tiki", index_path="motorhomes")

    assert products
    assert all(p.body_type is BodyType.COACH_BUILT_LOW_PROFILE for p in products)


def test_over_cab_storage_is_not_an_over_cab_bed() -> None:
    """The trap that would mislabel two low-profile ranges.

    The Kon-Tiki page says "Moulded over-cab storage compartments" and the Trekker 500
    says "Zip pocket storage on the overcab side lockers" — both are lockers in the
    low-profile pod. Swift's extra berths come from a drop-down bed over the *front
    lounge*. A keyword search for "over cab" classifies both ranges as Luton.
    """
    # The real Kon-Tiki page carries the trap wording, and still comes out low profile.
    assert "over-cab storage" in _MARKUP.sub(" ", KON_TIKI).lower()
    assert all(
        p.body_type is BodyType.COACH_BUILT_LOW_PROFILE
        for p in parse_range_page(KON_TIKI, slug="swift-kon-tiki", index_path="motorhomes")
    )

    storage = "<li>Moulded over-cab storage compartments with Skyview sunroof</li><li>low line pod</li>"
    assert find_body_type(
        storage, index_path="motorhomes", height_mm=None, model="774", elevating=frozenset()
    ) is BodyType.COACH_BUILT_LOW_PROFILE

    lounge = "<li>Height adjustable electric drop-down bed over front lounge (505)</li><li>low line pod</li>"
    assert find_body_type(
        lounge, index_path="motorhomes", height_mm=None, model="505", elevating=frozenset()
    ) is BodyType.COACH_BUILT_LOW_PROFILE

    # A real Luton must still be recognised, so the distinction is not just "always low".
    luton = "<li>Over-cab double bed</li><li>low line pod</li>"
    assert find_body_type(
        luton, index_path="motorhomes", height_mm=None, model="475", elevating=frozenset()
    ) is BodyType.COACH_BUILT_OVER_CAB_BED


def test_a_range_stating_no_profile_is_left_unset() -> None:
    # What should happen the day Swift add an A-class, rather than a silent "low profile".
    assert find_body_type(
        "<li>Some new construction</li>",
        index_path="motorhomes", height_mm=None, model="900", elevating=frozenset(),
    ) is None


def test_elevating_roof_models_are_read_from_the_page() -> None:
    """Standard fitment, restricted by model, stated in a parenthetical."""
    assert find_elevating_roof_models(MERLIN) == frozenset({"212", "244", "264", "274"})
    assert find_elevating_roof_models(TREKKER_VAN) == frozenset({"X"})

    # The Carrera's phrasing, which uses "only" rather than a list.
    carrera = "<li>Elevating roof in Black with Mini-Heki skylight (244 only)</li>"
    assert find_elevating_roof_models(carrera) == frozenset({"244"})


def test_a_range_with_no_elevating_roof_yields_an_empty_set() -> None:
    assert find_elevating_roof_models("<li>Fixed high top roof</li>") == frozenset()


def test_merlin_body_types_split_on_the_elevating_roof() -> None:
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    high = BodyType.CAMPERVAN_HIGH_TOP
    elevating = BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF
    assert {m: p.body_type for m, p in products.items()} == {
        "112": high, "122": high, "144": high, "164": high, "174": high,
        "212": elevating, "244": elevating, "264": elevating, "274": elevating,
    }


def test_merlins_without_their_own_height_still_get_a_roof_class() -> None:
    """112, 122 and 212 have no height, but a range is one bodyshell.

    The shortest published height in the range decides the roof class for all of it.
    Their own `mh_height_mm` stays empty — this settles the body type, not the figure.
    """
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    for model in ("112", "122", "212"):
        assert products[model].mh_height_mm is None
        assert products[model].body_type is not None


def test_a_campervan_range_with_no_height_gets_no_body_type() -> None:
    """The Carrera and Trekker vans, whose heights Swift do not publish.

    The high-top half of the 2x2 is unanswerable without one, so the field is left unset
    and FMLV's existing value is preserved rather than guessed over.
    """
    products = parse_range_page(TREKKER_VAN, slug="swift-trekker", index_path="campervans")

    assert products
    assert all(p.body_type is None for p in products)


def test_the_roof_class_uses_the_shared_2300mm_threshold_not_2680() -> None:
    """`HIGH_TOP_ABOVE_MM` is 2300, the same figure the other four adapters use.

    The 2680mm in `docs/adapters/README.md` describes what an extended high top
    characteristically measures; it is not the cut-off, and the README says so — Elddis's
    2610mm Boxer is a high top. This adapter briefly used 2680 and would have called a
    2610mm van a plain campervan.
    """
    assert HIGH_TOP_ABOVE_MM == 2300

    def roof(height: int, *, pop: bool = False) -> BodyType | None:
        return find_body_type(
            "",
            index_path="campervans",
            height_mm=height,
            model="A",
            elevating=frozenset({"A"}) if pop else frozenset(),
        )

    assert roof(2050) is BodyType.CAMPERVAN  # FMLV's tallest standard-height van
    assert roof(2300) is BodyType.CAMPERVAN  # strictly above, as auto_trail has it
    assert roof(2301) is BodyType.CAMPERVAN_HIGH_TOP
    assert roof(2610) is BodyType.CAMPERVAN_HIGH_TOP  # the Elddis case 2680 would fail
    assert roof(2050, pop=True) is BodyType.CAMPERVAN_ELEVATING_ROOF
    assert roof(2720, pop=True) is BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF


def test_swift_publishes_no_roof_wording_to_fall_back_on() -> None:
    """Why the Carrera and Trekker vans get no body type at all.

    Some manufacturers state a roof class in words (Bailey publishes an `H3` code), which
    would settle the class without a height. Swift publish nothing of the sort on any
    campervan page — so when the height is missing there is no second route, and the
    field is left unset rather than guessed.
    """
    for page in (MERLIN, TREKKER_VAN):
        text = _MARKUP.sub(" ", page).lower()
        for wording in ("high top", "high-top", "raised roof", "extended roof", "roof height"):
            assert wording not in text


def test_price_is_the_on_the_road_figure_the_site_publishes() -> None:
    products = {p.model: p for p in parse_range_page(MERLIN, slug="merlin", index_path="campervans")}

    # Merlin 112 is Swift's cheapest 2027 leisure vehicle.
    assert products["112"].rrp_pounds == 64685
    assert all(product.rrp_pounds is not None for product in products.values())


def test_family_evidence_quotes_swifts_own_wording() -> None:
    """Shown to a reviewer beside the source link when the body type is undetermined."""
    assert find_family_evidence(MERLIN) == (
        "Fiat Ducato panel van with body coloured grille and standard black front bumper"
    )
    assert find_family_evidence(TREKKER_VAN) == "Ford Transit panel van in Grey Matter"
    assert find_family_evidence(KON_TIKI) == (
        "Fiat chassis cab in Black Metallic, with body coloured grille and bumper"
    )


def test_the_quote_stops_at_its_own_element() -> None:
    """Flattening the page runs one feature bullet into the next.

    The Trekker's chassis bullet is followed immediately by its elevating-roof bullet;
    a quote taken from flattened text ends up saying "...Grey Matter Elevating roof in
    body colour (Trekker X) Fr".
    """
    quote = find_family_evidence(TREKKER_VAN)

    assert quote is not None
    assert "Elevating roof" not in quote


def test_a_page_naming_no_chassis_yields_no_quote() -> None:
    assert find_family_evidence("<li>Nothing about the base vehicle here</li>") is None


def test_an_undetermined_body_type_still_records_provenance() -> None:
    """So the field reaches the reviewer with a link and a quote, not as silence.

    The Trekker campervans have no published height, so their type cannot be settled —
    but Swift plainly call them panel vans, and that is what a reviewer needs to see.
    """
    from src.adapters.swift import _build_extracted_motorhome

    product = next(
        p for p in parse_range_page(TREKKER_VAN, slug="swift-trekker", index_path="campervans")
    )
    assert product.body_type is None  # the premise of this test

    extracted = _build_extracted_motorhome(
        product, "https://www.swiftgroup.co.uk/campervans/product/63872/swift-trekker/",
        payload_basis="checked",
    )

    provenance = extracted.provenance["body_type"]
    assert provenance.source_url.endswith("/swift-trekker/")
    assert "campervan" in provenance.snippet
    assert "Ford Transit panel van in Grey Matter" in provenance.snippet
    assert "four campervan" in provenance.snippet
