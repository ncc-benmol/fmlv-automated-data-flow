"""Tests for the `product` table: persisting the identity mapping matching produces."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import store
from src.vehicle_class import VehicleClass


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = store.connect(tmp_path / "runs.db")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def run_id(connection: sqlite3.Connection) -> int:
    run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    return run.id


def test_upsert_seen_inserts_a_new_product(
    connection: sqlite3.Connection, run_id: int
) -> None:
    product = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        run_id=run_id,
    )
    assert product.fmlv_product_id == 101
    assert product.first_seen_run_id == run_id
    assert product.last_seen_run_id == run_id


def test_upsert_seen_again_updates_last_seen_not_a_duplicate(
    connection: sqlite3.Connection, run_id: int
) -> None:
    first = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        run_id=run_id,
    )
    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    second = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        run_id=second_run.id,
    )

    assert second.id == first.id
    assert second.first_seen_run_id == run_id
    assert second.last_seen_run_id == second_run.id
    assert len(store.list_products(connection, manufacturer_id=3)) == 1


def test_upsert_seen_persists_a_rename_without_creating_a_duplicate(
    connection: sqlite3.Connection, run_id: int
) -> None:
    first = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="670 DC Supreme Alde RHD",
        run_id=run_id,
    )
    renamed = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="670 DC Supreme Alde RHD 2027",
        run_id=run_id,
    )

    assert renamed.id == first.id
    assert renamed.model == "670 DC Supreme Alde RHD 2027"
    assert len(store.list_products(connection, manufacturer_id=3)) == 1


def test_upsert_seen_without_fmlv_id_matches_on_range_and_model(
    connection: sqlite3.Connection, run_id: int
) -> None:
    first = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=None,
        manufacturer_range="Coral",
        model="Axess 600 SP",
        run_id=run_id,
    )
    second_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    seen_again = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=None,
        manufacturer_range="Coral",
        model="Axess 600 SP",
        run_id=second_run.id,
    )

    assert seen_again.id == first.id
    assert seen_again.last_seen_run_id == second_run.id


def test_upsert_seen_assigns_fmlv_id_once_the_new_product_is_uploaded(
    connection: sqlite3.Connection, run_id: int
) -> None:
    new_product = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=None,
        manufacturer_range="Coral",
        model="Axess 600 SP",
        run_id=run_id,
    )
    later_run = store.start_run(
        connection, manufacturer_id=3, fmlv_manufacturer="Adria Mobil", trigger="manual"
    )
    now_uploaded = store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=555,
        manufacturer_range="Coral",
        model="Axess 600 SP",
        run_id=later_run.id,
    )

    assert now_uploaded.id == new_product.id
    assert now_uploaded.fmlv_product_id == 555
    assert len(store.list_products(connection, manufacturer_id=3)) == 1


def test_a_rename_onto_a_phantom_absorbs_it_instead_of_failing(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """The Chausson case: FMLV renames a product to the name a phantom row already holds.

    A product first seen while absent from FMLV is stored under the manufacturer's own name
    with no `fmlv_product_id`. When the NCC renames the real product to match, the run
    arrives with both a real id and that same name. Before this was handled the `UPDATE`
    tripped `UNIQUE (manufacturer_id, manufacturer_range, model)` and the run died with a
    bare `IntegrityError` — on 16 products at once, in the real case.
    """
    phantom = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=None,
        manufacturer_range="Low profiles",
        model="650",
        run_id=run_id,
    )
    real = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=1648,
        manufacturer_range="Titanium",
        model="650",
        run_id=run_id,
    )
    assert phantom.id != real.id

    renamed = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=1648,
        manufacturer_range="Low profiles",
        model="650",
        run_id=run_id,
    )

    assert renamed.id == real.id  # the row with the FMLV identity is the one that survives
    assert renamed.fmlv_product_id == 1648
    assert renamed.manufacturer_range == "Low profiles"
    remaining = store.list_products(connection, manufacturer_id=53)
    assert len(remaining) == 1


def test_absorbing_a_phantom_keeps_its_review_history(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """A reviewer's proposed changes must follow the merge, not vanish with the phantom."""
    phantom = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=None,
        manufacturer_range="X",
        model="X550",
        run_id=run_id,
    )
    change = store.record_proposed_change(
        connection,
        run_id=run_id,
        product_id=phantom.id,
        field="rrp_pounds",
        old_value=None,
        new_value="73990",
    )
    store.record_verification(connection, run_id=run_id, product_id=phantom.id, field="berths")
    real = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=7419,
        manufacturer_range="Exclusive",
        model="X550",
        run_id=run_id,
    )

    store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=7419,
        manufacturer_range="X",
        model="X550",
        run_id=run_id,
    )

    assert store.get_proposed_change(connection, change.id).product_id == real.id
    moved = connection.execute(
        "SELECT product_id FROM verification WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert moved["product_id"] == real.id


def test_a_retired_product_gives_up_the_name_it_is_holding(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """The day-after case: the row holding the name has since been archived in FMLV.

    Chausson had two live products called `Low profiles 640`. Product 1612 won the baseline
    dedupe and took the name locally, was then archived in FMLV, and 5554 — the one the NCC
    kept — could not take the name it now holds on its own. A row not seen in this run is out
    of the baseline, so it yields the name rather than blocking the run.
    """
    retired = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=1612,
        manufacturer_range="Low profiles",
        model="640",
        run_id=run_id,
    )
    later = store.start_run(
        connection, manufacturer_id=53, fmlv_manufacturer="Trigano VDL Chausson", trigger="manual"
    )
    kept = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=5554,
        manufacturer_range="Titanium",
        model="640",
        run_id=later.id,
    )

    renamed = store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=5554,
        manufacturer_range="Low profiles",
        model="640",
        run_id=later.id,
    )

    assert renamed.id == kept.id
    assert renamed.model == "640"
    # The retired row keeps its FMLV identity, which is how it is found, and says why it
    # no longer holds the name.
    still_there = store.get_product(connection, retired.id)
    assert still_there.fmlv_product_id == 1612
    assert still_there.model == "640 (superseded by 5554)"


def test_two_real_products_sharing_a_name_is_an_error_worth_reading(
    connection: sqlite3.Connection, run_id: int
) -> None:
    """No local surgery can fix two live FMLV products with one name, so say so plainly.

    This is the other half of the Chausson rename: five layouts had two trim variants each,
    and renaming both to the manufacturer's single name would have collided. The message
    names both products, where the raw `IntegrityError` named only the columns.
    """
    store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=5559,
        manufacturer_range="S Low Profiles",
        model="S514",
        run_id=run_id,
    )
    store.upsert_seen(
        connection,
        manufacturer_id=53,
        fmlv_product_id=5560,
        manufacturer_range="Sport",
        model="S514",
        run_id=run_id,
    )

    with pytest.raises(store.ProductIdentityConflict) as caught:
        store.upsert_seen(
            connection,
            manufacturer_id=53,
            fmlv_product_id=5560,
            manufacturer_range="S Low Profiles",
            model="S514",
            run_id=run_id,
        )

    message = str(caught.value)
    assert "5559" in message and "5560" in message
    assert "archive or rename one of them" in message
    assert "in this run" in message  # both were seen in it, so both are live


def test_get_product_raises_for_unknown_id(connection: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        store.get_product(connection, 999)


def test_list_products_filters_by_manufacturer(
    connection: sqlite3.Connection, run_id: int
) -> None:
    store.upsert_seen(
        connection,
        manufacturer_id=3,
        fmlv_product_id=101,
        manufacturer_range="Matrix",
        model="Supreme 670 DC",
        run_id=run_id,
    )
    other_run = store.start_run(
        connection, manufacturer_id=46, fmlv_manufacturer="Morelo", trigger="manual"
    )
    store.upsert_seen(
        connection,
        manufacturer_id=46,
        fmlv_product_id=202,
        manufacturer_range="Empire",
        model="Liberty",
        run_id=other_run.id,
    )

    adria_products = store.list_products(connection, manufacturer_id=3)
    assert len(adria_products) == 1
    assert adria_products[0].fmlv_product_id == 101


def test_the_same_range_and_model_in_two_product_areas_are_two_products(
    connection: sqlite3.Connection,
) -> None:
    """A caravan named like a motorhome is a different vehicle, not the same one.

    Bailey's two line-ups don't currently share a single range or model name, and nor do
    Adria's — but the identity key must not depend on that luck holding for every brand.
    """
    run = store.start_run(
        connection, manufacturer_id=28, fmlv_manufacturer="Bailey", trigger="manual"
    )
    motorhome = store.upsert_seen(
        connection,
        manufacturer_id=28,
        fmlv_product_id=None,
        manufacturer_range="Discovery",
        model="D4-4",
        run_id=run.id,
        vehicle_class=VehicleClass.MOTORHOME,
    )
    caravan = store.upsert_seen(
        connection,
        manufacturer_id=28,
        fmlv_product_id=None,
        manufacturer_range="Discovery",
        model="D4-4",
        run_id=run.id,
        vehicle_class=VehicleClass.CARAVAN,
    )

    assert motorhome.id != caravan.id
    assert motorhome.vehicle_class is VehicleClass.MOTORHOME
    assert caravan.vehicle_class is VehicleClass.CARAVAN


def test_upsert_seen_still_matches_within_one_product_area(
    connection: sqlite3.Connection,
) -> None:
    run = store.start_run(
        connection, manufacturer_id=28, fmlv_manufacturer="Bailey", trigger="manual"
    )
    first = store.upsert_seen(
        connection,
        manufacturer_id=28,
        fmlv_product_id=None,
        manufacturer_range="Unicorn Deluxe",
        model="Cabrera",
        run_id=run.id,
        vehicle_class=VehicleClass.CARAVAN,
    )
    again = store.upsert_seen(
        connection,
        manufacturer_id=28,
        fmlv_product_id=None,
        manufacturer_range="Unicorn Deluxe",
        model="Cabrera",
        run_id=run.id,
        vehicle_class=VehicleClass.CARAVAN,
    )

    assert first.id == again.id


def test_list_products_can_scope_to_one_product_area(connection: sqlite3.Connection) -> None:
    run = store.start_run(
        connection, manufacturer_id=28, fmlv_manufacturer="Bailey", trigger="manual"
    )
    for vehicle_class, model in (
        (VehicleClass.MOTORHOME, "60-2"),
        (VehicleClass.CARAVAN, "Cabrera"),
    ):
        store.upsert_seen(
            connection,
            manufacturer_id=28,
            fmlv_product_id=None,
            manufacturer_range="R",
            model=model,
            run_id=run.id,
            vehicle_class=vehicle_class,
        )

    everything = store.list_products(connection, 28)
    caravans = store.list_products(connection, 28, vehicle_class=VehicleClass.CARAVAN)

    assert len(everything) == 2
    assert [product.model for product in caravans] == ["Cabrera"]
