"""Logging in to the NCC website and downloading the current FMLV export.

DESIGN.md §6.2: this is the one piece of NCC-site automation the pipeline does —
Playwright logs in and downloads the current export, which becomes the baseline for a
run. The *generated* upload CSV (`output/`) is still uploaded by hand; that human gate
on the only irreversible step is unaffected by this module.

Unlike a manufacturer adapter (DESIGN.md §5.1's "the only manufacturer-specific
code"), the NCC site itself has not been surveyed the way Phase 4 surveyed each
manufacturer — `NccSiteConfig`'s URLs and selectors below are therefore placeholders
to be confirmed against the real login/export pages, not facts read off them.
Whether the site even needs this route, versus exposing a proper export API, is still
open question 2 (DESIGN.md §9). Everything about the flow is a `NccSiteConfig` field
so confirming the real values is a config change, not a rewrite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

#: DESIGN.md §8: "Anthropic API key and NCC credentials via environment, never
#: committed." These are the two env vars that carry the NCC login.
CREDENTIALS_EMAIL_ENV = "NCC_LOGIN_EMAIL"
CREDENTIALS_PASSWORD_ENV = "NCC_LOGIN_PASSWORD"


class NccCredentialsError(RuntimeError):
    """Raised when the NCC login credentials aren't available in the environment."""


@dataclass(frozen=True)
class NccCredentials:
    """NCC site login. Always sourced from the environment — see `from_env`."""

    email: str
    password: str

    @classmethod
    def from_env(cls, *, env: dict[str, str] | None = None) -> NccCredentials:
        """Read the login from `NCC_LOGIN_EMAIL`/`NCC_LOGIN_PASSWORD`.

        Raises `NccCredentialsError` rather than proceeding with a blank credential —
        a login attempt with an empty password is a confusing failure to debug from
        the site's side, and there's nothing useful to do with a partial login.
        """
        source = env if env is not None else os.environ
        email = source.get(CREDENTIALS_EMAIL_ENV)
        password = source.get(CREDENTIALS_PASSWORD_ENV)
        if not email or not password:
            msg = (
                f"{CREDENTIALS_EMAIL_ENV} and {CREDENTIALS_PASSWORD_ENV} must both be "
                "set in the environment to log in to the NCC site"
            )
            raise NccCredentialsError(msg)
        return cls(email=email, password=password)


@dataclass(frozen=True)
class NccSiteConfig:
    """Where the NCC login/export pages are and how to drive them.

    Defaults are placeholders — see the module docstring — pass overrides once the
    real site has been surveyed rather than trusting these.
    """

    login_url: str = "https://www.findmyleisurevehicle.co.uk/login"
    export_url: str = "https://www.findmyleisurevehicle.co.uk/exports/motorhome-campervans"
    email_selector: str = 'input[type="email"], input[name="email"]'
    password_selector: str = 'input[type="password"], input[name="password"]'
    login_submit_selector: str = 'button[type="submit"]'
    download_trigger_selector: str = 'a:has-text("Download"), button:has-text("Download")'


def download_export(
    credentials: NccCredentials,
    dest_path: Path | str,
    *,
    config: NccSiteConfig = NccSiteConfig(),
    headless: bool = True,
    executable_path: str | None = None,
) -> Path:
    """Log in to the NCC site and download the current motorhome/campervan export.

    A fresh browser is launched and closed for this one action rather than reusing a
    long-lived instance the way `BrowserFetcher` does for many manufacturer-page
    fetches — a run needs this exactly once, to obtain the baseline (DESIGN.md §5).

    Returns `dest_path` (parents created if needed) once the download has landed.
    `executable_path` overrides which Chromium binary Playwright launches — normally
    left as `None` so Playwright uses the browser installed for the pinned version
    (see `playwright install chromium`, TODO.md Phase 3); tests pass it explicitly to
    target a specific local build.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, executable_path=executable_path)
        try:
            page = browser.new_page()
            page.goto(config.login_url)
            page.fill(config.email_selector, credentials.email)
            page.fill(config.password_selector, credentials.password)
            with page.expect_navigation():
                page.click(config.login_submit_selector)

            page.goto(config.export_url)
            with page.expect_download() as download_info:
                page.click(config.download_trigger_selector)
            download_info.value.save_as(dest_path)
        finally:
            browser.close()

    return dest_path
