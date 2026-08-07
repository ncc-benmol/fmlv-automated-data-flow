"""Unit tests for validation rules, independent of any real export file."""

from __future__ import annotations

from src.product_model import validation
from src.product_model.enums import (
    BathroomLayout,
    BodyType,
    Heating,
    KitchenLocation,
    LoungeLocation,
    SleepingArea,
)
from src.product_model.model import AutomaticVariant, Motorhome

BASE_FIELDS = {
    "manufacturer": "Adria Mobil",
    "base_vehicle_manufacturer": "Fiat",
    "manufacturer_display_name": "Adria",
    "manufacturer_range": "TWIN",
    "model": "Supreme 640 SLB",
    "mh_passenger_seats_inc_driver": 4,
    "berths": 2,
    "rrp_pounds": 75950,
    "mro_kilograms": 2944,
    "mtplm_kilograms": 3500,
    "mh_payload_kilograms": 556,
    "mh_length_mm": 6363,
    "mh_width_mm": 2050,
    "mh_height_mm": 2600,
    "body_type": BodyType.CAMPERVAN_HIGH_TOP,
    "sleeping_area": SleepingArea.BOTH,
    "kitchen_location": KitchenLocation.SIDE,
    "bathroom_layout": BathroomLayout.SIDE_SHOWER_TOILET,
    "lounge_location": LoungeLocation.FRONT,
    "heating": Heating.BLOWN_AIR,
}


def make_motorhome(**overrides: object) -> Motorhome:
    fields = {**BASE_FIELDS, **overrides}
    return Motorhome(**fields)


def test_complete_product_has_no_issues() -> None:
    motorhome = make_motorhome()
    assert validation.validate(motorhome) == []


def test_missing_required_field_is_an_error() -> None:
    motorhome = make_motorhome(rrp_pounds=None)
    issues = validation.validate(motorhome)
    errors = [i for i in issues if i.severity == "error"]
    assert len(errors) == 1
    assert errors[0].code == "missing_required"
    assert errors[0].field == "rrp_pounds"


def test_payload_mismatch_is_a_warning_not_an_error() -> None:
    motorhome = make_motorhome(mh_payload_kilograms=999)
    issues = validation.validate(motorhome)
    assert [i.code for i in issues] == ["payload_mismatch"]
    assert issues[0].severity == "warning"


def test_partial_automatic_variant_is_flagged() -> None:
    motorhome = make_motorhome(
        automatic=AutomaticVariant(rrp_pounds=80095)  # the other three left blank
    )
    issues = validation.validate(motorhome)
    assert any(i.code == "automatic_partial" for i in issues)


def test_complete_automatic_variant_with_correct_payload_is_clean() -> None:
    motorhome = make_motorhome(
        automatic=AutomaticVariant(
            mro_kilograms=2972,
            payload_kilograms=528,
            rrp_pounds=80095,
            price_min_range_pounds=80095,
        )
    )
    assert validation.validate(motorhome) == []


def test_automatic_payload_mismatch_is_flagged() -> None:
    motorhome = make_motorhome(
        automatic=AutomaticVariant(
            mro_kilograms=2972,
            payload_kilograms=999,  # should be 3500 - 2972 = 528
            rrp_pounds=80095,
            price_min_range_pounds=80095,
        )
    )
    issues = validation.validate(motorhome)
    assert any(i.code == "automatic_payload_mismatch" for i in issues)


def test_unset_layout_group_is_a_warning() -> None:
    motorhome = make_motorhome(heating=None)
    issues = validation.validate(motorhome)
    assert any(i.code == "layout_group_unset" and i.field == "heating" for i in issues)


def test_refrigeration_left_unset_is_not_flagged() -> None:
    # Guide: "do not put YES in both columns" — neither is a valid state, unlike the
    # other single-select groups which the guide phrases as "select one".
    motorhome = make_motorhome(refrigeration=None)
    issues = validation.validate(motorhome)
    assert not any(i.field == "refrigeration" for i in issues)


def test_validate_all_aggregates_across_products() -> None:
    good = make_motorhome()
    bad = make_motorhome(rrp_pounds=None)
    issues = validation.validate_all([good, bad])
    assert len(issues) == 1
    assert issues[0].product_key == bad.key


def test_format_issues_is_empty_for_no_issues() -> None:
    assert validation.format_issues([]) == ""


def test_format_issues_renders_one_readable_line_per_issue() -> None:
    bad = make_motorhome(rrp_pounds=None)
    issues = validation.validate(bad)
    text = validation.format_issues(issues)
    assert text.endswith("\n")
    lines = text.splitlines()
    assert len(lines) == len(issues)
    assert lines[0].startswith("[ERROR]")
    assert bad.key in lines[0]
    assert "rrp_pounds" in lines[0]
    assert "required field" in lines[0]
