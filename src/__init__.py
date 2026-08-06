"""FMLV automated data flow — see DESIGN.md."""

from __future__ import annotations


def main() -> int:
    """Console-script entry point, kept thin so importing the package stays cheap.

    `cli` pulls in Playwright (via `fetch.browser`) and every other stage, which no
    caller who just wants, say, `product_model.io` should have to pay for — hence the deferred
    import rather than a module-level one.
    """
    from .cli import main as cli_main

    return cli_main()
