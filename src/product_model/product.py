"""The union of the two canonical products, for code that works on either.

`Motorhome` and `Caravan` are deliberately separate classes (see the package docstring),
but most of the pipeline downstream of an adapter does not care which it has: matching
compares range and model names, diffing reads fields by name, and the run store keys
everything on a free-text field name. That code annotates `Product`.

A union rather than a shared base class. The two models have around thirty fields in
common, but the ones that look shared mostly are not — a motorhome's `mh_length_mm` is a
caravan's `exterior_body_length_mm`, and `body_type` and `sleeping_area` hold different
enums in each. A base class would have carried the carry-through fields, the prices and
five enums while both subclasses still declared most of their own content, in exchange
for making every field lookup a question about the hierarchy. The union states the same
thing without the indirection, and `isinstance` still distinguishes them where it matters
(`diff.compare.profile_for`).
"""

from __future__ import annotations

from .caravan import Caravan
from .model import Motorhome

#: One product of either area.
Product = Motorhome | Caravan

__all__ = ["Caravan", "Motorhome", "Product"]
