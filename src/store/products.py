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

from ..vehicle_class import DEFAULT as DEFAULT_VEHICLE_CLASS
from ..vehicle_class import VehicleClass


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
    #: Which FMLV product area this product belongs to. Part of its identity, not a
    #: label: the same range/model name in the other area is a different vehicle.
    vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS

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
            vehicle_class=VehicleClass(row["vehicle_class"]),
        )


def get_product(connection: sqlite3.Connection, product_id: int) -> Product:
    """Fetch a product by its local id. Raises `KeyError` if it doesn't exist."""
    row = connection.execute("SELECT * FROM product WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        msg = f"no product with id {product_id}"
        raise KeyError(msg)
    return Product.from_row(row)


def list_products(
    connection: sqlite3.Connection,
    manufacturer_id: int,
    *,
    vehicle_class: VehicleClass | None = None,
) -> list[Product]:
    """List known products for one manufacturer, by range then model.

    `vehicle_class` defaults to `None` — every product area — so a caller wanting "all of
    Bailey" still gets it. Pass one to scope to a single area, which is what a run does.
    """
    clauses = ["manufacturer_id = ?"]
    params: list[object] = [manufacturer_id]
    if vehicle_class is not None:
        clauses.append("vehicle_class = ?")
        params.append(VehicleClass(vehicle_class).value)
    joined = " AND ".join(clauses)
    rows = connection.execute(
        f"SELECT * FROM product WHERE {joined} ORDER BY manufacturer_range, model",  # noqa: S608
        params,
    ).fetchall()
    return [Product.from_row(row) for row in rows]


#: Tables holding a row per product, which have to follow the product when one is absorbed.
_PRODUCT_CHILD_TABLES = ("proposed_change", "verification", "disappearance_notice")


class ProductIdentityConflict(Exception):
    """Two products with different `fmlv_product_id`s claim one range/model name.

    Raised instead of letting sqlite's
    `UNIQUE (manufacturer_id, vehicle_class, manufacturer_range, model)` surface as a bare
    `IntegrityError`, because the fix is on the FMLV side and the message needs to say
    which two products are involved.
    """


def _absorb_clash(
    connection: sqlite3.Connection,
    *,
    keeping: int,
    manufacturer_id: int,
    manufacturer_range: str | None,
    model: str | None,
    run_id: int,
    vehicle_class: VehicleClass,
) -> None:
    """Clear the way for `keeping` to take a name another local row already holds.

    This is what a **rename in FMLV** looks like from here. A product first seen while it
    was absent from FMLV is stored under the manufacturer's own name with no
    `fmlv_product_id`; when the NCC later adds it — or renames the existing product to
    match the manufacturer — the run arrives holding both a real `fmlv_product_id` and
    that same name, and the two rows are the same vehicle. Without this the `UPDATE` in
    `upsert_seen` trips the unique constraint and the whole run dies with an
    `IntegrityError` naming only the columns, which is a long way from "somebody renamed a
    product". Chausson's 2026 rename hit exactly this, on 16 products at once.

    The row with no `fmlv_product_id` is the one to give up: it never had an identity of
    its own. Its proposed changes, verifications and disappearance notices are re-pointed
    at the surviving row first, so a reviewer's history survives the merge, and any
    decisions follow their changes untouched.

    Two rows that both carry an `fmlv_product_id` are a different matter, and which one it
    is turns on whether the clashing row has been seen in **this** run:

    * **Seen this run** — two live FMLV products really do share one name, which no local
      surgery can resolve, so this raises `ProductIdentityConflict`.
    * **Not seen this run** — the clashing product has left the baseline, archived or
      retired, and is holding a name the live product is entitled to. Chausson hit this the
      day after the rename: `1612` had won a dedupe and taken `Low profiles 640` locally,
      was then archived in FMLV, and `5554` could not take the name it now holds. The stale
      row keeps its `fmlv_product_id`, which is how it is found, and its name is marked as
      superseded so the constraint is satisfied and the history stays readable.
    """
    clash = connection.execute(
        """
        SELECT * FROM product
        WHERE manufacturer_id = ? AND vehicle_class = ? AND manufacturer_range IS ?
              AND model IS ? AND id != ?
        """,
        (manufacturer_id, VehicleClass(vehicle_class).value, manufacturer_range, model, keeping),
    ).fetchone()
    if clash is None:
        return

    survivor = connection.execute("SELECT * FROM product WHERE id = ?", (keeping,)).fetchone()
    if clash["fmlv_product_id"] is not None:
        if clash["last_seen_run_id"] == run_id:
            msg = (
                f"FMLV products {survivor['fmlv_product_id']} and {clash['fmlv_product_id']} "
                f"are both named {manufacturer_range!r} {model!r} in this run. Two live "
                f"products cannot share a name — archive or rename one of them in FMLV, then "
                f"run again."
            )
            raise ProductIdentityConflict(msg)
        connection.execute(
            "UPDATE product SET model = ? WHERE id = ?",
            (f"{model} (superseded by {survivor['fmlv_product_id']})", clash["id"]),
        )
        return

    for table in _PRODUCT_CHILD_TABLES:
        connection.execute(
            f"UPDATE {table} SET product_id = ? WHERE product_id = ?",  # noqa: S608 — fixed names
            (keeping, clash["id"]),
        )
    connection.execute("DELETE FROM product WHERE id = ?", (clash["id"],))


def upsert_seen(
    connection: sqlite3.Connection,
    *,
    manufacturer_id: int,
    fmlv_product_id: int | None,
    manufacturer_range: str | None,
    model: str | None,
    run_id: int,
    vehicle_class: VehicleClass = DEFAULT_VEHICLE_CLASS,
) -> Product:
    """Record that one product was seen in `run_id`.

    Looks up an existing row first by `fmlv_product_id` (stable NCC identity), falling
    back to an exact `manufacturer_range`/`model` match for products with no
    `fmlv_product_id` yet. If found, the row is updated in place — including its
    `manufacturer_range`/`model`, so a rename is picked up rather than orphaning the
    old name — rather than inserting a duplicate. Otherwise a new row is inserted.

    Both lookups are scoped to `vehicle_class`. The `fmlv_product_id` one does not strictly
    need it — FMLV mints those across both exports from one sequence, and Bailey's
    motorhome and caravan ids don't overlap — but the range/model fallback does: that is
    the path a product with no FMLV id yet takes, and a caravan named like a motorhome
    would otherwise be matched to it and inherit its history.
    """
    class_value = VehicleClass(vehicle_class).value
    existing = None
    if fmlv_product_id is not None:
        existing = connection.execute(
            """
            SELECT * FROM product
            WHERE manufacturer_id = ? AND vehicle_class = ? AND fmlv_product_id = ?
            """,
            (manufacturer_id, class_value, fmlv_product_id),
        ).fetchone()
    if existing is None:
        existing = connection.execute(
            """
            SELECT * FROM product
            WHERE manufacturer_id = ? AND vehicle_class = ? AND manufacturer_range IS ?
                  AND model IS ?
            """,
            (manufacturer_id, class_value, manufacturer_range, model),
        ).fetchone()

    if existing is not None:
        _absorb_clash(
            connection,
            keeping=existing["id"],
            manufacturer_id=manufacturer_id,
            manufacturer_range=manufacturer_range,
            model=model,
            run_id=run_id,
            vehicle_class=vehicle_class,
        )
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
             first_seen_run_id, last_seen_run_id, vehicle_class)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            manufacturer_id,
            fmlv_product_id,
            manufacturer_range,
            model,
            run_id,
            run_id,
            class_value,
        ),
    )
    connection.commit()
    assert cursor.lastrowid is not None
    return get_product(connection, cursor.lastrowid)
