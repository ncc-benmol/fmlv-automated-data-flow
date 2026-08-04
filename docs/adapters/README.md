# Adapters — the general pattern

One data point so far (Adria — see [`adria.md`](adria.md)), so treat this as a working
hypothesis to test against the next manufacturer, not a settled architecture.

## What Adria's survey found

A model-range page's plain HTML is nearly useless: no price, no specs, sometimes not
even the layout list, because the actual data loads via client-side JS after the page
renders. This should be checked first for every manufacturer — fetch the page with
plain `httpx` (`fetch/http.py`) and look for the numbers before reaching for a browser.

Two different pieces of data lived in two different places, discovered by two different
means:

1. **Layout, trim, berths, price** — inside a JSON blob attached to a scroll-triggered
   AJAX call (a Laravel Livewire component, in Adria's case), invisible to a plain HTTP
   fetch and invisible to a browser fetch that only waits for `networkidle` — it had to
   be found by watching the network panel while actually scrolling the rendered page.
2. **Weights and dimensions** — nowhere in that JSON. Found only by chasing a "download
   technical data" button through to its PDF, which turned out to sit at a predictable,
   unauthenticated URL keyed by a product ID that *was* in the JSON. Once known, that
   PDF is a plain deterministic fetch — no browser needed for it at all.

The general shape this suggests: **expect two fetches per product, not one** — a
JS-rendered page (or its underlying AJAX response) for identity/price/layout, and a
separate, often-plain-HTTP, document for the numeric technical spec. Don't assume the
spec sheet is reachable from a static URL pattern alone; it was only found by reading
what a real interaction (the "download" button) actually requested.

## Adapter interface

`adapters/base.py` defines the shared shape:

- `Provenance(source_url, snippet)` — where one field's value came from, for the reviewer.
- `ExtractedMotorhome(motorhome, provenance)` — a `Motorhome` plus a `{field_name:
  Provenance}` map. Not every field needs an entry.
- `Adapter.collect(http, browser, snapshot_dir) -> list[ExtractedMotorhome]` — one
  method, not fetch/parse split. For a JS-driven catalogue, deciding what to fetch next
  (e.g. which PDF) depends on content already fetched, so the adapter owns its whole
  fetch-then-parse sequence. Every fetch still goes through `Fetcher`/`BrowserFetcher`,
  so everything is still snapshotted to disk regardless (DESIGN.md §6.6).

`fetch/browser.py`'s `BrowserFetcher.fetch_with_capture()` is the one genuinely
manufacturer-agnostic addition this required: render a page, optionally scroll it in
steps, and snapshot any XHR/fetch response whose URL matches a substring. Scroll-
triggered lazy loading is common enough on modern marketing sites that this is written
as a generic capability, not something specific to Adria.

## What to check for the next manufacturer

- Does the plain-HTML page already have the numbers? (Don't reach for the browser
  before checking.)
- If not, is the real data in a JS framework's own state/AJAX payload (React/Vue
  hydration data, a Livewire snapshot, a GraphQL call)? Read the rendered DOM's
  `<script>` tags for a state blob before assuming a browser render alone is enough —
  Adria's data only appeared after triggering a *scroll*, not just a load.
- Is there a "download spec sheet" / "compare" / "brochure" button? Follow it — it may
  resolve to a stable, unauthenticated, non-JS URL that's cheaper to fetch directly than
  scripting the interaction that produces it every time.
- Are weights/dimensions ever in the HTML/JSON path at all, or always PDF-only? This
  was Adria's answer; DESIGN.md §9 open question 6 expects this to vary by manufacturer.
