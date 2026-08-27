"""Coachman's parsing and joining, against real captured pages and API payloads.

No network here. The HTML fixture is a trim of coachman.co.uk's homepage — one caravan
section plus every motorhome section, with the sections deliberately left duplicated
because the real page renders each product twice. The JSON fixtures are the REST API's
own responses, reduced to the keys the adapter reads.

Every negative test below is a trap that actually bit, or one the 2027 range is about to
spring — see `docs/adapters/coachman.md`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters import coachman
from src.adapters.coachman import CoachmanCard, CoachmanProduct

FIXTURES = Path(__file__).parent / "fixtures"

#: Taxonomy term IDs, as Coachman's CMS numbers them.
AVVENTURA, SPORTIVO, TRAVEL_MASTER, IMPERIAL, VELOCE = 49, 9, 8, 56, 60
ACADIA = 7


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cards() -> dict[tuple[str, int, str], CoachmanCard]:
    return coachman.parse_cards(_read("coachman_homepage_cards.html"))


@pytest.fixture(scope="module")
def motorhome_ranges() -> dict[int, str]:
    return coachman.parse_ranges(_read("coachman_motorhome_model.json"))


@pytest.fixture(scope="module")
def motorhomes(motorhome_ranges: dict[int, str]) -> dict[str, CoachmanProduct]:
    roster = coachman.parse_roster(_read("coachman_motorhome.json"), "motorhome", motorhome_ranges)
    joined = coachman.join_cards(roster, coachman.parse_cards(_read("coachman_homepage_cards.html")))
    return {product.title: product for product in joined}


# --------------------------------------------------------------------------- #
# The trap this adapter exists for: a model number is not an identity
# --------------------------------------------------------------------------- #


def test_two_different_motorhomes_share_the_model_number(
    motorhomes: dict[str, CoachmanProduct],
) -> None:
    """`545` is both an Avventura and a Travel Master, 321kg and £22,305 apart.

    The homepage card for each is headed `545` and nothing else. Reading the heading alone
    merges them or gives one the other's weights — and the result would look entirely
    plausible.
    """
    avventura = motorhomes["Avventura 545"]
    travel_master = motorhomes["Travel Master 545"]

    assert avventura.model == travel_master.model == "545"
    assert avventura.range_label == "Avventura"
    assert travel_master.range_label == "Travel Master"

    assert avventura.card is not None
    assert travel_master.card is not None
    assert avventura.card.mro_kilograms == 3250
    assert travel_master.card.mro_kilograms == 3571
    assert avventura.card.rrp_pounds == 110_725
    assert travel_master.card.rrp_pounds == 133_030


def test_the_range_comes_from_the_taxonomy_term_not_the_card(
    cards: dict[tuple[str, int, str], CoachmanCard],
) -> None:
    """Two cards both headed `545`, distinguished only by the section they sit in."""
    assert ("motorhome", AVVENTURA, "545") in cards
    assert ("motorhome", TRAVEL_MASTER, "545") in cards
    assert cards[("motorhome", AVVENTURA, "545")].model == "545"
    assert cards[("motorhome", TRAVEL_MASTER, "545")].model == "545"


def test_the_join_key_is_an_exact_triple(motorhomes: dict[str, CoachmanProduct]) -> None:
    """Every product resolves to exactly one card, and to the right one."""
    assert all(product.card is not None for product in motorhomes.values())
    assert {p.card.key for p in motorhomes.values()} == {p.key for p in motorhomes.values()}


# --------------------------------------------------------------------------- #
# Model naming: the nested range names
# --------------------------------------------------------------------------- #


def test_a_nested_range_name_is_stripped_whole() -> None:
    """`Travel Master Imperial 845` must not lose only `Travel Master`.

    Trimming word by word leaves `Imperial 845`, which then matches no card — the card is
    headed `845`. The whole range name comes off, longest match first.
    """
    assert coachman.model_name("Travel Master Imperial 845", "Travel Master Imperial") == "845"
    assert coachman.model_name("Travel Master 545", "Travel Master") == "545"
    assert coachman.model_name("Avventura 565", "Avventura") == "565"


def test_the_imperial_is_identified_and_priced(motorhomes: dict[str, CoachmanProduct]) -> None:
    """It was in the 2025 line-up, absent from 2026, and is back for 2027."""
    imperial = motorhomes["Travel Master Imperial 845"]
    assert imperial.range_label == "Travel Master Imperial"
    assert imperial.model == "845"
    assert imperial.term_id == IMPERIAL
    assert imperial.card is not None
    assert imperial.card.mtplm_kilograms == 5880
    assert imperial.card.rrp_pounds == 206_650


def test_a_title_with_no_matching_range_is_kept_whole() -> None:
    """Better a wrong-looking name than a silently truncated one."""
    assert coachman.model_name("Something Else 900", "Avventura") == "Something Else 900"


# --------------------------------------------------------------------------- #
# Caravans are out of scope
# --------------------------------------------------------------------------- #


def test_caravans_are_not_in_the_default_ranges() -> None:
    """Coachman make ~20 touring caravans. Omitting the post type is the whole exclusion."""
    post_types = [post_type for post_type, _label in coachman.DEFAULT_RANGES]
    assert "caravan" not in post_types
    assert post_types == ["motorhome", "campervan"]


def test_caravan_cards_are_parsed_but_never_join_a_motorhome(
    cards: dict[tuple[str, int, str], CoachmanCard],
    motorhomes: dict[str, CoachmanProduct],
) -> None:
    """The post type is part of the join key, so a caravan cannot be picked up by mistake.

    Worth asserting rather than assuming: the caravans share the site, the homepage and the
    card markup, and an Acadia 460 is one `545` away from a motorhome in the same page.
    """
    assert ("caravan", ACADIA, "545XTRA") in cards
    assert all(product.card.kind == "motorhome" for product in motorhomes.values())


def test_a_caravan_model_number_does_not_collide_with_a_motorhomes(
    cards: dict[tuple[str, int, str], CoachmanCard],
) -> None:
    """The 2027 Acadia has a `545 Xtra` and two motorhome ranges have a `545`.

    They stay apart on two counts — the post type and the `Xtra` suffix — but the near-miss
    is why the post type is part of the key rather than an afterthought.
    """
    assert cards[("caravan", ACADIA, "545XTRA")].rrp_pounds == 35_500
    assert cards[("motorhome", AVVENTURA, "545")].rrp_pounds == 110_725
    assert cards[("motorhome", TRAVEL_MASTER, "545")].rrp_pounds == 133_030


def test_a_caravans_imperial_length_is_not_read_as_millimetres(
    cards: dict[tuple[str, int, str], CoachmanCard],
) -> None:
    """Caravan cards append the imperial equivalent: `7390mm / 24′ 3″`.

    A pattern taking the last number in the cell would record 3mm. Motorhome cards have no
    imperial suffix, so this only ever bites via the caravans — which is exactly why the
    caravan section is kept in the fixture.
    """
    assert cards[("caravan", ACADIA, "545XTRA")].mh_length_mm == 7390


# --------------------------------------------------------------------------- #
# Veloce: published, but with nothing to publish
# --------------------------------------------------------------------------- #


def test_veloce_is_in_the_roster_with_its_range() -> None:
    """The campervans exist in the CMS under their own post type and taxonomy."""
    ranges = coachman.parse_ranges(_read("coachman_campervan_model.json"))
    assert ranges == {VELOCE: "Veloce"}

    roster = coachman.parse_roster(_read("coachman_campervan.json"), "campervan", ranges)
    assert {p.title for p in roster} == {"Veloce VL 65", "Veloce VR 65"}
    assert {p.model for p in roster} == {"VL 65", "VR 65"}
    assert all(p.range_label == "Veloce" for p in roster)


def test_veloce_has_no_specification_card_yet() -> None:
    """There is no campervan section on the homepage, so there are no numbers anywhere.

    `collect` skips these with a narrated reason rather than proposing two products whose
    every field is blank.
    """
    ranges = coachman.parse_ranges(_read("coachman_campervan_model.json"))
    roster = coachman.parse_roster(_read("coachman_campervan.json"), "campervan", ranges)
    joined = coachman.join_cards(roster, coachman.parse_cards(_read("coachman_homepage_cards.html")))
    assert all(product.card is None for product in joined)
    assert all(not coachman._reconciles(product) for product in joined)


# --------------------------------------------------------------------------- #
# Counts, against Coachman's own CMS
# --------------------------------------------------------------------------- #


def test_the_taxonomy_counts_match_the_roster(motorhome_ranges: dict[int, str]) -> None:
    """Coachman's CMS reports a product count per range — a free completeness check."""
    counts = coachman.parse_range_counts(_read("coachman_motorhome_model.json"))
    assert counts == {AVVENTURA: 2, SPORTIVO: 1, TRAVEL_MASTER: 2, IMPERIAL: 1}
    assert sum(counts.values()) == 6

    roster = coachman.parse_roster(_read("coachman_motorhome.json"), "motorhome", motorhome_ranges)
    for term, expected in counts.items():
        assert sum(1 for p in roster if p.term_id == term) == expected


def test_every_product_is_rendered_twice_and_deduplicated(
    cards: dict[tuple[str, int, str], CoachmanCard],
) -> None:
    """The homepage repeats each product; the fixture keeps the duplication deliberately."""
    motorhome_cards = [key for key in cards if key[0] == "motorhome"]
    assert len(motorhome_cards) == 6


# --------------------------------------------------------------------------- #
# Value parsing
# --------------------------------------------------------------------------- #


def test_price_drops_the_on_the_road_footnote_marker() -> None:
    """`£110,725.00*` — the asterisk footnotes the OTR basis, not a price."""
    assert coachman._pounds("£110,725.00*") == 110_725
    assert coachman._pounds("£206,650.00*") == 206_650
    assert coachman._pounds("") is None


def test_weights_parse_with_or_without_a_space() -> None:
    """Coachman are inconsistent: `4500 kg` on motorhomes, `1343kg` on caravans."""
    assert coachman._kilograms("4500 kg") == 4500
    assert coachman._kilograms("1343kg") == 1343
    assert coachman._kilograms("") is None


def test_a_weight_published_as_tbc_reads_as_absent() -> None:
    """Coachman ship the 2027 range with `TBC` where a weight is not settled yet.

    Their 2027 Acadia cards do exactly this. `TBC` must become an absent value, never a
    zero and never an exception — the missing-data rule then makes the gap visible.
    """
    assert coachman._kilograms("TBC") is None
    assert coachman._millimetres("TBC") is None
    assert coachman._pounds("TBC") is None


def test_a_product_with_tbc_weights_is_proposed_not_dropped(
    cards: dict[tuple[str, int, str], CoachmanCard],
) -> None:
    """A gap is a gap, not a contradiction.

    The 2027 caravan cards carry a price and a length but `TBC` weights. Were a motorhome
    published the same way it must still come through, with the weights blank and reported,
    rather than being dropped for failing a check it cannot answer.
    """
    tbc = cards[("caravan", ACADIA, "545XTRA")]
    assert tbc.mtplm_kilograms is None
    assert tbc.mro_kilograms is None
    assert tbc.rrp_pounds == 35_500  # what it does publish still comes through

    product = CoachmanProduct(
        kind="motorhome", term_id=AVVENTURA, range_label="Avventura", model="545",
        title="Avventura 545", slug="avventura-545",
        card=replace(tbc, kind="motorhome", term_id=AVVENTURA, model="545"),
    )
    assert coachman._reconciles(product)
    assert product.mh_payload_kilograms is None


def test_lengths_parse_with_or_without_a_space() -> None:
    assert coachman._millimetres("7996 mm") == 7996
    assert coachman._millimetres("7445mm") == 7445


def test_payload_is_derived_because_coachman_publish_none(
    motorhomes: dict[str, CoachmanProduct],
) -> None:
    sportivo = motorhomes["Sportivo 565"]
    assert sportivo.card.mtplm_kilograms == 3500
    assert sportivo.card.mro_kilograms == 3020
    assert sportivo.mh_payload_kilograms == 480


# --------------------------------------------------------------------------- #
# The self-check
# --------------------------------------------------------------------------- #


def test_all_six_motorhomes_reconcile(motorhomes: dict[str, CoachmanProduct]) -> None:
    assert len(motorhomes) == 6
    assert all(coachman._reconciles(product) for product in motorhomes.values())


def test_a_running_order_above_the_maximum_weight_is_rejected() -> None:
    """What a slipped term ID looks like: one range's MRO against another's MTPLM."""
    slipped = CoachmanProduct(
        kind="motorhome",
        term_id=SPORTIVO,
        range_label="Sportivo",
        model="565",
        title="Sportivo 565",
        slug="sportivo-565",
        card=CoachmanCard(
            kind="motorhome",
            term_id=SPORTIVO,
            model="565",
            mtplm_kilograms=3500,
            mro_kilograms=5147,  # the Imperial's running order
        ),
    )
    assert not coachman._reconciles(slipped)


def test_an_implausible_payload_is_rejected() -> None:
    """A card paired with the wrong vehicle can still order correctly but be far out."""
    absurd = CoachmanProduct(
        kind="motorhome",
        term_id=AVVENTURA,
        range_label="Avventura",
        model="545",
        title="Avventura 545",
        slug="avventura-545",
        card=CoachmanCard(
            kind="motorhome", term_id=AVVENTURA, model="545",
            mtplm_kilograms=5880, mro_kilograms=3250,
        ),
    )
    assert absurd.mh_payload_kilograms == 2630
    assert not coachman._reconciles(absurd)


def test_missing_weights_do_not_fail_the_check(motorhomes: dict[str, CoachmanProduct]) -> None:
    """A gap is reported as a missing field, not treated as a contradiction."""
    partial = CoachmanProduct(
        kind="motorhome", term_id=AVVENTURA, range_label="Avventura", model="545",
        title="Avventura 545", slug="avventura-545",
        card=CoachmanCard(kind="motorhome", term_id=AVVENTURA, model="545", rrp_pounds=110_725),
    )
    assert coachman._reconciles(partial)
    assert partial.mh_payload_kilograms is None


# --------------------------------------------------------------------------- #
# Base vehicle: transcribed from a document, not fetched
# --------------------------------------------------------------------------- #


def test_base_vehicle_comes_from_the_range_not_the_model() -> None:
    """Coachman state the chassis per range, and that is the safer granularity.

    It also means the three unpublished 2027 models inherit the right chassis the moment
    they appear — Sportivo 565 Compact and 565 TRAQ are Mercedes because Sportivo is,
    despite the TRAQ having a different weight and a 4x4 engine.
    """
    assert coachman.base_vehicle_for("Avventura") == "Fiat"
    assert coachman.base_vehicle_for("Veloce") == "Fiat"
    # FMLV holds `Mercedes`, never `Mercedes-Benz` - see docs/adapters/README.md.
    assert coachman.base_vehicle_for("Sportivo") == "Mercedes"
    assert coachman.base_vehicle_for("Travel Master") == "Mercedes"
    assert coachman.base_vehicle_for("Travel Master Imperial") == "Mercedes"


def test_an_unknown_range_gets_no_base_vehicle() -> None:
    """A range added since the preview was read must not be given an invented chassis."""
    assert coachman.base_vehicle_for("Something New") is None
    assert coachman.base_vehicle_for("") is None


def test_the_base_vehicle_reaches_the_product_and_is_flagged_as_manual(
    motorhomes: dict[str, CoachmanProduct],
) -> None:
    """It is not fetchable, so the reviewer must be told where it came from."""
    extracted = coachman._build_extracted_motorhome(
        motorhomes["Sportivo 565"], "https://www.coachman.co.uk/", "https://example.invalid/api"
    )
    assert extracted.motorhome.base_vehicle_manufacturer == "Mercedes"

    snippet = extracted.provenance["base_vehicle_manufacturer"].snippet
    assert "MANUALLY SOURCED" in snippet
    assert "2027 preview" in snippet
    assert "not refreshed by later runs" in snippet
    assert "re-verify at the next model-year changeover" in snippet


def test_manufacturer_matches_the_registry_key() -> None:
    """`MANUFACTURER` is the `ADAPTERS` key and must equal `fmlv_manufacturer` exactly."""
    assert coachman.MANUFACTURER == "Coachman"
