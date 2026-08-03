"""The run store: SQLite persistence for runs, snapshots, changes and decisions."""

from .db import connect
from .products import Product, get_product, list_products, upsert_seen
from .runs import Run, fail_run, finish_run, get_run, list_runs, start_run

__all__ = [
    "Product",
    "Run",
    "connect",
    "fail_run",
    "finish_run",
    "get_product",
    "get_run",
    "list_products",
    "list_runs",
    "start_run",
    "upsert_seen",
]
