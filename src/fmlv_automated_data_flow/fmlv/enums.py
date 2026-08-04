"""Grouped layout attributes from the FMLV motorhome schema.

The export represents these as ~40 independent Yes/No columns, but the field guide
(`csv-examples/field_guide_motorhome.csv`) shows they are really constrained groups:
most are "select YES against ONE option", one (bed types) is "select YES against ALL
that apply", and refrigeration is "do not put YES in both columns".

Modelling them as enums rather than booleans means an extractor picks from a closed
list, a diff reads as ``bathroom_layout: rear -> side`` instead of two boolean flips,
and the exactly-one rule is enforced by the type rather than by a check.

Each member's value is the FMLV column it expands to, so writing back is mechanical.
"""

from __future__ import annotations

from enum import Enum


class ColumnEnum(Enum):
    """An enum whose values are FMLV column names."""

    @classmethod
    def columns(cls) -> list[str]:
        return [member.value for member in cls]


class BodyType(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE 'TYPE' PER MODEL IN THIS SECTION."""

    MICRO = "type_micro"
    CAMPERVAN = "type_campervan"
    CAMPERVAN_ELEVATING_ROOF = "type_campervan_elevating_roof"
    CAMPERVAN_HIGH_TOP = "type_campervan_high_top"
    CAMPERVAN_HIGH_TOP_ELEVATING_ROOF = "type_campervan_high_top_elevating_roof"
    COACH_BUILT_LOW_PROFILE = "type_coach_built_low_profile"
    COACH_BUILT_OVER_CAB_BED = "type_coach_built_over_cab_bed"
    A_CLASS = "type_a_class"


class SleepingArea(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE 'SLEEPING AREA' OPTION."""

    FRONT = "sleeping_area_front"
    REAR = "sleeping_area_rear"
    BOTH = "sleeping_area_both"
    SEPARATE_CHILDRENS_AREA = "sleeping_area_separate_childrens_area"


class BedType(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ALL BED TYPES THAT APPLY.

    The only multi-select group in the schema.
    """

    MAKE_UP = "make_up_beds"
    FIXED = "fixed_bed"
    TRANSVERSE = "transverse_bed"
    ISLAND = "island_bed"
    FIXED_SEPARATE = "fixed_separate_beds"
    FIXED_BUNKS = "fixed_bunks"
    DROP_DOWN = "drop_down_bed"


class KitchenLocation(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE KITCHEN LOCATION."""

    REAR = "rear_kitchen"
    SIDE = "side_kitchen"
    CORNER = "corner_kitchen"


class BathroomLayout(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE BATHROOM LAYOUT."""

    NO_TOILET = "no_toilet"
    NO_SHOWER = "no_shower"
    TOILET_ONLY = "toilet_only"
    SHOWER_ONLY = "shower_only"
    REAR_SHOWER_TOILET = "rear_shower_toilet"
    SIDE_SHOWER_TOILET = "side_shower_toilet"
    SEPARATE_SHOWER_TOILET = "separate_shower_toilet"


class LoungeLocation(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE LOUNGE LOCATION."""

    FRONT = "front_lounge"
    REAR = "rear_lounge"
    TWIN = "twin_lounge"


class Heating(ColumnEnum):
    """Guide: SELECT 'YES' AGAINST ONE HEATING TYPE."""

    BLOWN_AIR = "blown_air_heating"
    WET_CENTRAL = "wet_central_heating"
    NONE = "no_heating"


class Refrigeration(ColumnEnum):
    """Guide: do not put 'YES' in both columns."""

    FRIDGE = "fridge"
    FRIDGE_FREEZER = "fridge_freezer"


#: Every single-select group, for validation and round-tripping.
SINGLE_SELECT_GROUPS: tuple[type[ColumnEnum], ...] = (
    BodyType,
    SleepingArea,
    KitchenLocation,
    BathroomLayout,
    LoungeLocation,
    Heating,
    Refrigeration,
)
