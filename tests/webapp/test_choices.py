"""Selectable values for single-select layout fields in the review form.

Added 2026-08-29 on the requester's suggestion: rather than leaving a new product's
`body_type` blank, propose it as a choice the reviewer makes from a list.
"""

from __future__ import annotations

from src.output.build import _ENUM_FIELDS
from src.product_model.enums import BodyType
from src.vehicle_class import VehicleClass
from src.webapp import choices


def test_body_types_are_offered_in_two_groups() -> None:
    """The requester asked for the campervan types and the coachbuilt types apart."""
    groups = dict(choices.field_choices("body_type"))

    assert set(groups) == {"Campervan", "Motorhome"}
    assert [value for value, _label in groups["Motorhome"]] == [
        BodyType.COACH_BUILT_LOW_PROFILE.value,
        BodyType.COACH_BUILT_OVER_CAB_BED.value,
        BodyType.A_CLASS.value,
    ]
    assert BodyType.CAMPERVAN_HIGH_TOP_ELEVATING_ROOF.value in [
        value for value, _label in groups["Campervan"]
    ]


def test_every_body_type_is_offered_exactly_once() -> None:
    offered = [value for _group, options in choices.field_choices("body_type") for value, _ in options]

    assert sorted(offered) == sorted(member.value for member in BodyType)


def test_every_enum_field_is_selectable() -> None:
    """Not just `body_type` — the other six single-selects get a list too."""
    for field in _ENUM_FIELDS:
        assert choices.field_choices(field), field


def test_a_non_enum_field_has_no_choices() -> None:
    """An empty list is what makes the form fall back to its free-text box.

    Every other field, and every other adapter, must be unaffected by this feature.
    """
    for field in ("mtplm_kilograms", "rrp_pounds", "model", "mh_height_mm"):
        assert choices.field_choices(field) == []


def test_labels_are_readable_rather_than_column_names() -> None:
    assert choices.label_for("type_campervan_high_top_elevating_roof") == (
        "Campervan — high top, elevating roof"
    )
    assert choices.label_for(None) == "—"
    assert choices.label_for("") == "—"


def test_an_unknown_value_falls_back_to_itself() -> None:
    # A value the label table doesn't know is shown, not swallowed.
    assert choices.label_for("type_something_new") == "type_something_new"


def test_valid_choices_are_recognised_and_others_are_not() -> None:
    assert choices.is_valid_choice("body_type", "type_a_class")
    assert not choices.is_valid_choice("body_type", "type_a_clas")
    assert not choices.is_valid_choice("body_type", "")
    # A field with no choices accepts nothing through this route, by construction.
    assert not choices.is_valid_choice("rrp_pounds", "12345")


def test_every_offered_value_survives_a_round_trip_into_the_model() -> None:
    """The point of the dropdown: what it submits must be applicable at upload time.

    A typo in the old free-text box only failed later, in `build.apply_field`.
    """
    from src.output.build import apply_field
    from src.product_model.model import Motorhome

    base = Motorhome(manufacturer="X", manufacturer_display_name="X", model="Y")
    for field, enum_cls in _ENUM_FIELDS.items():
        for _group, options in choices.field_choices(field):
            for value, _label in options:
                applied = apply_field(base, field, value)
                assert getattr(applied, field) == enum_cls(value)


# --------------------------------------------------------------------------- #
# "Leave blank" — which fields may be cleared
# --------------------------------------------------------------------------- #


def test_a_measurement_can_be_left_blank() -> None:
    """The case that prompted it: Swift withdrew these four for 2027."""
    for field in (
        "internal_length_mm",
        "height_mm",
        "awning_length_mm",
        "personal_effects_payload_kilograms",
    ):
        assert choices.can_be_blanked(field, VehicleClass.CARAVAN), field


def test_a_classification_can_be_left_blank() -> None:
    """An enum's empty state is a real one — no column ticked."""
    assert choices.can_be_blanked("body_type", VehicleClass.CARAVAN)
    assert choices.can_be_blanked("sleeping_area", VehicleClass.CARAVAN)


def test_a_boolean_cannot_be_left_blank() -> None:
    """`apply_field` writes `False` for an absent boolean, and FMLV holds that as `No`.

    So "leave blank" on an axle count would quietly assert *single axle* rather than
    *unknown* — a worse answer than the figure it replaced.
    """
    assert not choices.can_be_blanked("twin_axle", VehicleClass.CARAVAN)
    assert not choices.can_be_blanked("microwave", VehicleClass.CARAVAN)


def test_the_product_identity_cannot_be_left_blank() -> None:
    """Clearing one half of the name takes the row below the matcher's threshold and
    orphans its FMLV product id — see `docs/adapters/README.md` on renames."""
    for field in ("manufacturer", "manufacturer_display_name", "manufacturer_range", "model"):
        assert not choices.can_be_blanked(field, VehicleClass.CARAVAN), field


def test_bed_types_cannot_be_left_blank() -> None:
    """A list's empty state is `[]`, so "none recorded" and "has no beds" would
    serialise identically. Kept distinct until someone asks for it."""
    assert not choices.can_be_blanked("bed_types", VehicleClass.MOTORHOME)


def test_blankability_is_per_product_area() -> None:
    """A caravan has no base vehicle and a motorhome has no awning rail."""
    assert choices.can_be_blanked("awning_length_mm", VehicleClass.CARAVAN)
    assert not choices.can_be_blanked("awning_length_mm", VehicleClass.MOTORHOME)


def test_the_withdrawn_swift_fields_are_all_required_columns() -> None:
    """Why the button carries a warning.

    Every field Swift withdrew for 2027 is a required column, so clearing one leaves
    `validation.check_caravan` reporting the row as missing it. That report is correct —
    the row really does now have a gap FMLV expects filled — but the reviewer should meet
    it at review time, not hours later at upload.
    """
    for field in (
        "internal_length_mm",
        "height_mm",
        "awning_length_mm",
        "personal_effects_payload_kilograms",
    ):
        assert choices.can_be_blanked(field, VehicleClass.CARAVAN), field
        assert choices.is_required_field(field, VehicleClass.CARAVAN), field


def test_a_blankable_field_is_not_always_required() -> None:
    """So the warning distinguishes rather than decorating every button."""
    assert choices.can_be_blanked("body_type", VehicleClass.CARAVAN)
    assert not choices.is_required_field("body_type", VehicleClass.CARAVAN)


def test_required_is_read_per_product_area() -> None:
    assert choices.is_required_field("shipping_length_mm", VehicleClass.CARAVAN)
    assert not choices.is_required_field("shipping_length_mm", VehicleClass.MOTORHOME)
