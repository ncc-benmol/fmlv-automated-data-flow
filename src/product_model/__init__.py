"""Canonical FMLV product models, schemas and IO.

Two product areas, two schemas, deliberately parallel rather than generalised:

* **Motorhomes and campervans** — `schema.py` (68 columns), `model.Motorhome`, `io.py`.
* **Touring caravans** — `caravan_schema.py` (62 columns), `caravan.Caravan`,
  `caravan_io.py`.

They share `enums.py` (six of the eight layout groups are identical column-for-column),
`validation.py` and the cell-level coercions in `io.py`, and nothing else. A single model
spanning both would have to carry a base vehicle caravans never have, a rear garage they
cannot have, and four dimension fields whose meaning changes with the area.

The only part of the system that knows about either export's columns.
"""
