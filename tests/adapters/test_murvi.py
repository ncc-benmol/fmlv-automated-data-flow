"""Murvi's parsing functions, against real captured pages of the February 2026 price list.

No network and no PDF parsing here — `tests/fetch/test_pdf.py` covers extraction, and the
`murvi_*.txt` fixtures are what it produces. Every fixture is one page of the real document,
and each was chosen because it carries a trap the parser had to survive:

* **`ford_pimento_spec`** — `Payload  600 K gs` and `Mir f olded`, pypdf splitting words
  mid-token, and the mirrors-folded width printed *after* and *wider than* the body width.
* **`ford_pimento_xl_spec`** — `Payload 500 K gs (FWD) 340 Kgs (AWD)`, two payloads where
  only the front-wheel-drive base vehicle's counts.
* **`ford_morello_xl_spec`** — the one product on a 4,000kg GVW and the only `L4H3`.
* **`fiat_morocco_xl_spec`** — Fiat parenthesise the body code (`High Roof van (L4H2)`)
  where Ford put it inline (`MWB L2H2 High Roof`), the Elddis label trap in miniature.
* **`fiat_morello_xl_spec`** + **`fiat_morello_xl_options`** — the long-standing price
  contradiction, £79,956 against £78,596 on an identical ex-VAT figure.
* **`ford_pimento_options`** — an options page, which carries the same running header and
  the same price but no `Dimensions` block, and must not parse as a product.
* **`ford_pimento_xl_options`** — the same, and worse: it carries a stray
  `Ford Murvi Morello` header, Murvi's own layout error, which must not be read as a price
  for the Morello.
* **`price_list_page.html`** — trimmed to the block holding the one link.

See `docs/adapters/murvi.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters import murvi
from src.adapters.murvi import HIGH_TOP_ABOVE_MM, MurviSpec
from src.product_model.enums import BodyType
from src.product_model.model import Motorhome

FIXTURES = Path(__file__).parent / "fixtures"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ford_pimento() -> MurviSpec:
    spec = murvi.parse_specification_page(_text("murvi_ford_pimento_spec.txt"), 1)
    assert spec is not None
    return spec


@pytest.fixture(scope="module")
def ford_pimento_xl() -> MurviSpec:
    spec = murvi.parse_specification_page(_text("murvi_ford_pimento_xl_spec.txt"), 5)
    assert spec is not None
    return spec


@pytest.fixture(scope="module")
def ford_morello_xl() -> MurviSpec:
    spec = murvi.parse_specification_page(_text("murvi_ford_morello_xl_spec.txt"), 7)
    assert spec is not None
    return spec


@pytest.fixture(scope="module")
def fiat_morocco_xl() -> MurviSpec:
    spec = murvi.parse_specification_page(_text("murvi_fiat_morocco_xl_spec.txt"), 17)
    assert spec is not None
    return spec


@pytest.fixture(scope="module")
def fiat_morello_xl() -> MurviSpec:
    spec = murvi.parse_specification_page(_text("murvi_fiat_morello_xl_spec.txt"), 19)
    assert spec is not None
    return spec


# --- The whole spec block, on the page the docstring quotes ---------------------------------


def test_ford_pimento_reads_every_field(ford_pimento: MurviSpec) -> None:
    """The worked example from the module docstring, field by field.

    Every figure here is confirmed by FMLV's own row 7126, which holds this product's
    dimensions and its £77,290 exactly.
    """
    assert ford_pimento.make == "Ford"
    assert ford_pimento.family == "Pimento"
    assert ford_pimento.body_code == "L2H2"
    assert ford_pimento.mtplm_kilograms == 3500
    assert ford_pimento.mh_payload_kilograms == 600
    assert ford_pimento.mh_length_mm == 5531
    assert ford_pimento.mh_height_mm == 2580
    assert ford_pimento.price_inc_vat == 77290
    assert ford_pimento.price_exc_vat == 64475


def test_width_excludes_the_mirrors(ford_pimento: MurviSpec) -> None:
    """`Overall width 2.059M (6' 9") Mir folded 2.094M (6'10")` → 2059, not 2094.

    The NCC width rule excludes wing and door mirrors, and FMLV holds 2059 for every Ford
    Murvi — so the customer's own data confirms it. Note this is the first document surveyed
    where the mirrors-folded figure is the *larger* of the two, so a rule of "take the
    narrower" happens to agree here while a rule of "take the second figure" would not.
    """
    assert ford_pimento.mh_width_mm == 2059


def test_mro_is_derived_because_murvi_publish_none(ford_pimento: MurviSpec) -> None:
    """MRO = MTPLM − payload. Murvi publish no mass in running order anywhere.

    Which is exactly why `payload == MTPLM − MRO` is *not* this brand's self-check: it holds
    by construction. `_reconciles` uses the donor van's body code instead.
    """
    assert ford_pimento.mro_kilograms == 2900
    assert ford_pimento.mtplm_kilograms - ford_pimento.mro_kilograms == (
        ford_pimento.mh_payload_kilograms
    )


def test_dual_payload_takes_the_base_front_wheel_drive_figure(
    ford_pimento_xl: MurviSpec,
) -> None:
    """`Payload 500 K gs (FWD) 340 Kgs (AWD)` → 500.

    All-wheel drive is a cost option, so the base vehicle's payload is the front-wheel-drive
    one — and FMLV holds 500 for this product. Taking 340 would also have made the derived
    MRO 3160 rather than 3000.
    """
    assert ford_pimento_xl.mh_payload_kilograms == 500
    assert ford_pimento_xl.mro_kilograms == 3000


def test_the_one_four_tonne_product(ford_morello_xl: MurviSpec) -> None:
    """Ford Morello XL is the only Murvi on a 4,000kg GVW, and the only `L4H3`.

    A GVW pattern that assumed 3,500 — or a body-code pattern that assumed `H2` — would have
    parsed nine products and silently mis-weighed this one.
    """
    assert ford_morello_xl.mtplm_kilograms == 4000
    assert ford_morello_xl.body_code == "L4H3"
    assert ford_morello_xl.mro_kilograms == 3400
    assert ford_morello_xl.mh_length_mm == 6704
    assert ford_morello_xl.mh_height_mm == 2846


def test_fiat_parenthesises_the_body_code(fiat_morocco_xl: MurviSpec) -> None:
    """`Maxi XLWB 35 (3,500kg GVW) High Roof van (L4H2)` — the code comes *after* the roof.

    Ford write `MWB L2H2 High Roof van in White`, with the code before the roof. One pattern
    serves both only because the token itself is identical; anything anchored on the
    surrounding words would match one make and silently drop the other, which is the Elddis
    campervan-plural failure exactly.
    """
    assert fiat_morocco_xl.make == "Fiat"
    assert fiat_morocco_xl.body_code == "L4H2"
    assert fiat_morocco_xl.mh_length_mm == 6363
    assert fiat_morocco_xl.mh_height_mm == 2565
    assert fiat_morocco_xl.mh_width_mm == 2050


# --- Identity ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "make", "expected_range", "expected_model"),
    [
        ("Pimento", "Ford", "Pimento", "Ford"),
        ("Pimento", "Fiat", "Pimento", "Fiat"),
        ("Pimento XL", "Ford", "Pimento", "XL Ford"),
        ("Pimento XL", "Fiat", "Pimento", "XL Fiat"),
        ("Morello XL", "Fiat", "Morello", "XL Fiat"),
        ("Morocco", "Fiat", "Morocco", "Fiat"),
        ("Morocco XL", "Fiat", "Morocco", "XL Fiat"),
    ],
)
def test_identity_puts_the_chassis_in_the_model(
    family: str, make: str, expected_range: str, expected_model: str
) -> None:
    """Range is the family; model is what distinguishes the layout, then the chassis.

    So "Murvi Pimento XL Ford" and "Murvi Pimento Ford" — the requester's naming of
    2 September 2026. A layout whose name *is* its range carries the chassis alone rather
    than repeating itself, which also drops FMLV's existing `Pimento` + `Pimento` doubling.

    This is **Murvi-specific**. FMLV files a layout sold on both vans as two rows with
    identical range and model, distinguished only by `base_vehicle_manufacturer`; the
    requester was explicit that this is not a general rule and a brand doing it again comes
    back to them.
    """
    spec = MurviSpec(
        make=make,
        family=family,
        page_number=1,
        body_code="L3H2",
        mtplm_kilograms=3500,
        mh_payload_kilograms=500,
        mh_length_mm=5998,
        mh_width_mm=2050,
        mh_height_mm=2540,
        price_inc_vat=77440,
        price_exc_vat=64603,
    )
    assert spec.manufacturer_range == expected_range
    assert spec.model == expected_model


# --- Negative tests: the pages that must NOT become products -------------------------------


def test_an_options_page_is_not_a_product() -> None:
    """The options page carries the same header and the same price but no `Dimensions`.

    Identity alone therefore cannot tell a specification page from an options page, and a
    parser keying on the running header would have produced twenty products from a ten-product
    document — every layout twice, the second copy with no weights at all.
    """
    assert murvi.parse_specification_page(_text("murvi_ford_pimento_options.txt"), 2) is None


def test_the_morello_xl_options_page_is_not_a_product() -> None:
    """The page carrying the contradicting price is an options page and yields nothing."""
    assert (
        murvi.parse_specification_page(_text("murvi_fiat_morello_xl_options.txt"), 20) is None
    )


def test_a_page_missing_one_figure_is_dropped_whole(ford_pimento: MurviSpec) -> None:
    """No half-parsed products: with no MRO published, every field on the page is load-bearing.

    Removing just the payload line has to fail the whole page rather than emit a product with
    a `None` payload and, consequently, no derivable MRO.
    """
    page = _text("murvi_ford_pimento_spec.txt").replace("Payload  600 K gs", "")
    assert murvi.parse_specification_page(page, 1) is None
    assert ford_pimento.mh_payload_kilograms == 600  # unchanged by the edit above


def test_an_unknown_family_is_not_invented() -> None:
    """A family the roster does not know is dropped, not guessed at.

    `_FAMILIES` is the reconciled nav-plus-price-list roster, and a name outside it means
    either a new model (which `collect` narrates against `_EXPECTED`) or a mis-parse.
    """
    page = _text("murvi_ford_pimento_spec.txt").replace(
        "MURVI Pimento motorcaravan", "MURVI Cabernet motorcaravan"
    )
    assert murvi.parse_specification_page(page, 1) is None


# --- The self-check ------------------------------------------------------------------------


def test_siblings_on_one_donor_van_must_agree(
    ford_morello_xl: MurviSpec, ford_pimento: MurviSpec
) -> None:
    """A body code fixes the van's exterior, so two Murvis sharing one must agree.

    In the real document Ford `L3H2` covers Morello and Pimento XL at 5981x2580, Fiat `L3H2`
    covers three layouts at 5998x2540 and Fiat `L4H2` covers two at 6363x2565 — so 7 of the
    10 products are checked against a sibling. Here the Morello XL is given the Pimento's
    body code to force the clash a mis-attributed page would cause.
    """
    assert murvi._reconciles(ford_morello_xl, [ford_morello_xl, ford_pimento]) is None

    clashing = MurviSpec(**{**vars(ford_morello_xl), "body_code": "L2H2"})
    failure = murvi._reconciles(clashing, [clashing, ford_pimento])
    assert failure is not None
    assert "mis-attributed" in failure


def test_a_lone_body_code_still_passes(fiat_morocco_xl: MurviSpec) -> None:
    """A group of one cannot be cross-checked and must not be dropped for it."""
    assert murvi._reconciles(fiat_morocco_xl, [fiat_morocco_xl]) is None


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("mh_length_mm", 55310, "length"),
        ("mh_width_mm", 20590, "width"),
        ("mh_height_mm", 25800, "height"),
        ("mtplm_kilograms", 3200, "not a Murvi GVW"),
        ("mh_payload_kilograms", 60, "payload"),
    ],
)
def test_sanity_bounds_catch_a_badly_wrong_parse(
    ford_pimento: MurviSpec, field: str, value: int, expected: str
) -> None:
    """Wide bounds, there to catch a unit slip rather than to second-guess Murvi.

    A metres-to-millimetres conversion applied twice is the realistic failure, and it is what
    these numbers are sized for.
    """
    broken = MurviSpec(**{**vars(ford_pimento), field: value})
    failure = murvi._reconciles(broken, [broken])
    assert failure is not None
    assert expected in failure


def test_the_bounds_together_guarantee_a_sane_derived_mro(ford_pimento: MurviSpec) -> None:
    """The GVW and payload checks between them make a nonsensical MRO unreachable.

    MRO is derived, so a payload larger than the MTPLM would emit a negative weight. It
    cannot happen: the GVW must be one of 3500/3700/4000 and the payload at most 1200, so
    the lightest MRO any accepted product can have is 2300kg. That is why `_reconciles`
    carries no separate MRO guard — it would be dead code.
    """
    heaviest_payload = MurviSpec(
        **{**vars(ford_pimento), "mh_payload_kilograms": 1200, "mtplm_kilograms": 3500}
    )
    assert murvi._reconciles(heaviest_payload, [heaviest_payload]) is None
    assert heaviest_payload.mro_kilograms == 2300

    over = MurviSpec(**{**vars(ford_pimento), "mh_payload_kilograms": 1201})
    failure = murvi._reconciles(over, [over])
    assert failure is not None
    assert "payload" in failure


# --- The price, and the document's one real error ------------------------------------------


def test_the_price_is_confirmed_across_both_pages(ford_pimento: MurviSpec) -> None:
    """The options page repeats the price, which is the document's internal redundancy."""
    pages = [
        _text("murvi_ford_pimento_spec.txt"),
        _text("murvi_ford_pimento_options.txt"),
    ]
    messages: list[str] = []
    spec = MurviSpec(**{**vars(ford_pimento), "page_number": 1})
    assert murvi.other_page_prices(pages, spec) == [77290]
    assert murvi._price_from_pages(spec, pages, messages.append) == 77290
    assert messages == []


def test_the_morello_xl_price_contradiction_resolves_to_the_higher_figure(
    fiat_morello_xl: MurviSpec,
) -> None:
    """£79,956 from the specification page, with the disagreement narrated every run.

    Four grounds, set out in `_KNOWN_PRICE_TYPO`: Morocco XL prints £79,956 on both its pages
    and shares this product's ex-VAT £66,699, the two are the same van at the same dimensions
    and payload, FMLV holds both at one price, and three of the four printings agree. The same
    contradiction is in the October 2025 list, so it is not a fresh slip.

    Note this warns rather than dropping the product: the weights and dimensions on that page
    are sound and match FMLV exactly, so discarding the vehicle over one bad cell would lose
    good data.
    """
    pages = ["", _text("murvi_fiat_morello_xl_spec.txt"), _text("murvi_fiat_morello_xl_options.txt")]
    spec = MurviSpec(**{**vars(fiat_morello_xl), "page_number": 2})

    assert murvi.other_page_prices(pages, spec) == [78596]

    messages: list[str] = []
    assert murvi._price_from_pages(spec, pages, messages.append) == 79956
    assert len(messages) == 1
    assert messages[0].startswith("NOTE:")
    assert "79,956" in messages[0]
    assert "long-standing error" in messages[0]


def test_a_new_price_disagreement_is_warned_about_not_silently_resolved(
    ford_pimento: MurviSpec,
) -> None:
    """The override is keyed on the exact pair of figures, so it retires itself.

    If Murvi correct either page — or a different product starts disagreeing — the run must
    say so loudly rather than reuse a decision made about a different discrepancy.
    """
    pages = [
        _text("murvi_ford_pimento_spec.txt"),
        _text("murvi_ford_pimento_options.txt").replace("£64,475.00", "£64,475.00").replace(
            "77,290.00", "70,000.00"
        ),
    ]
    spec = MurviSpec(**{**vars(ford_pimento), "page_number": 1})
    messages: list[str] = []
    assert murvi._price_from_pages(spec, pages, messages.append) == 77290
    assert len(messages) == 1
    assert messages[0].startswith("WARNING:")
    assert "NEW disagreement" in messages[0]


def test_a_stray_header_only_ever_costs_a_spurious_warning() -> None:
    """Murvi's Ford Pimento XL options page carries a stray `Ford Murvi Morello` header.

    That is their layout error, not ours, and it means the Morello's price cross-check reads
    a page that is not the Morello's. The consequence is bounded and worth stating plainly
    rather than papering over: the Ford Morello and the Ford Pimento XL are both £78,598, so
    today the stray page agrees and nothing is warned about. If Murvi ever price the two
    differently, this raises a *warning* — never a wrong value, because `_price_from_pages`
    always returns the specification page's own figure and only ever narrates a disagreement.

    A tighter header pattern is not the answer: the same looseness is what lets the check
    survive pypdf corrupting five headers' first letter (`FFiat Murvi Morello`), and losing
    the cross-check entirely would cost the one defence that catches the Morello XL error.
    """
    options = _text("murvi_ford_pimento_xl_options.txt")
    assert "Murvi Morello" in options  # Murvi's stray header really is there

    morello = MurviSpec(
        make="Ford",
        family="Morello",
        page_number=3,
        body_code="L3H2",
        mtplm_kilograms=3500,
        mh_payload_kilograms=500,
        mh_length_mm=5981,
        mh_width_mm=2059,
        mh_height_mm=2580,
        price_inc_vat=78598,
        price_exc_vat=65565,
    )
    # The fixture stands in for page 6, the Pimento XL's options page; page 3 is the
    # Morello's own and is excluded by `page_number`.
    pages = ["", "", "", "", "", options]
    assert murvi.other_page_prices(pages, morello) == [78598]

    messages: list[str] = []
    assert murvi._price_from_pages(morello, pages, messages.append) == 78598
    assert messages == [], "the two prices agree today, so nothing should be narrated"


# --- The roster ----------------------------------------------------------------------------


def test_the_expected_roster_is_ten_products() -> None:
    """Murvi's own price list roster: ten spec pages, ten options pages, twenty pages exactly.

    Four families on both vans, plus Morocco and Morocco XL on the Fiat only — the Morocco
    page says "currently only based on the Fiat Ducato LWB", so the absence of a Ford Morocco
    is a fact about the range agreed by two sources, not a gap in the search.

    `Piccolo` is absent on purpose: still in the navigation and still holding a live page, but
    priced in neither the February 2026 nor the October 2025 list, unmodified since June 2021,
    and carrying model year 2024 in FMLV.
    """
    assert len(murvi._EXPECTED) == 10
    assert ("Fiat", "Morocco") in murvi._EXPECTED
    assert ("Ford", "Morocco") not in murvi._EXPECTED
    assert not any(family == "Piccolo" for _make, family in murvi._EXPECTED)
    assert "Piccolo" not in murvi._FAMILIES


def test_families_are_longest_first_so_xl_is_never_lost() -> None:
    """`Pimento XL` must be tried before `Pimento`, or every XL collapses into its base.

    The invariant: where one family name is a prefix of another, the longer must come first.
    """
    for index, family in enumerate(murvi._FAMILIES):
        for later in murvi._FAMILIES[index + 1 :]:
            assert not later.startswith(family + " "), (
                f"{later!r} is tried after {family!r}, which is its prefix"
            )


# --- Runs are per chassis ------------------------------------------------------------------


def test_the_range_selectors_are_base_vehicles() -> None:
    """Not FMLV ranges — which is the mechanism that makes this brand safe. See the module."""
    assert {label for _key, label in murvi.DEFAULT_RANGES} == {"Ford", "Fiat"}


@pytest.mark.parametrize(
    ("chassis", "labels", "expected"),
    [
        ("Fiat", {"Fiat"}, True),
        ("Ford", {"Fiat"}, False),
        ("Ford", {"Ford", "Fiat"}, True),
        (None, {"Ford", "Fiat"}, False),
    ],
)
def test_baseline_scope_is_decided_by_the_chassis(
    chassis: str | None, labels: set[str], expected: bool
) -> None:
    """`cli.baseline_scope`'s default matches `manufacturer_range` and would scope to zero.

    Scoping on the chassis is also what removes the `cli._dedupe_baseline` collapse: within
    one base vehicle no two Murvi baseline rows share a range and model, so nothing is
    discarded. Measured against the real 2026-09-02 export, `--range Fiat` matches 6 of 6
    correctly where a combined run matches 4 of 10 and writes 2 onto the wrong `product_id`.
    """
    row = Motorhome(
        manufacturer="Murvi",
        manufacturer_range="Pimento",
        model="XL",
        base_vehicle_manufacturer=chassis,
    )
    assert murvi.baseline_in_scope(row, labels) is expected


# --- Building the product ------------------------------------------------------------------


def test_every_field_set_is_also_registered(ford_pimento: MurviSpec) -> None:
    """Bürstner 27 August 2026: a set-but-unregistered field is silent in both directions.

    It is never compared against the baseline on an existing product, *and* it lands blank on
    a genuinely new one — so the two constants here (`body_type`, and the berths and seats
    read from prose) need provenance just as much as a parsed dimension does.
    """
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")

    # Compared against a bare `Motorhome` so the model's own defaults (`archived=False`,
    # the empty flag containers) are not mistaken for values this adapter chose to set.
    default = Motorhome(manufacturer=murvi.MANUFACTURER)
    claimed = {
        name
        for name, value in vars(built.motorhome).items()
        if value is not None and value != getattr(default, name, None)
    }
    unregistered = claimed - set(built.provenance)
    assert unregistered == set(), f"set but not registered: {sorted(unregistered)}"

    # And the converse: nothing is registered that was not actually set.
    assert set(built.provenance) <= claimed | {"manufacturer"}


def test_the_body_type_is_a_high_top_campervan(ford_pimento: MurviSpec) -> None:
    """Every Murvi is a factory high-roof panel van, and none offers an elevating roof.

    "pop-top" appears nowhere in the price list and the only roof option is a taller *fixed*
    one (H3), so per the 21 August 2026 rule the standard specification has no elevating
    roof. FMLV holds `type_campervan_high_top` on all 11 of its Murvi rows.
    """
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")
    assert built.motorhome.body_type is BodyType.CAMPERVAN_HIGH_TOP
    assert ford_pimento.mh_height_mm > HIGH_TOP_ABOVE_MM
    assert "elevating roof" in built.provenance["body_type"].snippet


def test_berths_and_seats_are_two_and_say_why(ford_pimento: MurviSpec) -> None:
    """Both come from prose, and the snippet carries Murvi's words rather than our reasoning.

    Rear travel seats are "the option of up to two", so the standard fitment is the two cab
    seats and four is the ceiling — the Bürstner distinction between a permitted figure and a
    fitted one. FMLV holds 2 and 2 on all 11 rows, which is the corroboration that makes the
    lower figure safe to take here.
    """
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")
    assert built.motorhome.berths == 2
    assert built.motorhome.mh_passenger_seats_inc_driver == 2
    assert "up to two rear travel seats" in (
        built.provenance["mh_passenger_seats_inc_driver"].snippet
    )


def test_both_halves_of_the_identity_say_they_belong_together(ford_pimento: MurviSpec) -> None:
    """Accepting a range rename alone corrupts the name — Bailey's `Adamo I`.

    Both halves carry provenance and both snippets say so, so a reviewer accepting one knows
    to accept the other.
    """
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")
    for field in ("manufacturer_range", "model"):
        assert "accept both or neither" in built.provenance[field].snippet


def test_the_base_vehicle_is_spelt_fmlvs_way(ford_pimento: MurviSpec) -> None:
    """Routed through `base.fmlv_base_vehicle` rather than emitted from the document."""
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")
    assert built.motorhome.base_vehicle_manufacturer == "Ford"


def test_the_derived_mro_says_it_is_derived(ford_pimento: MurviSpec) -> None:
    """A reviewer must be able to see that no document published this number."""
    built = murvi._build(ford_pimento, 77290, "https://example.invalid/list.pdf")
    snippet = built.provenance["mro_kilograms"].snippet
    assert "DERIVED" in snippet
    assert "publish no mass in running order" in snippet


# --- Finding the document ------------------------------------------------------------------


def test_the_price_list_link_is_found_on_the_page() -> None:
    assert murvi.find_price_list_url(_text("murvi_price_list_page.html")) == (
        "https://www.murvi.co.uk/wp-content/uploads/2026/02/Murvi-price-list-February-2026.pdf"
    )


def test_a_page_with_no_link_returns_none_rather_than_raising() -> None:
    """A site change is narrated as a skip by `collect`, not raised from here."""
    assert murvi.find_price_list_url("<p>Call us on 01752 892200</p>") is None


def test_a_brochure_link_is_not_mistaken_for_the_price_list() -> None:
    """The brochure page's PDF is four years old and carries no numbers at all.

    Zero occurrences of `Payload`, `Overall length`, `GVW` or a price across all 8 pages — so
    a run that picked it up would collect nothing and report a healthy zero-product sweep,
    which is Swift's failure mode.
    """
    html = (
        '<a href="https://www.murvi.co.uk/wp-content/uploads/2022/02/'
        'JAN_22_MURVI_BROCHURE.pdf">Brochure download</a>'
    )
    assert murvi.find_price_list_url(html) is None


def test_a_superseded_price_list_is_not_preferred_over_the_linked_one() -> None:
    """Eighteen superseded lists are still live, and the page's own link is the answer.

    This is Swift's lesson with the archive already in place: a filename pattern loose enough
    to match the current list matches all nineteen, and the newest by filename month is not
    reliably the newest either — "June 2025" was uploaded on 2025-07-06 and three separate
    "March 2025" lists exist. Only the link a customer is shown is trustworthy, so the
    October 2025 file must never win when it appears first in the markup.
    """
    html = (
        '<a href="https://www.murvi.co.uk/wp-content/uploads/2025/10/'
        'Murvi-price-list-October-2025.pdf">old</a>'
    )
    assert murvi.find_price_list_url(html) == (
        "https://www.murvi.co.uk/wp-content/uploads/2025/10/Murvi-price-list-October-2025.pdf"
    ), "the page's single link is taken as-is; ordering is not a defence and must not be relied on"
