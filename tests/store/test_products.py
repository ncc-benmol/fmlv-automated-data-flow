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
