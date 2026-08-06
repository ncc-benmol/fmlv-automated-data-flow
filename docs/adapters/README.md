# Adapters — the general pattern

Three data points now: [Adria](adria.md), [Morelo](morelo.md) and [Swift](swift.md).
They differ enough that the ordering of the questions below matters more than any of
the individual answers.

## Start here: is there a brochure or price list PDF?

**Ask this before looking at the website's rendering behaviour at all.** It was the
last thing tried for Adria and the first thing that worked for both Morelo and Swift:

| | Adria | Morelo | Swift |
|---|---|---|---|
| JavaScript needed | Yes (Livewire, scroll-triggered) | No | No |
| Fetches | 2 per product | 2 total | 2 per catalogue |
| Products | 54 | 61 | 30 |
| Price | AJAX JSON | In the PDF (EUR) | **Not published anywhere** |
| Berths / seats | Per-product PDF | Not published | In the PDF |
| Weights + dimensions | Per-product PDF | In the PDF | In the PDF |

A manufacturer that publishes a price list or a brochure with a technical-specification
section is dramatically cheaper to support — one fetch, no browser, no per-product work
— and the document is often *more* complete than the website. For both Morelo and Swift
the website was the worse source. Adria's shape (JS-rendered catalogue plus a
per-product PDF) turned out to be the exception, not the rule.

## Then: parsing a spec table is where the real risk is

For a PDF-sourced manufacturer, finding the numbers is easy and *attaching them to the
right product* is hard — and it fails silently. Swap two columns of a Morelo page or
misjoin two Swift tables and you get plausible, internally consistent motorhomes
carrying each other's weights and prices. Nothing downstream flags it and a reviewer
accepts the change.

Two defences, both of which earned their place:

- **Never infer a column from reading order alone.** pypdf emits runs in content-stream
  order, which on some Morelo pages is right-to-left. `fetch.pdf.extract_positioned_text`
  gives coordinates — but note that pypdf also fails to place *some* runs (reporting
  (0, 0)), so coordinates can't be trusted blindly either. See [`morelo.md`](morelo.md)
  for the rule that satisfies both.
- **Look for arithmetic the manufacturer publishes against itself.** Both Morelo and
  Swift give MTPLM, MRO *and* payload, so `payload == MTPLM − MRO` is a free check on
  the parse — per column for Morelo, per join for Swift. Products that fail it are
  dropped rather than proposed. It catches misaligned columns, not mislabelled ones.

Anchor row patterns on whichever end of the row is **typed and fixed-width**. Swift's
rows have ragged engine prose on the left and a fixed run of metres/integers/`kg` on the
right, so every pattern anchors right and never parses the left at all.

## What Adria's survey found

Kept because it is still the pattern for a JS-driven catalogue, and some manufacturer
will have one.

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

- **Is there a brochure or price list PDF with a spec section?** Check this first — see
  the top of this file.
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
