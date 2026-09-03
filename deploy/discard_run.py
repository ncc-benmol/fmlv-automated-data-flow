"""Discard one run and everything that hangs off it, including products it invented.

Written for a specific accident on 3 September 2026: the first caravan run diffed
against the *motorhome* sheet, so it recorded 24 caravan products named Adamo,
Autograph and Endeavour, none of which exist. Those rows outlive the run — they are
product identities, not run output — and would raise a fresh disappearance notice on
every caravan run from then on.

Kept in the repo rather than pasted into a terminal because it deletes review history
from the only copy of it. It reports by default and needs `--apply` to touch anything.

    .venv\\Scripts\\python.exe deploy\\discard_run.py 12
    .venv\\Scripts\\python.exe deploy\\discard_run.py 12 --apply

Only products **first seen by the discarded run** are removed, and only when no other
run has seen them since. A product the run merely re-confirmed belongs to the runs that
found it first and is left alone.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import paths, store  # noqa: E402


def _rows(connection: sqlite3.Connection, sql: str, *params: object) -> list[sqlite3.Row]:
    return connection.execute(sql, params).fetchall()


def report(connection: sqlite3.Connection, run_id: int) -> dict[str, int]:
    """What discarding `run_id` would remove."""
    run = store.get_run(connection, run_id)
    print(
        f"run #{run.id}: {run.fmlv_manufacturer} / {run.vehicle_class.value} / "
        f"{run.status} / started {run.started_at}"
    )

    changes = _rows(connection, "SELECT id FROM proposed_change WHERE run_id = ?", run_id)
    change_ids = [row["id"] for row in changes]
    decisions = (
        connection.execute(
            "SELECT COUNT(*) FROM decision WHERE proposed_change_id IN "
            f"({','.join('?' * len(change_ids))})",
            change_ids,
        ).fetchone()[0]
        if change_ids
        else 0
    )
    verifications = _rows(connection, "SELECT id FROM verification WHERE run_id = ?", run_id)
    notices = _rows(connection, "SELECT id FROM disappearance_notice WHERE run_id = ?", run_id)
    snapshots = _rows(connection, "SELECT id FROM source_snapshot WHERE run_id = ?", run_id)

    orphans = _rows(
        connection,
        """
        SELECT id, vehicle_class, manufacturer_range, model, fmlv_product_id
        FROM product
        WHERE first_seen_run_id = ? AND (last_seen_run_id IS NULL OR last_seen_run_id = ?)
        ORDER BY manufacturer_range, model
        """,
        run_id,
        run_id,
    )

    print(f"  proposed changes    {len(changes)}")
    print(f"  decisions on them   {decisions}")
    print(f"  verifications       {len(verifications)}")
    print(f"  disappearance notes {len(notices)}")
    print(f"  source snapshots    {len(snapshots)}")
    print(f"  products only this run ever saw: {len(orphans)}")
    for row in orphans:
        fmlv = row["fmlv_product_id"]
        print(
            f"      [{row['vehicle_class']}] {row['manufacturer_range']} {row['model']}"
            f"{'' if fmlv is None else f' (FMLV {fmlv})'}"
        )
    if decisions:
        print("  NOTE: decisions exist on this run — someone reviewed it. Check before applying.")
    return {
        "changes": len(changes),
        "decisions": decisions,
        "verifications": len(verifications),
        "notices": len(notices),
        "snapshots": len(snapshots),
        "products": len(orphans),
    }


def discard(connection: sqlite3.Connection, run_id: int) -> None:
    """Delete the run and everything that hangs off it. Call `report` first."""
    change_ids = [
        row["id"]
        for row in _rows(connection, "SELECT id FROM proposed_change WHERE run_id = ?", run_id)
    ]
    orphan_ids = [
        row["id"]
        for row in _rows(
            connection,
            """
            SELECT id FROM product
            WHERE first_seen_run_id = ? AND (last_seen_run_id IS NULL OR last_seen_run_id = ?)
            """,
            run_id,
            run_id,
        )
    ]

    with connection:
        if change_ids:
            placeholders = ",".join("?" * len(change_ids))
            connection.execute(
                f"DELETE FROM decision WHERE proposed_change_id IN ({placeholders})",  # noqa: S608
                change_ids,
            )
        connection.execute("DELETE FROM proposed_change WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM verification WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM disappearance_notice WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM source_snapshot WHERE run_id = ?", (run_id,))
        # Products can carry child rows from *other* runs; clear those first so the
        # delete cannot fail halfway and leave the store inconsistent.
        for product_id in orphan_ids:
            for table in ("proposed_change", "verification", "disappearance_notice"):
                connection.execute(
                    f"DELETE FROM {table} WHERE product_id = ?",  # noqa: S608 — fixed names
                    (product_id,),
                )
            connection.execute("DELETE FROM product WHERE id = ?", (product_id,))
        connection.execute("DELETE FROM run WHERE id = ?", (run_id,))

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        msg = f"foreign key check failed after discarding run {run_id}: {violations}"
        raise RuntimeError(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", type=int)
    parser.add_argument("--data-dir", type=Path, default=paths.DATA_DIR)
    parser.add_argument(
        "--apply", action="store_true", help="actually delete; omit to report only"
    )
    args = parser.parse_args(argv)

    connection = store.connect(paths.db_path(root=args.data_dir))
    try:
        try:
            counts = report(connection, args.run_id)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        if not args.apply:
            print("\nreport only — re-run with --apply to delete")
            return 0

        discard(connection, args.run_id)
        print(f"\ndiscarded run #{args.run_id} and {counts['products']} product row(s)")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
