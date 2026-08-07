"""The manufacturer registry data model.

One `Manufacturer` per row of `data/manufacturers.csv` — who to visit, where, and in
what shape. See `data/manufacturers.README.md` for the column-by-column field guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Status(str, Enum):
    """Whether a manufacturer participates in scheduled sweeps."""

    ACTIVE = "active"
    PAUSED = "paused"  # skip in scheduled sweeps, still runnable manually
    RETIRED = "retired"  # brand no longer trading


class TriState(str, Enum):
    """yes / no / unknown — used where the answer is genuinely undiscovered yet."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Manufacturer:
    """One manufacturer, as recorded in the registry.

    `manufacturer_id` is the NCC-assigned identifier Ben has populated the registry
    with — not a slug we invented (see the open question this raised in TODO.md about
    confirming what system it comes from). `ncc_supplier_name` is a separate identity
    again: the exact label this manufacturer has in the NCC site's own "Export Products
    by Supplier" dropdown (`fetch/ncc.py`), which doesn't always match
    `fmlv_manufacturer` (e.g. `"Adria Mobil"` vs `"Adria Caravans & Motorhomes"`).
    """

    manufacturer_id: int
    fmlv_manufacturer: str
    fmlv_display_name: str | None
    categories: tuple[str, ...]
    status: Status
    pilot_priority: int | None
    country: str | None
    website_url: str
    uk_site_url: str | None
    models_index_url: str | None
    price_list_url: str | None
    brochure_url: str | None
    ncc_supplier_name: str | None
    specs_format: str
    needs_javascript: TriState
    login_required: bool
    ncc_member: bool | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    last_verified: str | None
    notes: str | None

    @property
    def includes_motorhomes(self) -> bool:
        """Whether this manufacturer is in scope for a motorhome run.

        The prototype is motorhome-only (see DESIGN.md §3). A manufacturer with no
        `categories` recorded yet is included by default — nothing to exclude on —
        rather than silently skipped; a `categories_unset` issue is still raised at
        load time so the gap gets noticed and filled in.
        """
        if not self.categories:
            return True
        return "motorhome" in self.categories

    @property
    def is_runnable(self) -> bool:
        return self.status == Status.ACTIVE

    @property
    def crawl_entry_point(self) -> str | None:
        """The best URL to start a crawl from, preferring the most specific one known."""
        return self.models_index_url or self.uk_site_url or self.website_url
