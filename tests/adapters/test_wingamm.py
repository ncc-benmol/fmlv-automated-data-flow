"""Wingamm's parsing functions, against real captured documents and pages.

No network and no PDF parsing here — `tests/fetch/test_pdf.py` covers extraction, and the
`*_catalog_text.txt` fixtures are what it produces. Each fixture is cut down to the pages
or the block that matter, and every one of them broke the parser while it was being
written:

* the five catalogues, because no two of them name the weights the same way;
* the 610 GL page, which carries the Technical info block twice with two lengths;
* the City Pro page, which labels the chassis `Tractor`, publishes mass in running order
  where the others publish total mass, and puts some values outside the span holding
  their own label;
* the Brownie page, whose block has no chassis row under the name the Oasi pages use;
* the download area, one of whose rows has a title and no readable download link.

See `docs/adapters/wingamm.md`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters import wingamm
from src.adapters.wingamm import WingammPage, WingammProduct, WingammSpec
from src.product_model.enums import BodyType
from src.product_model.model import Motorhome

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def download_area() -> str:
    return _text("wingamm_download_area.html")


@pytest.fixture(scope="module")
def specs() -> dict[str, WingammSpec]:
    return {
        label: wingamm.parse_spec(_text(f"wingamm_{name}_catalog_text.txt"))
        for label, name in (
            ("Oasi 540.1", "oasi_540"),
            ("Oasi 610", "oasi_610"),
            ("Oasi 690", "oasi_690"),
            ("Brownie", "brownie"),
            ("City Pro", "citypro"),
        )
    }


# --------------------------------------------------------------------------- #
# The declared tables
# --------------------------------------------------------------------------- #


def test_eight_layouts_in_three_ranges() -> None:
    """Wingamm's roster: six Oasi layouts, Brownie and City Pro.

    The number the first real run was checked against. The index's own prose claims "3
    models in 5 variants", which is stale by one — six Oasi layouts have live pages and
    catalogue prices, and FMLV holds all six.
    """
    layouts = [layout for document in wingamm._DOCUMENTS for layout in document.layouts]
    assert len(layouts) == 8
    # The ranges Wingamm actually sell, per the requester: Brownie, City Pro and Oasi.
    # Brownie's is the one that cannot be written back — see the identity tests below.
    assert {
        document.intended_range or document.fmlv_range for document in wingamm._DOCUMENTS
    } == {"Oasi", "Brownie", "City Pro"}


def test_range_labels_are_unique() -> None:
    """`cli.resolve_ranges` keys `--range` on the label and would collapse duplicates.

    Three documents share one FMLV range, so the label has to be the *document* and
    `fmlv_range` a separate field. Were both "Oasi", `--range Oasi` would silently
    select whichever document came last.
    """
    labels = [label for _key, label in wingamm.DEFAULT_RANGES]
    assert len(labels) == len(set(labels))


def test_model_strings_are_the_ones_fmlv_holds() -> None:
    """Verbatim from the export, spacing included — see `docs/adapters/wingamm.md`."""
    models = {model for document in wingamm._DOCUMENTS for _slug, model in document.layouts}
    assert models == {"540", "610GL", "610M", "610ST", "690G", "690 TWINS", "Brownie", "City Pro"}


def test_city_pro_proposes_no_body_type() -> None:
    """FMLV's `campervan_high_top` is left alone; every other layout is low profile."""
    by_label = {document.label: document for document in wingamm._DOCUMENTS}
    assert by_label["City Pro"].body_type is None
    assert by_label["Oasi 610"].body_type is BodyType.COACH_BUILT_LOW_PROFILE
    assert by_label["Brownie"].body_type is BodyType.COACH_BUILT_LOW_PROFILE


# --------------------------------------------------------------------------- #
# The download area
# --------------------------------------------------------------------------- #


def test_parse_download_area_finds_every_readable_document(download_area: str) -> None:
    documents = wingamm.parse_download_area(download_area)
    assert set(documents) == {
        "1OASI5401CATALOGANDPRICELIST",
        "2OASI610CATALOGANDPRICELIST",
        "3OASI690CATALOGANDPRICELIST",
        "BROWNIECATALOGUE",
        "CITYPROCATALOGUE",
        "ROOKIE35PRICELIST",
        "ROOKIELPRICELIST",
        "ROOKIELCATALOGUE",
    }


def test_download_urls_drop_the_cache_buster(download_area: str) -> None:
    """`&refresh=` changes on every render, so keeping it would re-fetch 13MB each run."""
    documents = wingamm.parse_download_area(download_area)
    assert documents["2OASI610CATALOGANDPRICELIST"] == (
        "https://www.wingamm.com/en/download/oasi610-catalog-en/?wpdmdl=90170"
    )
    assert all("refresh" not in url for url in documents.values())


def test_one_download_row_has_no_readable_link(download_area: str) -> None:
    """The logo and media kit. Counted so a *catalogue* row changing shape is reported."""
    assert wingamm.count_download_rows(download_area) == 9
    assert len(wingamm.parse_download_area(download_area)) == 8


@pytest.mark.parametrize(
    ("title_key", "expected_slug"),
    [
        ("OASI5401", "oasi540-1-catalog"),
        ("OASI610", "oasi610-catalog-en"),
        ("OASI690", "oasi-690-catalog"),
        ("BROWNIE", "brownie-catalogo-3"),
        ("CITYPRO", "citypro-catalogo-3"),
    ],
)
def test_each_document_key_matches_exactly_one_title(
    download_area: str, title_key: str, expected_slug: str
) -> None:
    url, matched = wingamm.document_url(wingamm.parse_download_area(download_area), title_key)
    assert len(matched) == 1
    assert url is not None
    assert expected_slug in url


def test_an_ambiguous_document_key_yields_no_url() -> None:
    """A future `OASI 610 XL CATALOG` beside the 610's would make `OASI610` ambiguous.

    Guessing between them would attach one range's weights to another's layouts, so the
    caller is given nothing and narrates a skip.
    """
    documents = {
        "2OASI610CATALOGANDPRICELIST": "https://example.com/a",
        "4OASI610XLCATALOGANDPRICELIST": "https://example.com/b",
    }
    url, matched = wingamm.document_url(documents, "OASI610")
    assert url is None
    assert len(matched) == 2


# --------------------------------------------------------------------------- #
# The roster
# --------------------------------------------------------------------------- #


def test_parse_roster_finds_every_model_page() -> None:
    roster = wingamm.parse_roster(_text("wingamm_models_index.html"))
    assert roster == [
        "oasi-540",
        "oasi-610-gl",
        "oasi-610-st",
        "oasi-610m",
        "oasi-690-twins",
        "oasi-690-garage",
        "brownie",
        "city-pro",
        "rookie",
        "rookie-l",
    ]


def test_the_whole_roster_is_accounted_for() -> None:
    """Nothing on the index is unexplained: eight collected, two caravans excluded."""
    assert wingamm.unmapped_slugs(wingamm.parse_roster(_text("wingamm_models_index.html"))) == []


def test_baseline_scope_is_decided_by_model_not_range() -> None:
    """A `--range` run's selectors are documents, and two ranges are being renamed.

    Run #32 scoped `--range "Oasi 690"` to zero baseline rows and proposed both products
    as new, because `cli.baseline_scope`'s default matches the selector against
    `manufacturer_range` and the selector is `Oasi 690` against a range of `Oasi`.
    """
    def scope(motorhome: Motorhome, labels: set[str]) -> bool:
        return wingamm.baseline_in_scope(motorhome, labels)

    assert scope(Motorhome(manufacturer_range="Oasi", model="690G"), {"Oasi 690"})
    assert scope(Motorhome(manufacturer_range="Oasi", model="690 TWINS"), {"Oasi 690"})
    assert not scope(Motorhome(manufacturer_range="Oasi", model="610GL"), {"Oasi 690"})
    # The archived 2024 row belongs to no current layout.
    assert not scope(Motorhome(manufacturer_range="Oasi", model="690 GC"), {"Oasi 690"})


def test_a_renamed_products_baseline_row_stays_in_scope() -> None:
    """City Pro's row is still filed under `Campervan`, and must not be missed.

    Scoping on the range column would have proposed a duplicate of a product FMLV
    already holds — the "too narrow" half of `cli.baseline_scope`'s warning.
    """
    assert wingamm.baseline_in_scope(
        Motorhome(manufacturer_range="Campervan", model="City Pro"), {"City Pro"}
    )
    assert wingamm.baseline_in_scope(
        Motorhome(manufacturer_range="Coach Built low profile", model="Brownie"), {"Brownie"}
    )


def test_a_new_layout_is_reported_rather_than_ignored() -> None:
    assert wingamm.unmapped_slugs(["oasi-540", "oasi-750-xl", "rookie"]) == ["oasi-750-xl"]


def test_the_610m_card_is_found_despite_being_titled_610_gl() -> None:
    """The index titles the 610 M card "Oasi 610 GL", so only the href identifies it.

    Two cards therefore *look* like the GL and none like the M. The roster is taken from
    links for exactly this reason.
    """
    index = _text("wingamm_models_index.html")
    assert "oasi-610m" in wingamm.parse_roster(index)
    assert index.count("Oasi 610 GL") > index.count("Oasi 610 M")


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3.500", 3500),  # Italian thousands separator
        ("3,500", 3500),  # and the English one, on the model pages
        ("2240", 2240),  # the 690 catalogue drops the separator entirely
        ("6.103", 6103),
        ("13,9", None),  # a turning radius, not an integer
        ("540.1", None),  # a model name
        ("", None),
    ],
)
def test_integer_only_strips_a_genuine_thousands_separator(raw: str, expected: int | None) -> None:
    assert wingamm._integer(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [("3+1", 3), ("3 + 1", 3), ("4", 4), ("2", 2)])
def test_leading_int_takes_the_standard_figure(raw: str, expected: int) -> None:
    """The base-vehicle rule: the 540.1's `3+1` is 3 berths, the +1 being an option."""
    assert wingamm._leading_int(raw) == expected


# --------------------------------------------------------------------------- #
# Catalogue technical blocks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("label", "length", "width", "height", "mtplm", "mro", "payload"),
    [
        # Every figure here is also what FMLV already holds, which is how the survey
        # established that FMLV's data came from these documents and not the website.
        ("Oasi 540.1", 5420, 2240, 3030, 3500, 2845, 655),
        ("Oasi 610", 6103, 2240, 3030, 3500, 3047, 453),
        ("Oasi 690", 6920, 2240, 3030, 3500, 3150, 350),
        ("Brownie", 5890, 2190, 2750, 3500, 2747, 753),
        ("City Pro", 5990, 2050, 2770, 3500, 2888, 612),
    ],
)
def test_every_catalogue_yields_its_dimensions_and_weights(
    specs: dict[str, WingammSpec],
    label: str,
    length: int,
    width: int,
    height: int,
    mtplm: int,
    mro: int,
    payload: int,
) -> None:
    spec = specs[label]
    assert (spec.mh_length_mm, spec.mh_width_mm, spec.mh_height_mm) == (length, width, height)
    assert (spec.mtplm_kilograms, spec.mro_kilograms, spec.mh_payload_kilograms) == (
        mtplm,
        mro,
        payload,
    )


def test_the_540_catalogue_publishes_no_running_order(specs: dict[str, WingammSpec]) -> None:
    """It jumps from `Overall maximum weight KG 3.500` to `Payload KG 655`.

    So its MRO is derived, flagged as derived, and its self-check falls back to the
    cross-document form.
    """
    assert specs["Oasi 540.1"].mro_derived is True
    assert specs["Oasi 540.1"].mro_kilograms == 3500 - 655


@pytest.mark.parametrize("label", ["Oasi 610", "Oasi 690", "Brownie", "City Pro"])
def test_the_other_four_publish_it(specs: dict[str, WingammSpec], label: str) -> None:
    assert specs[label].mro_derived is False


@pytest.mark.parametrize(
    ("label", "seats", "berths_published"),
    [
        ("Oasi 540.1", 4, "3+1"),
        ("Oasi 610", 4, "4"),
        ("Oasi 690", 4, "4"),  # `Approved seats` and `Sleeping capacity`, this one alone
        ("Brownie", 4, "4"),
    ],
)
def test_the_catalogues_that_state_seats_and_berths_inline(
    specs: dict[str, WingammSpec], label: str, seats: int, berths_published: str
) -> None:
    assert specs[label].seats == seats
    assert specs[label].berths_published == berths_published


def test_the_city_pro_catalogue_states_no_berths_on_one_line(
    specs: dict[str, WingammSpec],
) -> None:
    """Its second technical page emits every label, then every value.

    Pairing 22 labels with 21 values by position is the silent misalignment
    `docs/adapters/README.md` forbids, so the berth count is read from the model page and
    the catalogue contributes nothing here rather than a guess.
    """
    assert specs["City Pro"].berths_published is None


def test_payload_decoys_are_not_read_as_the_payload() -> None:
    """Four wrong payloads sit in or beside the same block, and one is marketing copy.

    `PAYLOAD 350KG` is from the 610 catalogue's feature pages and is the *690's* figure.
    """
    block = "\n".join(
        [
            "PAYLOAD 350KG",
            "Overall maximum weight KG 3.500",
            "Weight in running order KG 3.047",
            "Payload KG 453",
            "Garage payload kg 200",
            "External rear motorbike rack payload (OPT) KG 150",
            "Towbar payload (OPT) KG 2.000",
        ]
    )
    assert wingamm.parse_spec(block).mh_payload_kilograms == 453


def test_the_gross_train_style_near_miss_is_not_read_as_the_laden_weight() -> None:
    """Each maximum-weight label is matched in full, so a longer one cannot substitute."""
    spec = wingamm.parse_spec("Maximum towable mass KG 2.000\nOverall maximum weight KG 3.500")
    assert spec.mtplm_kilograms == 3500


# --------------------------------------------------------------------------- #
# Layout prices — narrated only, never emitted
# --------------------------------------------------------------------------- #


def test_layout_prices_are_read_from_both_renderings() -> None:
    """The 610 and 690 print `OASI 610ST  106.300 €`; the 540.1 prints `€ 99.800`."""
    assert wingamm.parse_layout_prices(_text("wingamm_oasi_610_catalog_text.txt")) == {
        "OASI610ST": 106300,
        "OASI610GL": 106300,
        "OASI610M": 106300,
    }
    assert wingamm.parse_layout_prices(_text("wingamm_oasi_540_catalog_text.txt")) == {
        "OASI5401": 99800
    }


def test_price_for_matches_540_against_the_documents_5401() -> None:
    prices = {"OASI5401": 99800, "OASI610GL": 106300}
    assert wingamm.price_for("540", prices) == 99800
    assert wingamm.price_for("610GL", prices) == 106300
    assert wingamm.price_for("690G", prices) is None


def test_no_price_reaches_a_motorhome() -> None:
    """Wingamm publish a euro ex-works ex-VAT figure; FMLV holds a UK importer price.

    The adapter narrates the euro figure and emits nothing, so a run can never overwrite
    a pound price with it. See the module docstring in `src/adapters/wingamm.py`.
    """
    product = _product()
    extracted = wingamm._build_extracted_motorhome(product, "https://example.com/pdf", "https://example.com/page")
    assert extracted.motorhome.rrp_pounds is None
    assert extracted.motorhome.price_min_range_pounds is None
    assert "rrp_pounds" not in extracted.provenance


# --------------------------------------------------------------------------- #
# Model pages
# --------------------------------------------------------------------------- #


def test_the_540_page_gives_three_berths_from_3_plus_1() -> None:
    page = wingamm.parse_model_page(_text("wingamm_page_oasi_540.html"))
    assert page.berths_published == "3+1"
    assert page.berths == 3
    assert page.seats == 4
    assert page.base_vehicle_manufacturer == "Fiat"
    assert page.mtplm_kilograms == 3500


def test_the_610_gl_page_carries_the_block_twice(specs: dict[str, WingammSpec]) -> None:
    """`Length: 6,100 mm` in one block, `6.103 mm` in the other, against 6103 published.

    The first match wins; the 3mm gap is inside the tolerance, so nothing is dropped and
    nothing is even warned about.
    """
    page = wingamm.parse_model_page(_text("wingamm_page_oasi_610_gl.html"))
    assert page.length_mm == 6100
    product = _product(spec=specs["Oasi 610"], page=page)
    assert wingamm.length_warning(product) is None


def test_a_real_length_disagreement_is_warned_about(specs: dict[str, WingammSpec]) -> None:
    product = _product(spec=specs["Oasi 610"], page=WingammPage(length_mm=6200))
    warning = wingamm.length_warning(product)
    assert warning is not None
    assert "6103" in warning and "6200" in warning


def test_the_brownie_page_labels_the_chassis_tractor() -> None:
    """`Drive:` on the six Oasi pages, `Tractor:` on Brownie's and City Pro's.

    Reading only `Drive` leaves the base vehicle blank on the two products whose
    catalogue never spells out `FIAT DUCATO` either.
    """
    page = wingamm.parse_model_page(_text("wingamm_page_brownie.html"))
    assert page.base_vehicle_manufacturer == "Fiat"
    assert page.seats == 4
    assert page.berths == 4


def test_the_city_pro_page_publishes_running_order_not_total_mass() -> None:
    """And puts the value outside the span that holds its own label.

        <span ...><span ...>Mass in running order:&nbsp;</span></span>2.888 kg

    Both are why City Pro would otherwise have had no cross-document check at all.
    """
    page = wingamm.parse_model_page(_text("wingamm_page_city_pro.html"))
    assert page.mro_kilograms == 2888
    assert page.mtplm_kilograms is None
    assert page.berths == 2
    assert page.base_vehicle_manufacturer == "Fiat"


def test_an_empty_row_does_not_borrow_the_next_rows_value() -> None:
    """Only closing tags may be skipped, so reaching the next `<li>` is impossible."""
    html = (
        '<li><span class="t">Sleeps:&nbsp;</span></li>'
        '<li><span class="t">Total mass: 3,500 kg</span></li>'
    )
    page = wingamm.parse_model_page(html)
    assert page.berths is None
    assert page.mtplm_kilograms == 3500


def test_a_bumper_is_not_a_base_vehicle() -> None:
    """The City Pro catalogue's only mention of Fiat is `FIAT front bumper`."""
    assert wingamm.parse_spec("Body-coloured FIAT front bumper DESIGN PACK").base_vehicle_manufacturer is None
    assert wingamm.parse_spec("POWER ENGINE FIAT DUCATO 2.2 JTD 140 CV").base_vehicle_manufacturer == "Fiat"


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def _product(
    *,
    spec: WingammSpec | None = None,
    page: WingammPage | None = None,
    body_type: BodyType | None = BodyType.COACH_BUILT_LOW_PROFILE,
    intended_range: str | None = None,
) -> WingammProduct:
    return WingammProduct(
        fmlv_range="Oasi",
        model="610GL",
        slug="oasi-610-gl",
        document_label="Oasi 610",
        spec=spec
        or WingammSpec(
            mh_length_mm=6103,
            mh_width_mm=2240,
            mh_height_mm=3030,
            mtplm_kilograms=3500,
            mro_kilograms=3047,
            mh_payload_kilograms=453,
            seats=4,
            berths_published="4",
            base_vehicle_manufacturer="Fiat",
        ),
        page=page
        or WingammPage(
            seats=4,
            berths_published="4",
            length_mm=6103,
            mtplm_kilograms=3500,
            base_vehicle_manufacturer="Fiat",
        ),
        body_type=body_type,
        intended_range=intended_range,
    )


def test_a_consistent_product_reconciles() -> None:
    ok, why = wingamm.reconciles(_product())
    assert ok
    assert why is None


def test_a_payload_that_does_not_match_the_masses_is_dropped() -> None:
    """The check that matters: it catches a mass read out of the wrong row."""
    product = _product(spec=replace(_product().spec, mh_payload_kilograms=200))
    ok, why = wingamm.reconciles(product)
    assert not ok
    assert why is not None and "200kg payload" in why


def test_a_towbar_payload_read_as_the_payload_is_dropped() -> None:
    product = _product(spec=replace(_product().spec, mh_payload_kilograms=2000, mro_kilograms=1500))
    ok, _why = wingamm.reconciles(product)
    assert not ok


def test_a_catalogue_paired_with_the_wrong_range_is_dropped() -> None:
    """The cross-document half: the page republishes the total mass, so they must agree."""
    product = _product(page=replace(_product().page, mtplm_kilograms=3650))
    ok, why = wingamm.reconciles(product)
    assert not ok
    assert why is not None and "3650kg" in why


def test_a_berth_disagreement_between_page_and_catalogue_is_dropped() -> None:
    product = _product(page=replace(_product().page, berths_published="2"))
    ok, why = wingamm.reconciles(product)
    assert not ok
    assert why is not None and "berths" in why


def test_the_540_reconciles_despite_its_derived_running_order(
    specs: dict[str, WingammSpec],
) -> None:
    """Its arithmetic is vacuous by construction, so it must not be *failed* by it."""
    page = wingamm.parse_model_page(_text("wingamm_page_oasi_540.html"))
    ok, why = wingamm.reconciles(_product(spec=specs["Oasi 540.1"], page=page))
    assert ok, why


# --------------------------------------------------------------------------- #
# The record handed to the pipeline
# --------------------------------------------------------------------------- #


def test_both_halves_of_the_identity_carry_provenance() -> None:
    """FMLV files Brownie under range "Coach Built low profile" and City Pro under
    "Campervan". Renaming one column without the other corrupts the name, so both are
    proposed and each snippet says they belong together.
    """
    extracted = wingamm._build_extracted_motorhome(
        _product(), "https://example.com/pdf", "https://example.com/page"
    )
    assert "manufacturer_range" in extracted.provenance
    assert "model" in extracted.provenance
    for field in ("manufacturer_range", "model"):
        assert "accept both or neither" in extracted.provenance[field].snippet


def test_an_undeliverable_rename_proposes_neither_half() -> None:
    """Brownie's range is wrong in FMLV and stays wrong, deliberately.

    `{coach, built, low, profile, brownie}` -> `{brownie}` scores 0.200 against
    `matching.DEFAULT_THRESHOLD` of 0.5, so proposing it orphans `product_id` 5855 and
    reports a discontinuation that has not happened — which run #30 did. So FMLV's own
    range is emitted, unproposed, and the correction is narrated for a manual edit.
    """
    from src.diff.matching import DEFAULT_THRESHOLD, _identity_tokens

    baseline = _identity_tokens("Coach Built low profile", "Brownie")
    renamed = _identity_tokens("Brownie", "Brownie")
    assert len(baseline & renamed) / len(baseline | renamed) < DEFAULT_THRESHOLD

    brownie = next(d for d in wingamm._DOCUMENTS if d.label == "Brownie")
    assert brownie.fmlv_range == "Coach Built low profile"
    assert brownie.intended_range == "Brownie"

    extracted = wingamm._build_extracted_motorhome(
        _product(intended_range="Brownie"), "https://example.com/pdf", "https://example.com/page"
    )
    assert "manufacturer_range" not in extracted.provenance
    assert "model" not in extracted.provenance
    # The weights still update — this suppresses a rename, not the whole product.
    assert extracted.provenance["mtplm_kilograms"] is not None


def test_the_city_pro_rename_survives_matching_and_is_proposed() -> None:
    """Same class of error, opposite outcome: 0.667 clears the threshold comfortably.

    The asymmetry with Brownie is the matcher's, not Wingamm's.
    """
    from src.diff.matching import DEFAULT_THRESHOLD, _identity_tokens

    baseline = _identity_tokens("Campervan", "City Pro")
    renamed = _identity_tokens("City Pro", "City Pro")
    assert len(baseline & renamed) / len(baseline | renamed) > DEFAULT_THRESHOLD

    city_pro = next(d for d in wingamm._DOCUMENTS if d.label == "City Pro")
    assert city_pro.fmlv_range == "City Pro"
    assert city_pro.intended_range is None


def test_width_and_height_provenance_explains_the_inverted_rule() -> None:
    """They come from the PDF against the website, which is not the house default."""
    extracted = wingamm._build_extracted_motorhome(
        _product(), "https://example.com/pdf", "https://example.com/page"
    )
    for field in ("mh_width_mm", "mh_height_mm"):
        assert "contradicts itself" in extracted.provenance[field].snippet


def test_a_derived_running_order_says_so(specs: dict[str, WingammSpec]) -> None:
    extracted = wingamm._build_extracted_motorhome(
        _product(spec=specs["Oasi 540.1"]), "https://example.com/pdf", "https://example.com/page"
    )
    assert "derived" in extracted.provenance["mro_kilograms"].snippet


def test_a_published_running_order_does_not(specs: dict[str, WingammSpec]) -> None:
    extracted = wingamm._build_extracted_motorhome(
        _product(spec=specs["Oasi 610"]), "https://example.com/pdf", "https://example.com/page"
    )
    assert "derived" not in extracted.provenance["mro_kilograms"].snippet


def test_berth_provenance_carries_the_published_wording() -> None:
    """A reviewer seeing `3` needs to know Wingamm printed `3+1`."""
    page = wingamm.parse_model_page(_text("wingamm_page_oasi_540.html"))
    extracted = wingamm._build_extracted_motorhome(
        _product(page=page), "https://example.com/pdf", "https://example.com/page"
    )
    assert "3+1" in extracted.provenance["berths"].snippet
    assert "optional dinette bed" in extracted.provenance["berths"].snippet


def test_no_body_type_provenance_where_none_is_proposed() -> None:
    extracted = wingamm._build_extracted_motorhome(
        _product(body_type=None), "https://example.com/pdf", "https://example.com/page"
    )
    assert extracted.motorhome.body_type is None
    assert "body_type" not in extracted.provenance
