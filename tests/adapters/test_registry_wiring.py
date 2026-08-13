"""Every adapter module is fully wired in, and matches a real registry row.

Adding an adapter takes three separate edits to `src/adapters/__init__.py` — the import,
the `ADAPTERS` entry and `__all__` — plus a matching row in `config/manufacturers.csv`.
Missing any of them **fails silently**: `adapter_for()` returns `None`, which the pipeline
treats as the entirely normal "nobody has written an adapter for this brand yet" state
(see its docstring). Nothing raises. The manufacturer simply never appears in the review
app's trigger dropdown and scheduled sweeps skip it, which is indistinguishable from the
adapter not existing.

So these tests turn a silent omission into a red test. Modules are discovered with
`pkgutil` rather than listed, for the same reason `test_cli.py` iterates `ADAPTERS` — a
test naming the four current adapters would go stale the moment a fifth is written, which
is exactly when it is needed.
"""

from __future__ import annotations

import inspect
import pkgutil
from types import ModuleType

import pytest

from src import adapters, paths, registry

#: Modules in `src/adapters/` that are infrastructure rather than a manufacturer.
_NOT_ADAPTERS = {"base"}


def _adapter_modules() -> list[ModuleType]:
    """Every manufacturer module in `src.adapters`, imported."""
    found = [
        info.name
        for info in pkgutil.iter_modules(adapters.__path__)
        if not info.name.startswith("_") and info.name not in _NOT_ADAPTERS
    ]
    return [getattr(adapters, name) for name in found if hasattr(adapters, name)]


def _adapter_module_names() -> list[str]:
    return [
        info.name
        for info in pkgutil.iter_modules(adapters.__path__)
        if not info.name.startswith("_") and info.name not in _NOT_ADAPTERS
    ]


ADAPTER_NAMES = _adapter_module_names()


def test_there_is_at_least_one_adapter() -> None:
    # Guards the discovery itself: every assertion below is vacuously true against an
    # empty list, so a broken `_adapter_modules` would turn this whole file green.
    assert ADAPTER_NAMES


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_module_is_imported_in_the_package(name: str) -> None:
    # Edit 1 of 3: the `from . import ...` line.
    assert hasattr(adapters, name), (
        f"src/adapters/{name}.py exists but is not imported in src/adapters/__init__.py"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_module_declares_a_manufacturer(name: str) -> None:
    module = getattr(adapters, name)
    manufacturer = getattr(module, "MANUFACTURER", None)
    assert isinstance(manufacturer, str) and manufacturer.strip(), (
        f"src/adapters/{name}.py must declare a non-empty MANUFACTURER — it is the key "
        f"ADAPTERS is registered under"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_module_is_registered_in_adapters(name: str) -> None:
    # Edit 2 of 3: the ADAPTERS dict entry. This is the one that actually breaks running.
    module = getattr(adapters, name)
    manufacturer = module.MANUFACTURER
    assert adapters.ADAPTERS.get(manufacturer) is module, (
        f"adapter_for({manufacturer!r}) does not return src/adapters/{name}.py — add "
        f"`{name}.MANUFACTURER: {name},` to ADAPTERS in src/adapters/__init__.py"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_module_is_exported(name: str) -> None:
    # Edit 3 of 3: __all__.
    assert name in adapters.__all__, (
        f"{name!r} is missing from __all__ in src/adapters/__init__.py"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_collect_accepts_on_progress(name: str) -> None:
    """`cli.execute_run` always passes `on_progress=`, so omitting it fails at run time.

    It has a default in the `Adapter` protocol, which makes it easy to leave out of a new
    adapter and impossible to notice until the first real run — by which point a browser
    has been launched and an export downloaded.
    """
    module = getattr(adapters, name)
    collect = getattr(module, "collect", None)
    assert callable(collect), f"src/adapters/{name}.py has no collect() function"

    parameter = inspect.signature(collect).parameters.get("on_progress")
    assert parameter is not None, (
        f"{name}.collect() must accept `on_progress` — src/cli.py always passes it"
    )
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"{name}.collect()'s `on_progress` must be keyword-only, as it is passed by name"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_manufacturer_matches_a_registry_row(name: str) -> None:
    """`MANUFACTURER` must match a `fmlv_manufacturer` in `config/manufacturers.csv`.

    A mismatch here is the subtle one — a trailing space, or `Ltd` against `Ltd.`. The
    adapter loads, the registry loads, and `adapter_for()` returns `None` for the row the
    user actually asked to run.
    """
    module = getattr(adapters, name)
    result = registry.load(paths.registry_path())
    known = {manufacturer.fmlv_manufacturer for manufacturer in result.manufacturers}
    assert module.MANUFACTURER in known, (
        f"{name}.MANUFACTURER = {module.MANUFACTURER!r} matches no fmlv_manufacturer in "
        f"config/manufacturers.csv. Known: {sorted(known)}"
    )


@pytest.mark.parametrize("name", ADAPTER_NAMES)
def test_default_ranges_is_well_formed(name: str) -> None:
    """`DEFAULT_RANGES` is optional, but a malformed one only fails when `--range` is used.

    `cli.resolve_ranges` reads it with `getattr` and unpacks each entry into
    `(path, label)`, so a bare tuple of strings passes every other check in this file and
    then raises on the first smoke run.
    """
    module = getattr(adapters, name)
    ranges = getattr(module, "DEFAULT_RANGES", None)
    if ranges is None:
        pytest.skip(f"{name} does not support --range")

    assert isinstance(ranges, tuple) and ranges, f"{name}.DEFAULT_RANGES must be a non-empty tuple"
    for entry in ranges:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"{name}.DEFAULT_RANGES entries must be (path, label) pairs, got {entry!r}"
        )
        assert all(isinstance(part, str) and part.strip() for part in entry), (
            f"{name}.DEFAULT_RANGES entries must be two non-empty strings, got {entry!r}"
        )
