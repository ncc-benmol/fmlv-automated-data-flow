"""The `product` table: persisting the identity mapping matching produces.

`diff.match_products` decides, in memory, which scraped product corresponds to which
baseline product. This module is where that decision is remembered across runs, so a
manufacturer renaming a configuration on their site doesn't make matching start over
from nothing next time (TODO.md Phase 5: "persist the mapping so a rename doesn't
create a duplicate").

Matching for `upsert_seen` prefers `fmlv_product_id` (the NCC-assigned id) when known,
since it's stable identity — DESIGN.md §4.1. A genuinely new product has no
`fmlv_product_id` yet, so it's matched on `manufacturer_range`/`model` instead, which
is all it has.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    """One product this application knows about, local to one manufacturer."""

    id: int
    manufacturer_id: int
    fmlv_product_id: int | None
    manufacturer_range: str | None
    model: str | None
    first_seen_run_id: int | None
    last_seen_run_id: int | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Product:
        return cls(
            id=row["id"],
            manufacturer_id=row["manufacturer_id"],
            fmlv_product_id=row["fmlv_product_id"],
            manufacturer_range=row["manufacturer_range"],
            model=row["model"],
            first_seen_run_id=row["first_seen_run_id"],
            last_seen_run_id=row["last_seen_run_id"],
        )


def get_product(connection: sqlite3.Connection, product_id: int) -> Product:
    """Fetch a product by its local id. Raises `KeyError` if it doesn't exist."""
    row = connection.execute("SELECT * FROM product WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        msg = f"no product with id {product_id}"
        raise KeyError(msg)
    return Product.from_row(row)


def list_products(connection: sqlite3.Connection, manufacturer_id: int) -> list[Product]:
    """List every known product for one manufacturer, by range then model."""
    rows = connection.execute(
        """
        SELECT * FROM product
        WHERE manufacturer_id = ?
        ORDER BY manufacturer_range, model
        """,
        (manufacturer_id,),
    ).fetchall()
    return [Product.from_row(row) for row in rows]


def upsert_seen(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int,
    fmlv_product_id: int | None,
    manufacturer_range: str | None,
    model: str | None,
    run_id: int,
) -> Product:
    """Record that one product was seen in `run_id`.

    Looks up an existing row first by `fmlv_product_id` (stable NCC identity), falling
    back to an exact `manufacturer_range`/`model` match for products with no
    `fmlv_product_id` yet. If found, the row is updated in place — including its
    `manufacturer_range`/`model`, so a rename is picked up rather than orphaning the
    old name — rather than inserting a duplicate. Otherwise a new row is inserted.
    """
    existing = None
    if fmlv_product_id is not None:
        existing = connection.execute(
            "SELECT * FROM product WHERE manufacturer_id = ? AND fmlv_product_id = ?",
            (manufacturer_id, fmlv_product_id),
        ).fetchone()
    if existing is None:
        existing = connection.execute(
            """
            SELECT * FROM product
            WHERE manufacturer_id = ? AND manufacturer_range IS ? AND model IS ?
            """,
            (manufacturer_id, manufacturer_range, model),
        ).fetchone()

    if existing is not None:
        connection.execute(
            """
            UPDATE product
            SET fmlv_product_id = ?, manufacturer_range = ?, model = ?, last_seen_run_id = ?
            WHERE id = ?
            """,
            (fmlv_product_id, manufacturer_range, model, run_id, existing["id"]),
        )
        connection.commit()
        return get_product(connection, existing["id"])

    cursor = connection.execute(
        """
        INSERT INTO product
            (manufacturer_id, fmlv_product_id, manufacturer_range, model,
             first_seen_run_id, last_seen_run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (manufacturer_id, fmlv_product_id, manufacturer_range, model, run_id, run_id),
    )
    connection.commit()
    assert cursor.lastrowid is not None
    return get_product(connection, cursor.lastrowid)
