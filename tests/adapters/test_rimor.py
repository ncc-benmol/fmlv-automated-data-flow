"""Rimor's parsing functions, against real captured pages from both of its sites.

No network here. Every negative test below is a trap that actually bit while the adapter
was being written or rebuilt; see `docs/adapters/rimor.md`.

The fixtures are trimmed to the regions the adapter reads — for the MNC pages that means
scripts, styles and the image gallery are gone, and for the factory pages the navigation
plus the overview block. `rimor_mnc_*_category.html` keeps only the product anchors,
duplicates included, because the duplicates are what `parse_mnc_product_slugs` exists to
collapse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import rimor
from src.product_model.enums import BedType, BodyType

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def kilig_category() -> str:
    return _fixture("rimor_mnc_kilig_category.html")


@pytest.fixture(scope="module")
def sailer_category() -> str:
    return _fixture("rimor_mnc_sailer_category.html")


@pytest.fixture(scope="module")
def mnc_kilig_5() -> str:
    return _fixture("rimor_mnc_kilig_5_product.html")


@pytest.fixture(scope="module")
def mnc_kilig_66() -> str:
    return _fixture("rimor_mnc_kilig_66_product.html")


@pytest.fixture(scope="module")
def mnc_sailer_55_plus_demo() -> str:
    return _fixture("rimor_mnc_sailer_55_plus_demo_product.html")


@pytest.fixture(scope="module")
def mnc_horus_40_automatic() -> str:
    return _fixture("rimor_mnc_horus_40_automatic_product.html")


@pytest.fixture(scope="module")
def mnc_van_238() -> str:
    return _fixture("rimor_mnc_van_238_product.html")


@pytest.fixture(scope="module")
def factory_kilig_5() -> str:
    return _fixture("rimor_factory_kilig_5_model.html")


@pytest.fixture(scope="module")
def factory_kilig_66_plus() -> str:
    return _fixture("rimor_factory_kilig_66_plus_model.html")


@pytest.fixture(scope="module")
def factory_horus_38() -> str:
    return _fixture("rimor_factory_horus_38_model.html")


@pytest.fixture(scope="module")
def factory_sarus_66_plus() -> str:
    return _fixture("rimor_factory_sarus_66_plus_model.html")


@pytest.fixture(scope="module")
def factory_kilig_listing() -> str:
    return _fixture("rimor_factory_kilig_low_profile_listing.html")


# --------------------------------------------------------------------------- #
# Slug parsing — the join key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("rimor-kilig-55-plus-2027", ("kilig", "55-plus", 2027, frozenset())),
        ("rimor-kilig-5-2026", ("kilig", "5", 2026, frozenset())),
        ("rimor-kilig-9", ("kilig", "9", None, frozenset())),
        ("rimor-horus-40-2026-automatic", ("horus", "40", 2026, frozenset({"automatic"}))),
        ("rimor-super-brig-677-tc-2027", ("super-brig", "677-tc", 2027, frozenset())),
        ("rimor-super-brig-suite-2027", ("super-brig", "suite", 2027, frozenset())),
        ("rimor-van-238-2026-automatic", ("van", "238", 2026, frozenset({"automatic"}))),
    ],
)
def test_parse_layout_key_reduces_a_slug_to_its_layout(
    slug: str, expected: tuple[str, str, int | None, frozenset[str]]
) -> None:
    assert rimor.parse_layout_key(slug) == expected


def test_parse_layout_key_reads_super_brig_before_sarus() -> None:
    """`super-brig` has to be matched before any shorter prefix, or it splits wrongly.

    The range list is ordered longest-first for exactly this reason.
    """
    range_slug, layout, _year, _markers = rimor.parse_layout_key(
        "rimor-super-brig-695-tc-2027"
    )
    assert (range_slug, layout) == ("super-brig", "695-tc")


def test_parse_layout_key_collapses_every_listing_of_one_layout() -> None:
    """A layout's plain, optioned and demo listings all have to reduce to one key."""
    keys = {
        rimor.parse_layout_key(slug)[:2]
        for slug in (
            "rimor-sailer-55-plus-2026",
            "rimor-sailer-55-plus-2026-automatic-demo-van",
        )
    }
    assert keys == {("sailer", "55-plus")}


def test_parse_layout_key_marks_stock_listings() -> None:
    _range, _layout, _year, markers = rimor.parse_layout_key(
        "rimor-kilig-79-2026-automatic-demo-van"
    )
    assert markers & rimor.STOCK_MARKERS


def test_parse_layout_key_rejects_an_unknown_range() -> None:
    """A slug naming no known range returns None rather than being guessed into one."""
    assert rimor.parse_layout_key("rimor-elsewhere-99-2027") is None
    assert rimor.parse_layout_key("some-other-product") is None


def test_parse_layout_key_rejects_a_slug_with_no_layout_left() -> None:
    """Every token being noise means there is no layout to key on."""
    assert rimor.parse_layout_key("rimor-kilig-2026") is None


# --------------------------------------------------------------------------- #
# MNC: the range
# --------------------------------------------------------------------------- #


def test_parse_mnc_product_slugs_deduplicates(kilig_category: str) -> None:
    """Each product is linked several times per page — image, title and "More Info"."""
    slugs = rimor.parse_mnc_product_slugs(kilig_category)
    assert len(slugs) == len(set(slugs))
    assert "rimor-kilig-55-plus-2027" in slugs
    assert len(slugs) == 18


def test_select_listings_keeps_one_slug_per_layout(kilig_category: str) -> None:
    slugs = rimor.parse_mnc_product_slugs(kilig_category)
    selected, set_aside = rimor.select_listings(slugs)

    assert len(selected) == 15
    assert len(selected) + len(set_aside) == len(slugs)
    keys = {rimor.parse_layout_key(slug)[:2] for slug in selected}
    assert len(keys) == len(selected)


def test_select_listings_prefers_a_plain_listing_over_a_demo_unit() -> None:
    """Kilig 79 has both a plain page and a demo van; the plain page is the layout."""
    selected, set_aside = rimor.select_listings(
        ["rimor-kilig-79-2026-automatic-demo-van", "rimor-kilig-79-2026"]
    )
    assert selected == ["rimor-kilig-79-2026"]
    assert "rimor-kilig-79-2026-automatic-demo-van" in set_aside


def test_select_listings_falls_back_to_a_demo_unit_when_it_is_all_there_is() -> None:
    """Sailer 55 Plus is genuinely on sale; only its demo listing survives on MNC.

    Dropping it would lose a layout MNC really sells, so the demo listing stands in —
    and `price_from` then takes the pre-discount figure.
    """
    selected, _set_aside = rimor.select_listings(
        ["rimor-sailer-55-plus-2026-automatic-demo-van"]
    )
    assert selected == ["rimor-sailer-55-plus-2026-automatic-demo-van"]


def test_select_listings_prefers_the_base_vehicle_over_an_optioned_variant() -> None:
    """Between two equally clean listings the shorter slug wins, which is the base."""
    selected, _set_aside = rimor.select_listings(
        ["rimor-horus-40-2026-automatic", "rimor-horus-40-2026"]
    )
    assert selected == ["rimor-horus-40-2026"]


def test_select_listings_prefers_the_later_model_year() -> None:
    selected, _set_aside = rimor.select_listings(
        ["rimor-sailer-87-plus-2026", "rimor-sailer-87-plus-2027"]
    )
    assert selected == ["rimor-sailer-87-plus-2027"]


def test_select_listings_explains_every_slug_it_sets_aside(sailer_category: str) -> None:
    slugs = rimor.parse_mnc_product_slugs(sailer_category)
    selected, set_aside = rimor.select_listings(slugs)
    assert len(selected) == 5
    assert set(set_aside) == set(slugs) - set(selected)
    assert all(reason for reason in set_aside.values())


# --------------------------------------------------------------------------- #
# MNC: the price
# --------------------------------------------------------------------------- #


def test_parse_mnc_listing_reads_an_undiscounted_price(mnc_kilig_5: str) -> None:
    listing = rimor.parse_mnc_listing(mnc_kilig_5, "rimor-kilig-5-2026", "u")
    assert listing.title == "Rimor Kilig 5 2026"
    assert listing.rrp_pounds == 59_995
    assert listing.pre_discount_pounds is None
    assert listing.is_demo is False


def test_parse_mnc_listing_takes_the_current_price_of_a_promoted_layout(
    mnc_horus_40_automatic: str,
) -> None:
    """The whole Horus range shows £61,990 struck through at £59,995.

    That is a range-wide promotion, and £59,995 is the figure MNC's own page leads with,
    so it is the guide price FMLV should match.
    """
    listing = rimor.parse_mnc_listing(
        mnc_horus_40_automatic, "rimor-horus-40-2026-automatic", "u"
    )
    assert listing.is_demo is False
    assert listing.rrp_pounds == 59_995
    assert listing.pre_discount_pounds == 61_990


def test_parse_mnc_listing_takes_the_pre_discount_price_of_a_demo_unit(
    mnc_sailer_55_plus_demo: str,
) -> None:
    """A demo unit's discount belongs to that vehicle, not to the layout.

    £69,995 is exactly what the other three Sailers cost; £64,995 is what this one van
    costs. Publishing the latter as the layout's price would be wrong.
    """
    listing = rimor.parse_mnc_listing(
        mnc_sailer_55_plus_demo, "rimor-sailer-55-plus-2026-automatic-demo-van", "u"
    )
    assert listing.is_demo is True
    assert listing.rrp_pounds == 69_995


def test_price_from_detects_a_demo_unit_from_the_page_not_the_slug(
    mnc_sailer_55_plus_demo: str,
) -> None:
    """`rimor-sailer-55-plus-2026` 301s onto the demo van, so the slug cannot be trusted.

    Parsed under the *plain* slug, the listing must still be recognised as a demo unit
    from its title, and still yield the pre-discount price.
    """
    listing = rimor.parse_mnc_listing(
        mnc_sailer_55_plus_demo, "rimor-sailer-55-plus-2026", "u"
    )
    assert listing.markers == frozenset()
    assert listing.is_demo is True
    assert listing.rrp_pounds == 69_995


def test_price_from_reads_the_currency_symbol_across_its_own_span() -> None:
    """WooCommerce puts the £ in a span of its own, so symbol and digits never adjoin."""
    block = (
        '<span class="woocommerce-Price-amount amount"><bdi>'
        '<span class="woocommerce-Price-currencySymbol">&pound;</span>59,995</bdi></span>'
    )
    assert rimor.price_from(block, is_demo=False) == (59_995, None)


def test_price_from_ignores_a_page_with_no_price() -> None:
    assert rimor.price_from("<span>Call for details</span>", is_demo=False) == (None, None)


# --------------------------------------------------------------------------- #
# MNC: body type and base vehicle
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("fixture_name", "slug", "expected"),
    [
        ("rimor_mnc_kilig_5_product.html", "rimor-kilig-5-2026",
         BodyType.COACH_BUILT_OVER_CAB_BED),
        ("rimor_mnc_kilig_66_product.html", "rimor-kilig-66-2026",
         BodyType.COACH_BUILT_LOW_PROFILE),
        ("rimor_mnc_van_238_product.html", "rimor-van-238-2026-automatic",
         BodyType.CAMPERVAN),
    ],
)
def test_parse_mnc_listing_reads_body_type_from_the_categories(
    fixture_name: str, slug: str, expected: BodyType
) -> None:
    listing = rimor.parse_mnc_listing(_fixture(fixture_name), slug, "u")
    assert listing.body_type is expected


def test_parse_mnc_listing_normalises_the_base_vehicle(mnc_horus_40_automatic: str) -> None:
    """"Vehicle: Fiat Ducato" is a chassis; FMLV stores the make."""
    listing = rimor.parse_mnc_listing(
        mnc_horus_40_automatic, "rimor-horus-40-2026-automatic", "u"
    )
    assert listing.base_vehicle_manufacturer == "Fiat"


def test_parse_mnc_listing_files_the_van_under_the_range_mnc_gives_it(
    mnc_van_238: str,
) -> None:
    """MNC lists the Van 238 under Horus, and MNC decides the range."""
    listing = rimor.parse_mnc_listing(mnc_van_238, "rimor-van-238-2026-automatic", "u")
    assert listing.range_slug == "van"
    assert listing.range_label == "Horus"


# --------------------------------------------------------------------------- #
# rimor.it: the specification
# --------------------------------------------------------------------------- #


def test_parse_model_page_reads_every_field(factory_kilig_5: str) -> None:
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert model.range_label == "Kilig"
    assert model.model == "5"
    assert (model.mh_length_mm, model.mh_width_mm, model.mh_height_mm) == (6970, 2340, 3040)
    assert model.mh_passenger_seats_inc_driver == 6
    assert model.berths == 4
    assert model.mtplm_kilograms == 3500
    assert model.mro_kilograms == 2961
    assert model.mh_payload_kilograms == 539
    assert model.body_type is BodyType.COACH_BUILT_OVER_CAB_BED
    assert model.bed_types == [BedType.TRANSVERSE]


def test_parse_model_page_takes_only_the_outside_dimension(factory_kilig_5: str) -> None:
    """The rows pair outside with inside: `2340 - 2200 mm`. Only the first is FMLV's."""
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert model.mh_width_mm == 2340
    assert model.mh_height_mm == 3040


def test_parse_model_page_takes_the_standard_chassis_not_an_uprated_one(
    factory_kilig_5: str,
) -> None:
    """MTPLM reads `3500 / 3550 / 4100 kg`; the heavier two are paid options."""
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert model.mtplm_text == "3500 / 3550 / 4100"
    assert model.mtplm_kilograms == 3500


def test_parse_model_page_reads_a_single_figure_mtplm(factory_horus_38: str) -> None:
    """Horus quotes one chassis and carries no footnote link, unlike Kilig."""
    model = rimor.parse_model_page(factory_horus_38, "/int/en/gamma/horus/modello/38")
    assert model.mtplm_text == "3500"
    assert model.mtplm_kilograms == 3500
    assert model.mh_payload_kilograms == 730


def test_parse_model_page_drops_the_reduced_seat_homologation(factory_kilig_5: str) -> None:
    """Seats read `6 / 5`: the `5` frees up payload and is not the standard figure."""
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert model.seats_text == "6 / 5"
    assert model.mh_passenger_seats_inc_driver == 6


def test_parse_model_page_tells_seats_and_berths_apart(factory_kilig_5: str) -> None:
    """The two widgets are identical but for an Italian icon class.

    `posti omologati` is seats and `posti letto` is berths. Kilig 5 publishes 6 and 4, so
    reading them by position instead would swap them and MNC would appear to be right.
    """
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert model.mh_passenger_seats_inc_driver == 6
    assert model.berths == 4


def test_parse_model_page_scopes_to_the_overview_block(factory_kilig_66_plus: str) -> None:
    """The page repeats the range's other layouts; an unscoped read takes theirs."""
    model = rimor.parse_model_page(
        factory_kilig_66_plus, "/int/en/gamma/kilig/modello/66-plus"
    )
    assert model.model == "66 Plus"
    assert model.mh_length_mm == 7338
    assert model.mro_kilograms == 3017


def test_parse_model_page_needs_the_overview_block() -> None:
    """No overview means the page shape moved; say so rather than emit empty fields."""
    assert rimor.parse_model_page("<html><body>nothing</body></html>", "/x") is None


def test_parse_model_page_reads_body_type_from_the_url_segment(
    factory_sarus_66_plus: str,
) -> None:
    model = rimor.parse_model_page(
        factory_sarus_66_plus, "/int/en/gamma/sarus/modello/66-plus"
    )
    assert model.body_style == "low-profile"
    assert model.body_type is BodyType.COACH_BUILT_LOW_PROFILE


def test_parse_model_slugs_deduplicates_the_repeated_list(factory_kilig_listing: str) -> None:
    """The model list appears twice per body-style page, in content and in a footer."""
    slugs = rimor.parse_model_slugs(factory_kilig_listing)
    assert len(slugs) == len(set(slugs))
    assert slugs == [
        "55-plus", "56-plus", "66-plus", "67-plus", "69-plus", "73-plus",
        "77-plus", "78-plus", "79-plus", "95-plus", "99-plus",
    ]


# --------------------------------------------------------------------------- #
# The join
# --------------------------------------------------------------------------- #


def test_factory_slug_matches_exactly_when_it_can() -> None:
    assert rimor._factory_slug("677-tc", {"677-tc", "687-tc"}) == "677-tc"


def test_factory_slug_survives_rimors_plus_renaming() -> None:
    """Rimor renamed its Kilig low-profile line to `<n> Plus`; MNC kept the old names."""
    assert rimor._factory_slug("66", {"66-plus", "67-plus"}) == "66-plus"


def test_factory_slug_also_works_the_other_way() -> None:
    """MNC will catch up, and Sarus already lists `66 Plus` names of its own."""
    assert rimor._factory_slug("66-plus", {"66"}) == "66"


def test_factory_slug_invents_nothing() -> None:
    """Only a slug the factory actually publishes is returned."""
    assert rimor._factory_slug("12", {"38", "40", "45"}) is None


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def test_dimension_conflicts_tolerates_mncs_truncation(
    mnc_kilig_66: str, factory_kilig_66_plus: str
) -> None:
    """MNC prints 7.33 m where the factory says 7338 mm — truncation, not disagreement."""
    listing = rimor.parse_mnc_listing(mnc_kilig_66, "rimor-kilig-66-2026", "u")
    model = rimor.parse_model_page(
        factory_kilig_66_plus, "/int/en/gamma/kilig/modello/66-plus"
    )
    assert listing.mnc_length_mm == 7330
    assert model.mh_length_mm == 7338
    assert rimor.dimension_conflicts(listing, model) == []


def test_dimension_conflicts_reports_a_real_disagreement(
    mnc_kilig_5: str, factory_kilig_66_plus: str
) -> None:
    """Deliberately mismatched: the check has to notice a wrongly joined layout."""
    listing = rimor.parse_mnc_listing(mnc_kilig_5, "rimor-kilig-5-2026", "u")
    model = rimor.parse_model_page(
        factory_kilig_66_plus, "/int/en/gamma/kilig/modello/66-plus"
    )
    conflicts = rimor.dimension_conflicts(listing, model)
    assert conflicts
    assert "length" in conflicts[0]


def test_dimension_conflicts_stays_quiet_when_mnc_publishes_nothing(
    factory_kilig_5: str,
) -> None:
    """Horus 12 has no dimensions on MNC at all; that is not a conflict."""
    listing = rimor.parse_mnc_listing(
        "<html><body></body></html>", "rimor-horus-12-2027", "u"
    )
    model = rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    assert rimor.dimension_conflicts(listing, model) == []


# --------------------------------------------------------------------------- #
# Building a product
# --------------------------------------------------------------------------- #


def test_product_takes_price_from_mnc_and_specs_from_the_factory(
    mnc_kilig_66: str, factory_kilig_66_plus: str
) -> None:
    """The whole point of the adapter, on one product.

    Note the model name: MNC still calls this "Kilig 66" and Rimor now calls it
    "66 Plus". The factory's current name wins, because a rename is not a new model.
    """
    listing = rimor.parse_mnc_listing(mnc_kilig_66, "rimor-kilig-66-2026", "u")
    model = rimor.parse_model_page(
        factory_kilig_66_plus, "/int/en/gamma/kilig/modello/66-plus"
    )
    product = rimor._build_extracted_motorhome(listing, model).motorhome

    assert product.manufacturer == "Rimor"
    assert product.manufacturer_range == "Kilig"
    assert product.model == "66 Plus"
    assert product.rrp_pounds == 59_995
    assert product.mh_length_mm == 7338
    assert product.mh_passenger_seats_inc_driver == 4
    assert product.berths == 4
    assert product.mtplm_kilograms == 3500
    assert product.mro_kilograms == 3017
    assert product.mh_payload_kilograms == 483
    assert product.base_vehicle_manufacturer == "Ford"


def test_product_never_takes_berths_from_mnc(
    mnc_kilig_5: str, factory_kilig_5: str
) -> None:
    """MNC says "6 berth with 6 travel seats"; the factory says 6 seats and 4 berths.

    MNC repeats its travel-seat count in the berth position on the coachbuilts, so its
    berth figure is not a berth count at all.
    """
    listing = rimor.parse_mnc_listing(mnc_kilig_5, "rimor-kilig-5-2026", "u")
    assert listing.mnc_berths == 6

    product = rimor._build_extracted_motorhome(
        listing, rimor.parse_model_page(factory_kilig_5, "/int/en/gamma/kilig/modello/5")
    ).motorhome
    assert product.berths == 4
    assert product.mh_passenger_seats_inc_driver == 6


def test_product_without_a_factory_page_keeps_price_and_body_type(
    mnc_van_238: str,
) -> None:
    """The Van 238 has no factory spec page, and is still a UK product MNC sells."""
    listing = rimor.parse_mnc_listing(mnc_van_238, "rimor-van-238-2026-automatic", "u")
    product = rimor._build_extracted_motorhome(listing, None).motorhome

    assert product.manufacturer_range == "Horus"
    assert product.model == "Van 238"
    assert product.rrp_pounds == 56_995
    assert product.body_type is BodyType.CAMPERVAN
    assert product.base_vehicle_manufacturer == "Ford"
    # Nothing MNC alone cannot be trusted on.
    assert product.mh_length_mm is None
    assert product.mtplm_kilograms is None


def test_product_without_a_factory_page_takes_counts_only_when_they_differ(
    mnc_van_238: str,
) -> None:
    """MNC's "3 berth with 4 travel seats" has two distinct figures, so it is usable.

    Two equal figures cannot be told apart from MNC's repeat-the-seat-count bug, so they
    are left empty instead — see `test_product_without_a_factory_page_drops_equal_counts`.
    """
    listing = rimor.parse_mnc_listing(mnc_van_238, "rimor-van-238-2026-automatic", "u")
    product = rimor._build_extracted_motorhome(listing, None).motorhome
    assert product.mh_passenger_seats_inc_driver == 4
    assert product.berths == 3


def test_product_without_a_factory_page_drops_equal_counts(mnc_kilig_5: str) -> None:
    """Kilig 5 reads "6 berth with 6 travel seats" — the bug signature, so unusable."""
    listing = rimor.parse_mnc_listing(mnc_kilig_5, "rimor-kilig-5-2026", "u")
    product = rimor._build_extracted_motorhome(listing, None).motorhome
    assert product.berths is None
    assert product.mh_passenger_seats_inc_driver is None


def test_product_records_which_price_a_demo_listing_gave(
    mnc_sailer_55_plus_demo: str,
) -> None:
    """A reviewer has to be able to see that the pre-discount figure was the choice."""
    listing = rimor.parse_mnc_listing(
        mnc_sailer_55_plus_demo, "rimor-sailer-55-plus-2026-automatic-demo-van", "u"
    )
    extracted = rimor._build_extracted_motorhome(listing, None)
    assert extracted.motorhome.rrp_pounds == 69_995
    assert "before the demo-unit discount" in extracted.provenance["rrp_pounds"].snippet


def test_product_provenance_cites_the_site_each_field_came_from(
    mnc_kilig_66: str, factory_kilig_66_plus: str
) -> None:
    listing = rimor.parse_mnc_listing(
        mnc_kilig_66, "rimor-kilig-66-2026", "https://motorhomesandcaravansltd.co.uk/product/x/"
    )
    model = rimor.parse_model_page(
        factory_kilig_66_plus, "/int/en/gamma/kilig/modello/66-plus"
    )
    provenance = rimor._build_extracted_motorhome(listing, model).provenance

    assert "motorhomesandcaravansltd.co.uk" in provenance["rrp_pounds"].source_url
    assert "rimor.it" in provenance["mh_length_mm"].source_url
    assert "rimor.it" in provenance["berths"].source_url
    assert "rimor.it" in provenance["mh_payload_kilograms"].source_url


# --------------------------------------------------------------------------- #
# Bedding solutions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("solution", "expected"),
    [
        ("Transverse bed", [BedType.TRANSVERSE]),
        ("Twin beds", [BedType.FIXED_SEPARATE]),
        ("Bunk beds", [BedType.FIXED_BUNKS]),
        ("Double bunk beds", [BedType.FIXED_BUNKS]),
        ("Double superimposed bunk beds", [BedType.FIXED_BUNKS]),
        ("Island bed", [BedType.ISLAND]),
        ("Rear suite bed", [BedType.FIXED]),
        ("Double bed", [BedType.FIXED]),
        ("Front drop-down bed", [BedType.DROP_DOWN]),
    ],
)
def test_bed_types_for_maps_each_solution(solution: str, expected: list[BedType]) -> None:
    assert rimor.bed_types_for(solution) == expected


def test_bed_types_for_matches_the_longer_phrase_first() -> None:
    """`Double bed` is a prefix of `Double bunk beds`; the wrong order flattens bunks."""
    assert rimor.bed_types_for("Double bunk beds") == [BedType.FIXED_BUNKS]


def test_bed_types_for_leaves_an_unknown_solution_empty() -> None:
    """An unmapped phrase is a new layout style to notice, not one to guess at."""
    assert rimor.bed_types_for("Hammock") == []
    assert rimor.bed_types_for(None) == []
