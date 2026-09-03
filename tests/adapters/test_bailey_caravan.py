"""Bailey's touring-caravan adapter — the first caravan adapter.

Fixtures are whole model pages saved from the live site on 3 September 2026, with only
`<script>`, `<style>` and comments removed (checked at capture time to leave every spec
value reachable). Whole pages rather than the spec section alone, because the page turns
out to carry **two** blocks of `col-6` label/value pairs — `Axle` and `RRP Price` live in
an early one around 96KB in, and `Range`/`Model`/the dimensions in the "Technical
specification" section 240KB further down. A fixture trimmed to the heading a reader would
think of as "the spec table" silently lost the axle and the price.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import ADAPTERS, adapter_for, bailey, bailey_caravan
from src.product_model.caravan import Caravan
from src.product_model.enums import CaravanBodyType
from src.vehicle_class import VehicleClass

FIXTURES_DIR = Path(__file__).parent / "fixtures"

MESSINA = "bailey_caravan_pegasus_black_messina.html"
DISCOVERY_D4_2 = "bailey_caravan_discovery_d4_2.html"
CABRERA = "bailey_caravan_unicorn_deluxe_cabrera.html"
PHOENIX_420 = "bailey_caravan_phoenix_black_420.html"
INDEX = "bailey_caravan_models_index.html"


def fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def parsed(name: str) -> bailey_caravan.BaileyCaravan:
    return bailey_caravan.parse_model_page(fixture(name))


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_the_two_bailey_adapters_coexist() -> None:
    """The whole point of keying `ADAPTERS` on `(manufacturer, class)`."""
    assert adapter_for("Bailey", VehicleClass.CARAVAN) is bailey_caravan
    assert adapter_for("Bailey", VehicleClass.MOTORHOME) is bailey
    assert adapter_for("Bailey") is bailey  # the default is still motorhomes
    assert ADAPTERS[("Bailey", VehicleClass.CARAVAN)] is bailey_caravan


def test_the_adapter_declares_itself_a_caravan_adapter() -> None:
    """Without this it would register under `(Bailey, motorhome)` and replace `bailey`."""
    assert bailey_caravan.VEHICLE_CLASS is VehicleClass.CARAVAN
    assert bailey_caravan.MANUFACTURER == bailey.MANUFACTURER


# --------------------------------------------------------------------------- #
# The model index
# --------------------------------------------------------------------------- #


def test_the_index_lists_every_current_model() -> None:
    assert len(bailey_caravan.find_model_urls(fixture(INDEX))) == 23


def test_the_index_can_be_narrowed_to_one_range() -> None:
    urls = bailey_caravan.find_model_urls(fixture(INDEX), "discovery")

    assert len(urls) == 3
    assert all("/touring-caravans/discovery/" in url for url in urls)


def test_a_range_that_is_a_prefix_of_another_is_not_over_matched() -> None:
    """`pegasus-black-edition` must not also sweep in some future `pegasus-black-x`."""
    urls = bailey_caravan.find_model_urls(fixture(INDEX), "pegasus-black-edition")

    assert len(urls) == 5
    assert all(
        url.startswith(f"{bailey_caravan.BASE_URL}/touring-caravans/pegasus-black-edition/")
        for url in urls
    )


def test_the_interior_tour_anchors_are_not_taken_for_model_pages() -> None:
    """The index links each model twice — once plainly, once with `#interior360`."""
    urls = bailey_caravan.find_model_urls(fixture(INDEX))

    assert len(urls) == len(set(urls))
    assert not [url for url in urls if "#" in url]


def test_every_default_range_is_present_in_the_index() -> None:
    index = fixture(INDEX)
    for path, _label in bailey_caravan.DEFAULT_RANGES:
        assert bailey_caravan.find_model_urls(index, path), f"no models found for {path}"


# --------------------------------------------------------------------------- #
# Parsing one page
# --------------------------------------------------------------------------- #


def test_messina_reads_every_field_off_the_page() -> None:
    product = parsed(MESSINA)

    assert product.manufacturer_range == "Pegasus Black Edition"
    assert product.model == "Messina"
    assert product.berths == 4
    assert product.twin_axle is True
    assert product.rrp_pounds == 34499
    assert product.mtplm_kilograms == 1712
    assert product.mro_kilograms == 1552
    assert product.personal_effects_payload_kilograms == 160
    assert product.internal_length_mm == 6332
    assert product.shipping_length_mm == 7905
    assert product.overall_width_mm == 2433
    assert product.height_mm == 2582
    assert product.headroom_mm == 1960
    assert product.awning_length_mm == 10891


def test_the_spec_tables_abbreviated_range_is_corrected() -> None:
    """The requester, 3 September 2026: the brochure and page headers say "Edition"...

    ...and only the specification template drops it, so the longer form is the real name.
    Note the page's own `<h1>` and `<title>` abbreviate it too ("Pegasus Black Messina"),
    which is why this is a correction table rather than "read the heading instead".
    """
    assert parsed(MESSINA).manufacturer_range == "Pegasus Black Edition"
    assert parsed(PHOENIX_420).manufacturer_range == "Phoenix Black Edition"


def test_a_range_the_spec_table_already_spells_correctly_is_left_alone() -> None:
    assert parsed(CABRERA).manufacturer_range == "Unicorn Deluxe"
    assert parsed(DISCOVERY_D4_2).manufacturer_range == "Discovery"


def test_a_single_axle_caravan_is_not_marked_twin() -> None:
    assert parsed(DISCOVERY_D4_2).twin_axle is False
    assert parsed(CABRERA).twin_axle is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Twin", True), ("twin", True), (" Twin ", True), ("Single", False), ("", False)],
)
def test_the_axle_field_only_says_twin_when_bailey_does(value: str, expected: bool) -> None:
    """An unrecognised value understates rather than inventing a second axle."""
    html = (
        f'<div class="col-6">Axle</div><div class="col-6">{value}</div>'
        f'<div class="col-6">Model</div><div class="col-6">X</div>'
    )
    assert bailey_caravan.parse_model_page(html).twin_axle is expected


def test_awning_size_is_read_from_centimetres() -> None:
    """The one dimension Bailey give in cm, to a tenth: 1089.1cm -> 10891mm."""
    assert parsed(MESSINA).awning_length_mm == 10891
    assert parsed(PHOENIX_420).awning_length_mm == 8448


def test_a_range_that_publishes_no_awning_size_leaves_it_unset() -> None:
    """All three Discovery models omit it — and FMLV holds it blank for them too."""
    assert parsed(DISCOVERY_D4_2).awning_length_mm is None


def test_no_page_yields_an_exterior_body_length() -> None:
    """Bailey publish internal and shipping length and nothing between them.

    Out of scope in `config/field_guide_caravan.csv` as a result, so `Caravan` keeps
    whatever FMLV already holds rather than the run proposing a blank.
    """
    for name in (MESSINA, DISCOVERY_D4_2, CABRERA, PHOENIX_420):
        extracted = bailey_caravan.build_extracted(parsed(name), "https://example.test")
        assert extracted.caravan.exterior_body_length_mm is None
        assert "exterior_body_length_mm" not in extracted.provenance


# --------------------------------------------------------------------------- #
# The arithmetic self-check
# --------------------------------------------------------------------------- #


def test_payload_reconciles_on_every_fixture() -> None:
    """`Total User Payload == MTPLM - MRO` on all 23 current models."""
    for name in (MESSINA, DISCOVERY_D4_2, CABRERA, PHOENIX_420):
        assert parsed(name).payload_reconciles is True, name


def test_a_payload_that_does_not_reconcile_is_reported_not_hidden() -> None:
    product = bailey_caravan.BaileyCaravan(
        manufacturer_range="Pegasus Black Edition",
        model="Messina",
        berths=4,
        twin_axle=True,
        rrp_pounds=34499,
        mtplm_kilograms=1712,
        mro_kilograms=1552,
        personal_effects_payload_kilograms=999,
        internal_length_mm=6332,
        shipping_length_mm=7905,
        overall_width_mm=2433,
        height_mm=2582,
        headroom_mm=1960,
        awning_length_mm=10891,
    )

    assert product.payload_reconciles is False


def test_payload_reconciliation_is_unknowable_without_all_three_figures() -> None:
    product = bailey_caravan.BaileyCaravan(
        manufacturer_range="R",
        model="M",
        berths=None,
        twin_axle=False,
        rrp_pounds=None,
        mtplm_kilograms=1712,
        mro_kilograms=None,
        personal_effects_payload_kilograms=160,
        internal_length_mm=None,
        shipping_length_mm=None,
        overall_width_mm=None,
        height_mm=None,
        headroom_mm=None,
        awning_length_mm=None,
    )

    assert product.payload_reconciles is None


# --------------------------------------------------------------------------- #
# Building the canonical product
# --------------------------------------------------------------------------- #


def test_build_extracted_produces_a_caravan_not_a_motorhome() -> None:
    extracted = bailey_caravan.build_extracted(parsed(MESSINA), "https://example.test")

    assert isinstance(extracted.caravan, Caravan)
    assert extracted.product is extracted.caravan


def test_every_product_is_rigid() -> None:
    """Stated by the requester and true of all 81 Bailey caravans in FMLV.

    The micro rule never fires here: Bailey market nothing as a micro, and the models
    under 1250kg are all held as rigid.
    """
    for name in (MESSINA, DISCOVERY_D4_2, CABRERA, PHOENIX_420):
        extracted = bailey_caravan.build_extracted(parsed(name), "https://example.test")
        assert extracted.caravan.body_type is CaravanBodyType.RIGID


def test_the_body_type_and_axle_carry_provenance_even_though_asserted() -> None:
    """A reviewer should see why a value is there, not infer it from its bare presence."""
    extracted = bailey_caravan.build_extracted(parsed(MESSINA), "https://example.test")

    assert "only rigid caravans" in extracted.provenance["body_type"].snippet
    assert "Axle: Twin" in extracted.provenance["twin_axle"].snippet


def test_provenance_quotes_the_page_for_every_extracted_figure() -> None:
    extracted = bailey_caravan.build_extracted(parsed(MESSINA), "https://example.test")

    assert "£34,499" in extracted.provenance["rrp_pounds"].snippet
    assert "1712kg" in extracted.provenance["mtplm_kilograms"].snippet
    assert "7.905m" in extracted.provenance["shipping_length_mm"].snippet
    assert "1089.1cm" in extracted.provenance["awning_length_mm"].snippet
    assert all(p.source_url == "https://example.test" for p in extracted.provenance.values())


def test_a_field_the_page_omits_gets_no_provenance() -> None:
    """`diff.compare` reads a missing provenance entry as "not attempted", not "now blank"."""
    extracted = bailey_caravan.build_extracted(parsed(DISCOVERY_D4_2), "https://example.test")

    assert "awning_length_mm" not in extracted.provenance
    assert extracted.caravan.awning_length_mm is None


def test_no_layout_flag_is_guessed_from_the_marketing_copy() -> None:
    """The pages describe layouts in prose — enough to guess from, not enough to be right.

    `bailey.py` takes the same line, setting only what Bailey state outright.
    """
    extracted = bailey_caravan.build_extracted(parsed(MESSINA), "https://example.test")
    caravan = extracted.caravan

    assert caravan.sleeping_area is None
    assert caravan.bed_types == []
    assert caravan.kitchen_location is None
    assert caravan.bathroom_layout is None
    assert caravan.lounge_location is None
    assert caravan.heating is None
    assert caravan.refrigeration is None
    assert caravan.microwave is False


def test_no_caravan_carries_an_optional_equipment_payload() -> None:
    extracted = bailey_caravan.build_extracted(parsed(MESSINA), "https://example.test")

    assert extracted.caravan.optional_equipment_payload_kilograms is None
    assert "optional_equipment_payload_kilograms" not in extracted.provenance


def test_the_identity_fields_are_set_for_the_fmlv_join() -> None:
    extracted = bailey_caravan.build_extracted(parsed(CABRERA), "https://example.test")

    assert extracted.caravan.manufacturer == "Bailey"
    assert extracted.caravan.manufacturer_display_name == "Bailey"
    assert extracted.caravan.key == "Bailey Unicorn Deluxe Cabrera"
