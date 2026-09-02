"""Selectable values for single-select layout fields in the review form.

Added 2026-08-29 on the requester's suggestion: rather than leaving a new product's
`body_type` blank, propose it as a choice the reviewer makes from a list.
"""

from __future__ import annotations

from src.output.build import _ENUM_FIELDS
from src.product_model.enums import BodyType
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
