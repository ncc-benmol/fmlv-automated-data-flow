"""Tests for the `product` table: persisting the identity mapping matching produces."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import store


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
