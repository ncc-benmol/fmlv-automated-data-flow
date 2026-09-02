"""Tests for the Knaus adapter's pure parsing functions, against real captured artefacts.

Fixtures were captured 1 September 2026 — see `docs/adapters/knaus.md`. The two index
pages are trimmed to their layout cards with the `<picture>`/`<svg>`/`<img>` markup
removed, verified to parse identically to the untrimmed pages before being saved; each
layout page is trimmed to its `<dl>` plus the price-list link. The price lists are the
*extracted text* of the PDFs, page-separated by a form feed — the PDFs themselves are
never committed, and `tests/fetch/test_pdf.py` covers the extraction itself.

No network here.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters.knaus import (
    DEFAULT_RANGES,
    HIGH_TOP_ABOVE_MM,
    MANUFACTURER,
    MATCH_THRESHOLD,
    KnausProduct,
    LayoutCard,
    PriceListRow,
    _build_extracted_motorhome,
    _centimetres_to_mm,
    _pl_row_values,
    _reconciles,
    _thousands,
    baseline_in_scope,
    find_price_list_url,
    parse_layout_index,
    parse_layout_page,
    parse_price_list_pages,
    parse_spec_rows,
)
from src.product_model.enums import BodyType
from src.product_model.model import Motorhome

FIXTURES = Path(__file__).parent / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / f"knaus_{name}.html").read_text(encoding="utf-8")


def _price_list_pages(name: str) -> list[str]:
    return (FIXTURES / f"knaus_pricelist_{name}.txt").read_text(encoding="utf-8").split("\x0c")


def _card(range_label: str, model: str, category: str = "motorhomes") -> LayoutCard:
    return LayoutCard(
        category=category,
        range_label=range_label,
        model=model,
        year=2027,
        price_text=None,
        url=f"https://www.knaus.com/en-gb/{category}/x/y",
    )


# --------------------------------------------------------------------------- #
# Number parsing — the German thousands separator
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3.500 kg", 3500),
        ("2.690 kg (2.555 kg - 2.824 kg)", 2690),
        ("699 cm", 699),
        ("from 75.895 GBP* incl. Selection equipment", 75895),
        ("from 107.985 GBP*", 107985),
        ("4", 4),
        (None, None),
        ("autom.", None),
    ],
)
def test_thousands_reads_the_german_separator(raw: str | None, expected: int | None) -> None:
    assert _thousands(raw) == expected


def test_thousands_never_treats_the_dot_as_a_decimal_point() -> None:
    """`3.500 kg` is three and a half *tonnes*, not three and a half kilograms.

    The regression this guards is silent and severe: nothing downstream bounds a mass, so
    a 3kg motorhome would reach a reviewer looking merely odd rather than impossible.
    """
    assert _thousands("3.500 kg") == 3500
    assert _thousands("3.500 kg") != 3
    assert _centimetres_to_mm("699 cm") == 6990


# --------------------------------------------------------------------------- #
# The Layouts index
# --------------------------------------------------------------------------- #


def test_index_yields_the_full_published_roster() -> None:
    """18 motorhomes and 10 campervans — KNAUS's own MY2027 UK roster.

    Reconciled against a second source at survey time: the German sitemap lists exactly
    the same 18 and the same 10. A change here is a real range change, not a parse drift.
    """
    motorhomes = parse_layout_index(_html("motorhomes_layouts_index"), "motorhomes")
    campervans = parse_layout_index(_html("campervans_layouts_index"), "camper-vans")
    assert len(motorhomes) == 18
    assert len(campervans) == 10


def test_index_reads_range_model_year_and_price_from_the_card() -> None:
    cards = parse_layout_index(_html("motorhomes_layouts_index"), "motorhomes")
    card = next(c for c in cards if c.range_label == "SKY TI VW" and c.model == "650 MEG")
    assert card.year == 2027
    assert card.rrp_pounds == 107985
    assert card.url == "https://www.knaus.com/en-gb/motorhomes/sky-ti-vw/650-meg"
    assert card.category == "motorhomes"


def test_index_covers_every_range_the_adapter_declares() -> None:
    found = {
        (c.category, c.range_label)
        for name, _url in (("motorhomes", ""), ("camper-vans", ""))
        for c in parse_layout_index(
            _html(
                "motorhomes_layouts_index"
                if name == "motorhomes"
                else "campervans_layouts_index"
            ),
            name,
        )
    }
    assert found == set(DEFAULT_RANGES)


def test_index_strips_the_model_year_tag_out_of_the_model() -> None:
    """The card prints `590 MF (2027)`; the model is `590 MF` and the year is separate."""
    cards = parse_layout_index(_html("motorhomes_layouts_index"), "motorhomes")
    assert all("(" not in card.model for card in cards)
    assert all(card.year == 2027 for card in cards)


def test_index_trims_the_boxlife_600_mq_trailing_space() -> None:
    """One BOXLIFE card prints `600 MQ ` with a trailing space inside the tag.

    Left in, the model would not match its price-list row and, worse, would score
    differently against the FMLV baseline than the identically-named BOXTIME layout.
    """
    cards = parse_layout_index(_html("campervans_layouts_index"), "camper-vans")
    models = [c.model for c in cards if c.range_label == "BOXLIFE PLATINUM SELECTION"]
    assert "600 MQ" in models
    assert all(m == m.strip() for m in models)


def test_index_prices_are_all_present_and_plausible() -> None:
    for name, category in (
        ("motorhomes_layouts_index", "motorhomes"),
        ("campervans_layouts_index", "camper-vans"),
    ):
        for card in parse_layout_index(_html(name), category):
            assert card.rrp_pounds is not None, card.label
            assert 60_000 < card.rrp_pounds < 130_000, card.label


# --------------------------------------------------------------------------- #
# The layout page
# --------------------------------------------------------------------------- #


def test_layout_page_reads_the_whole_specification() -> None:
    card = _card("SKY TI VW", "650 MEG")
    product = parse_layout_page(card, _html("sky_ti_vw_650_meg"))
    assert product.base_vehicle_manufacturer == "VW"
    assert product.mh_length_mm == 6990
    assert product.mh_width_mm == 2300
    assert product.mh_height_mm == 2870
    assert product.mro_kilograms == 3107
    assert product.mtplm_website == 3500
    assert product.berths == 2


def test_chassis_goes_through_the_shared_base_vehicle_map() -> None:
    """`FIAT` on the page, `Fiat` in FMLV. The map is the only place that decision lives."""
    product = parse_layout_page(_card("BOXTIME", "630 MX"), _html("boxtime_630_mx"))
    assert product.base_vehicle_manufacturer == "Fiat"


def test_berths_take_beds_not_max_number_of_beds() -> None:
    """`Beds: 2` and `Max. number of beds: 5` on the same page — the standard figure wins."""
    rows = parse_spec_rows(_html("boxtime_630_mx"))
    assert ("Beds", "2") in rows
    assert ("Max. number of beds", "5") in rows
    product = parse_layout_page(_card("BOXTIME", "630 MX"), _html("boxtime_630_mx"))
    assert product.berths == 2


def test_duplicated_mass_in_running_order_keeps_both_and_records_the_first() -> None:
    """18 of 28 layouts print the row twice with two different figures.

    The labels and tooltips are byte-identical, so nothing distinguishes them; the first
    is taken because it pairs with the Chassis/Engine/Gearbox rows above it. Both reach
    the reviewer through the provenance snippet — a dict-based parse would have dropped
    one silently.
    """
    product = parse_layout_page(
        _card("VAN TI VANSATION", "550 MF"), _html("van_ti_vansation_550_mf")
    )
    assert len(product.mro_published) == 2
    assert product.mro_published[0].startswith("2.690")
    assert product.mro_published[1].startswith("2.700")
    assert product.mro_kilograms == 2690

    extracted = _build_extracted_motorhome(product, None)
    snippet = extracted.provenance["mro_kilograms"].snippet
    assert "2.690" in snippet and "2.700" in snippet


def test_spec_rows_are_a_list_so_a_repeated_label_is_not_collapsed() -> None:
    rows = parse_spec_rows(_html("van_ti_vansation_550_mf"))
    masses = [value for label, value in rows if label.startswith("Mass in running order")]
    assert len(masses) == 2
    assert masses[0] != masses[1]


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def test_every_fixture_layout_reconciles() -> None:
    for name, card in (
        ("sky_ti_vw_650_meg", _card("SKY TI VW", "650 MEG")),
        ("van_ti_vansation_550_mf", _card("VAN TI VANSATION", "550 MF")),
        ("live_wave_700_meg", _card("L!VE WAVE PLATINUM SELECTION", "700 MEG")),
        ("boxtime_630_mx", _card("BOXTIME", "630 MX", "camper-vans")),
    ):
        assert _reconciles(parse_layout_page(card, _html(name))), name


def test_a_misread_mass_fails_the_tolerance_band() -> None:
    """The band is what catches a thousands separator mishandled or a row misread."""
    good = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert _reconciles(good)
    assert not _reconciles(replace(good, mro_kilograms=2107))
    assert not _reconciles(replace(good, mro_band=(2951, 9999)))


def test_a_missing_band_is_not_a_reason_to_drop_a_vehicle() -> None:
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert _reconciles(replace(product, mro_band=None))


def test_rounding_inside_a_kilogram_still_reconciles() -> None:
    """KNAUS round their own band, so the check allows a kilogram either way.

    This is not hypothetical: the SKY TI VW 650 MEG publishes `2.951` where an exact −5%
    of 3107 is 2952. Every one of the 28 layouts surveyed sat within a kilogram, and none
    sat further, which is where `_BAND_TOLERANCE_KG` comes from.
    """
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert product.mro_kilograms == 3107
    assert product.mro_band == (2951, 3262)  # exact ±5% would be (2952, 3262)

    exact_low = round(3107 * 0.95)
    exact_high = round(3107 * 1.05)
    assert _reconciles(replace(product, mro_band=(exact_low, exact_high)))
    assert _reconciles(replace(product, mro_band=(exact_low - 1, exact_high + 1)))
    assert not _reconciles(replace(product, mro_band=(exact_low - 2, exact_high)))
    assert not _reconciles(replace(product, mro_band=(exact_low, exact_high + 2)))


# --------------------------------------------------------------------------- #
# The price list
# --------------------------------------------------------------------------- #


def test_price_list_url_is_found_on_a_layout_page() -> None:
    url = find_price_list_url(_html("sky_ti_vw_650_meg"))
    assert url is not None
    assert url.startswith("https://konfigurator.knaustabbert.de/rest/1/downloadPriceList/")


def test_price_list_gives_the_belted_seat_count_per_layout() -> None:
    """`Three-point belts in driving direction`, the field the website never publishes.

    4 on the 650 MEG — its L-shaped seating group carries two belted seats as standard —
    and 2 on the two 700s, whose folding belted seats are a cost option.
    """
    price_list = parse_price_list_pages(_price_list_pages("sky_ti_vw"), "http://x")
    assert price_list.rows[("SKY TI VW", "650 MEG")].belts_in_driving_direction == 4
    assert price_list.rows[("SKY TI VW", "700 DEG")].belts_in_driving_direction == 2
    assert price_list.rows[("SKY TI VW", "700 DX")].belts_in_driving_direction == 2


def test_price_list_rows_are_keyed_on_range_and_model_together() -> None:
    """`650 MEG` exists in six KNAUS ranges, so the model alone is not a key.

    A category-wide price list covers all seven motorhome ranges in one document; keying
    on the model would leave one range's figures standing for all six.
    """
    price_list = parse_price_list_pages(_price_list_pages("sky_ti_vw"), "http://x")
    assert all(isinstance(key, tuple) and len(key) == 2 for key in price_list.rows)
    assert ("SKY TI VW", "650 MEG") in price_list.rows
    assert "650 MEG" not in price_list.rows


def test_price_list_gives_the_base_mtplm_where_the_website_gives_the_uprated_one() -> None:
    """L!VE WAVE 700 MEG: 3650 on the website, 3500 here, and the uprate priced at £329."""
    price_list = parse_price_list_pages(_price_list_pages("live_wave"), "http://x")
    row = price_list.rows[("L!VE WAVE PLATINUM SELECTION", "700 MEG")]
    assert row.mtplm_kilograms == 3500

    website = parse_layout_page(
        _card("L!VE WAVE PLATINUM SELECTION", "700 MEG"), _html("live_wave_700_meg")
    )
    assert website.mtplm_website == 3650
    assert replace(website, mtplm_price_list=row.mtplm_kilograms).mtplm_kilograms == 3500


def test_price_list_covers_every_layout_of_its_range() -> None:
    price_list = parse_price_list_pages(_price_list_pages("live_wave"), "http://x")
    models = {model for _range, model in price_list.rows}
    assert models == {"650 MG", "650 MF", "650 MEG", "700 MEG", "700 DX"}


def test_a_row_whose_value_count_disagrees_with_the_roster_is_rejected() -> None:
    """The padding trap: a short row must not be sliced to fit the model count.

    Taking the first `count` values of a longer row silently attributes one layout's
    figure to another; taking a shorter row at all means it has swallowed the next row's
    label. Both are rejected outright.
    """
    assert _pl_row_values("Belts 2 2 2", "Belts", 3) == ["2", "2", "2"]
    assert _pl_row_values("Belts 2 2", "Belts", 3) is None
    assert _pl_row_values("Belts 2 2 2 2", "Belts", 3) is None
    assert _pl_row_values("Nothing here", "Belts", 3) is None


def test_a_page_with_no_range_heading_contributes_nothing() -> None:
    """Without a range the rows have no safe key, so they are dropped rather than guessed."""
    page = "Technical Data 650 MEG 700 DEG 700 DX Three-point belts in driving direction 4 2 2"
    assert parse_price_list_pages([page], "http://x").rows == {}


# --------------------------------------------------------------------------- #
# Body type
# --------------------------------------------------------------------------- #


def test_campervans_are_high_tops_and_motorhomes_are_not() -> None:
    boxtime = parse_layout_page(
        _card("BOXTIME", "630 MX", "camper-vans"), _html("boxtime_630_mx")
    )
    assert boxtime.mh_height_mm is not None
    assert boxtime.mh_height_mm > HIGH_TOP_ABOVE_MM
    assert boxtime.body_type is BodyType.CAMPERVAN_HIGH_TOP

    sky = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert sky.body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_live_i_is_the_only_a_class_range() -> None:
    sky = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert replace(sky, card=_card("L!VE I", "650 MEG")).body_type is BodyType.A_CLASS
    assert sky.body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_a_campervan_of_unknown_height_gets_no_body_type() -> None:
    """Never guessed — the missing-data rule applies to body type like any other field."""
    boxtime = parse_layout_page(
        _card("BOXTIME", "630 MX", "camper-vans"), _html("boxtime_630_mx")
    )
    assert replace(boxtime, mh_height_mm=None).body_type is None


# --------------------------------------------------------------------------- #
# Payload, and the two figures that are not payload
# --------------------------------------------------------------------------- #


def test_payload_is_derived_from_the_two_masses() -> None:
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert product.mh_payload_kilograms == 3500 - 3107


def test_the_sites_own_payload_rows_are_never_read() -> None:
    """`Maximum payload` reads 8kg on this layout and -161kg in its price list.

    They are EU 2021/535 homologation figures net of passenger and optional-equipment
    mass. Reading either would put an 8kg payload on a 3.5 tonne motorhome.
    """
    rows = dict(parse_spec_rows(_html("sky_ti_vw_650_meg")))
    assert rows["Maximum payload (kg)"] == "8 kg"
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    assert product.mh_payload_kilograms == 393


# --------------------------------------------------------------------------- #
# Provenance and identity
# --------------------------------------------------------------------------- #


def test_every_value_set_on_the_model_is_registered_in_provenance() -> None:
    """A field set but not registered is invisible: right on matched products, blank on new ones."""
    card = replace(
        _card("SKY TI VW", "650 MEG"), price_text="from 107.985 GBP*", url="http://layout"
    )
    product = replace(
        parse_layout_page(card, _html("sky_ti_vw_650_meg")),
        mh_passenger_seats_inc_driver=4,
        mtplm_price_list=3500,
    )
    extracted = _build_extracted_motorhome(product, "http://pricelist")

    interesting = {
        "manufacturer_range",
        "model",
        "base_vehicle_manufacturer",
        "rrp_pounds",
        "mro_kilograms",
        "mtplm_kilograms",
        "mh_payload_kilograms",
        "mh_length_mm",
        "mh_width_mm",
        "mh_height_mm",
        "mh_passenger_seats_inc_driver",
        "berths",
        "body_type",
    }
    for name in interesting:
        assert getattr(extracted.motorhome, name) is not None, name
        assert name in extracted.provenance, name


def test_range_and_model_provenance_say_they_move_together() -> None:
    """FMLV's range names are a generation behind on every range, so both halves move."""
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    extracted = _build_extracted_motorhome(product, None)
    assert "both together" in extracted.provenance["manufacturer_range"].snippet
    assert "Paired with the range above" in extracted.provenance["model"].snippet


def test_seat_provenance_names_the_row_it_used_and_the_row_it_refused() -> None:
    product = replace(
        parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg")),
        mh_passenger_seats_inc_driver=4,
    )
    snippet = _build_extracted_motorhome(product, "http://pl").provenance[
        "mh_passenger_seats_inc_driver"
    ].snippet
    assert "Three-point belts in driving direction" in snippet
    assert "type-approval" in snippet


def test_mtplm_provenance_explains_an_override() -> None:
    website = parse_layout_page(
        _card("L!VE WAVE PLATINUM SELECTION", "700 MEG"), _html("live_wave_700_meg")
    )
    extracted = _build_extracted_motorhome(replace(website, mtplm_price_list=3500), None)
    snippet = extracted.provenance["mtplm_kilograms"].snippet
    assert "3500" in snippet and "3650" in snippet and "uprated" in snippet


def test_manufacturer_matches_the_registry_join_key() -> None:
    product = parse_layout_page(_card("SKY TI VW", "650 MEG"), _html("sky_ti_vw_650_meg"))
    motorhome = _build_extracted_motorhome(product, None).motorhome
    assert motorhome.manufacturer == MANUFACTURER == "Knaus Tabbert AG Knaus"
    assert motorhome.manufacturer_display_name == "Knaus"


# --------------------------------------------------------------------------- #
# Matching and baseline scope
# --------------------------------------------------------------------------- #


def test_threshold_rejects_the_sky_ti_replacement_but_keeps_the_boxlife_renames() -> None:
    """The 2027 SKY TI replaced the Fiat 700 MEG with a VW 700 DEG.

    At the 0.5 default that pair matches at exactly 0.500 and is offered as a revision,
    which both rewrites a Fiat coachbuilt into a VW one and hides the 700 MEG's
    discontinuation. The lowest legitimate KNAUS score is the 0.600 BOXLIFE rename, so
    0.55 separates them — the per-manufacturer threshold `docs/adapters/README.md` names.
    """
    from src.diff.matching import token_similarity

    def score(left: tuple[str, str], right: tuple[str, str]) -> float:
        return token_similarity(
            Motorhome(manufacturer=MANUFACTURER, manufacturer_range=left[0], model=left[1]),
            Motorhome(manufacturer=MANUFACTURER, manufacturer_range=right[0], model=right[1]),
        )

    bad = score(("SKY TI VW", "700 DEG"), ("Sky TI", "700 MEG"))
    assert bad == pytest.approx(0.5)
    assert bad < MATCH_THRESHOLD

    for legitimate in (
        (("BOXLIFE PLATINUM SELECTION", "540 MQ"), ("Boxlife", "540 MQ")),
        (("L!VE TI PLATINUM SELECTION", "590 MF"), ("L!ve TI", "590 MF")),
        (("VAN TI VW VANSATION", "640 MEG"), ("Van TI", "640 MEG")),
        (("SKY TI VW", "650 MEG"), ("Sky TI", "650 MEG")),
        (("L!VE I", "650 MEG"), ("L!ve I", "650 MEG")),
    ):
        assert score(*legitimate) >= MATCH_THRESHOLD, legitimate


def test_baseline_scope_matches_on_model_because_the_range_is_being_renamed() -> None:
    """Scoping on `manufacturer_range` would find no baseline row for a narrowed run.

    FMLV holds `Sky TI`, the site says `SKY TI VW`. Wingamm's failure was scoping on the
    very column being changed: the run then proposes a product FMLV already holds as new,
    and an upload duplicates it.
    """
    labels = {"SKY TI VW"}
    held_by_fmlv = Motorhome(
        manufacturer=MANUFACTURER, manufacturer_range="Sky TI", model="650 MEG"
    )
    assert baseline_in_scope(held_by_fmlv, labels)

    unrelated = Motorhome(
        manufacturer=MANUFACTURER, manufacturer_range="Boxlife", model="540 MQ"
    )
    assert not baseline_in_scope(unrelated, labels)


def test_baseline_scope_still_matches_an_exact_range_name() -> None:
    """So it keeps working once the proposed renames have been accepted."""
    labels = {"BOXTIME"}
    assert baseline_in_scope(
        Motorhome(manufacturer=MANUFACTURER, manufacturer_range="BOXTIME", model="540 MQ"),
        labels,
    )
    assert baseline_in_scope(
        Motorhome(
            manufacturer=MANUFACTURER, manufacturer_range="SKY TI VW", model="700 DEG"
        ),
        {"SKY TI VW"},
    )


def test_baseline_scope_does_not_drag_in_other_ranges_sharing_a_model_code() -> None:
    """`650 MEG` exists in six KNAUS ranges; a SKY TI run must not claim the other five.

    Scoping on the bare model code pulled twelve baseline rows into a three-product
    `--range "SKY TI VW"` run and reported eleven as disappeared. A check that fires on a
    correct run is worse than no check.
    """
    labels = {"SKY TI VW"}
    for other_range in ("L!ve I", "L!ve TI", "Van TI Plus", "Boxlife", "L!VE WAVE"):
        assert not baseline_in_scope(
            Motorhome(
                manufacturer=MANUFACTURER,
                manufacturer_range=other_range,
                model="650 MEG",
            ),
            labels,
        ), other_range


def test_baseline_scope_splits_the_shared_van_ti_range_by_model() -> None:
    """FMLV's one `Van TI` range spans two of the site's, so those entries pin the model."""
    vw = Motorhome(manufacturer=MANUFACTURER, manufacturer_range="Van TI", model="640 MEG")
    duplicate = Motorhome(
        manufacturer=MANUFACTURER, manufacturer_range="Van TI", model="550 MF"
    )
    assert baseline_in_scope(vw, {"VAN TI VW VANSATION"})
    assert not baseline_in_scope(vw, {"VAN TI VANSATION"})
    assert baseline_in_scope(duplicate, {"VAN TI VANSATION"})
    assert not baseline_in_scope(duplicate, {"VAN TI VW VANSATION"})


def test_baseline_scope_ignores_a_row_with_no_model() -> None:
    assert not baseline_in_scope(
        Motorhome(manufacturer=MANUFACTURER, manufacturer_range="Whatever", model=None),
        {"SKY TI VW"},
    )


# --------------------------------------------------------------------------- #
# The superseded / wrong-document negatives
# --------------------------------------------------------------------------- #


def test_a_german_price_list_link_is_still_matched_only_by_shape_not_language() -> None:
    """The URL carries no language, so the *page* is the filter, not the pattern.

    KNAUS publish a German `VAN TI DE | DE` price list on the same endpoint. It is linked
    only from `de-de` pages, which this adapter never fetches — the defence is that the
    price-list URL is read off the English layout page itself. This test pins the
    host-and-path anchoring so a future loosening cannot start matching other hosts.
    """
    assert find_price_list_url('<a href="https://example.com/downloadPriceList/x">') is None
    assert (
        find_price_list_url(
            '<a href="https://konfigurator.knaustabbert.de/rest/1/downloadPriceList/AbC-1_2">'
        )
        == "https://konfigurator.knaustabbert.de/rest/1/downloadPriceList/AbC-1_2"
    )


def test_a_layout_card_without_a_technical_data_link_is_dropped() -> None:
    """There is no route to a specification without it, so half a product is not carried."""
    card_html = (
        '<h3><span class="c-tag">550 MF (2027)</span></h3>'
        "<p>from 73.765 GBP*</p>"
    )
    assert parse_layout_index(card_html, "motorhomes") == []


def test_an_empty_index_yields_nothing_rather_than_raising() -> None:
    assert parse_layout_index("", "motorhomes") == []
    assert parse_spec_rows("") == []
