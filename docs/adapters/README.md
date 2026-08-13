# Adapters — the general pattern

Five data points now: [Adria](adria.md), [Morelo](morelo.md), [Swift](swift.md),
[Sunlight](sunlight.md) and [Rimor](rimor.md). They differ enough that the ordering of
the questions below matters more than any of the individual answers.

## Start here: is there a brochure or price list PDF?

**Ask this before looking at the website's rendering behaviour at all.** It was the
last thing tried for Adria and the first thing that worked for the three after it:

| | Adria | Morelo | Swift | Sunlight | Rimor |
|---|---|---|---|---|---|
| JavaScript needed | Yes (Livewire, scroll-triggered) | No | No | No | No |
| Fetches | 2 per product | 2 total | 2 per catalogue | 2 per catalogue | 1 per product + 1 per range |
| Products | 54 | 61 | 30 | 26 | 41 |
| Price | AJAX JSON | In the PDF (EUR) | **Not published anywhere** | In the PDF (**GBP**) | **Not published anywhere** |
| Berths / seats | Per-product PDF | Not published | In the PDF | In the PDF | In the HTML |
| Weights + dimensions | Per-product PDF | In the PDF | In the PDF | In the PDF | Dimensions in the HTML; MTPLM only, from the catalogue |

Three of five publish everything in a PDF, and where they do, the PDF has been the
better source every time — cheaper (one fetch, no browser, no per-product work) *and*
more complete than the website.

**But ask the question, don't assume the answer.** Rimor is the counter-example, and it
is worth being precise about *why*, because the obvious reading is wrong.

Rimor's catalogue is not thin. It publishes everything the website does **plus**
wheelbase, MTPLM, engine, tank capacities and equipment — on field count it beats the
HTML comfortably. What it cannot do is say **which model a number belongs to**. Its spec
pages set two or three models side by side and print a value once where it spans several
columns:

```
HORUS 12    HORUS 38    HORUS 45      <- three models
Outside length (mm) 5413 5998         <- two values
```

pypdf returns that whole row as a single run at a single x, so there is nothing to
recover the spans from. The numbers are present and unattributable.

The website wins because **attribution is free**: one URL per model, one set of numbers
on it. That is what the question at the top of this section is really asking. "Is there
a PDF?" is a proxy for *where can I get many products in one fetch, with each number
unambiguously attached to one of them?* For Adria, Morelo, Swift and Sunlight the PDF
was that place. For Rimor it is the place where attribution collapses, so the PDFs are
demoted: the catalogue is kept for the two fields that are **constant down the page**
(MTPLM, engine) and so need no alignment at all, and the leaflets — which genuinely do
carry a strict subset of the HTML — are kept only as the cross-check.

Two things to carry forward:

- **Rank sources by attribution, not by field count.** A document with fewer fields and
  one product per page beats a richer one whose columns cannot be separated.
- **A PDF that looks parseable may not be.** Check whether the value you want varies per
  column *before* planning to read columns. If it does, and the layout merges cells, no
  amount of effort recovers it — but a page-constant value is still safe to take.

Adria's shape, a JS-rendered catalogue plus a per-product PDF, remains the other
exception.

Two follow-on questions the later surveys added:

- **Is there a market-specific edition?** Sunlight is German but publishes a UK & Ireland
  price list in sterling, which removes the exchange-rate problem that is the single
  worst piece of data in the Morelo adapter. Check before converting a currency.
- **Does the downloads page list more than the current document?** Every one so far has
  had a near-miss sitting beside the file actually wanted — Morelo's catalogue in a
  directory called `kataloge_preislisten`, Swift's opaque media key, Sunlight's three
  superseded model years *and* a differently-named glossy catalogue. Match precisely,
  prefer the newest, and rediscover per run rather than hardcoding.

### If the document is behind a name/email form

Two things, in this order.

**First, check whether the form is actually protecting anything.** Rimor's catalogue is
fronted by a lead-generation form (name, email, city, three consent boxes) and the PDF
itself sits unauthenticated on a public asset path — no token, no cookie. The form was
a front door, not a lock. A web search for the filename found it in a minute. Try that
before anything else; a gated-looking document may not be gated at all.

**If it really is gated, use Ben's details.** `config/reviewers.csv` holds them, and
there is standing permission to submit them to a manufacturer's catalogue or brochure
request form. This is what the form is for: a real person at the NCC asking a
manufacturer for their catalogue.

Two rules when doing so:

- **Never invent details.** Fabricated names and addresses go into a real CRM under a
  real consent flow, and they poison the manufacturer's data. Use the real ones or
  don't submit.
- **Tick only the consent that is required.** Read the labels: there is usually one
  mandatory "I have read the privacy policy" box and one or two optional marketing and
  profiling consents. Rimor's form validates `privacy_1` only. Leave the optional ones
  unticked — the permission is to request a document, not to sign the NCC up for a
  manufacturer's marketing.

Say in the survey document which route was used, and if a form was submitted, say so
explicitly at the checkpoint.

## Then: parsing a spec table is where the real risk is

For a PDF-sourced manufacturer, finding the numbers is easy and *attaching them to the
right product* is hard — and it fails silently. Swap two columns of a Morelo page or
misjoin two Swift tables and you get plausible, internally consistent motorhomes
carrying each other's weights and prices. Nothing downstream flags it and a reviewer
accepts the change.

Three defences, all of which earned their place:

- **Never infer a column from reading order alone.** pypdf emits runs in content-stream
  order, which on some Morelo pages is right-to-left. `fetch.pdf.extract_positioned_text`
  gives coordinates — but note that pypdf also fails to place *some* runs (reporting
  (0, 0)), so coordinates can't be trusted blindly either. See [`morelo.md`](morelo.md)
  for the rule that satisfies both.
- **Parse runs, not lines, wherever cell boundaries carry meaning.** A line is a lossy
  rendering of a table: joined up, `CLIFF 540 V` and `CLIFF 540` followed by a stray
  `V` are the same string, and Sunlight sells both. Where a value can contain a space,
  run boundaries are the only thing that says where a cell ends.
- **Look for arithmetic the manufacturer publishes against itself.** Morelo and Swift
  give MTPLM, MRO *and* payload, so `payload == MTPLM − MRO` is a free check on the
  parse — per column for Morelo, per join for Swift. Sunlight publishes no payload but
  prints each mass with its ±5% tolerance band, which is self-consistent in the same
  way and serves the same purpose. Look for *some* redundancy in the document; there
  has been one every time. Products that fail it are dropped rather than proposed. It
  catches misaligned columns, not mislabelled ones.

  Rimor publishes no payload *and* no MRO, so its redundancy is **cross-document**: the
  range leaflet republishes every layout's `length x width`, and the body-style listing
  republishes the seats and berths that the model's own page states. Where one document
  has no internal arithmetic, look for a second that says the same thing twice — and
  compare as an **unordered multiset**, since the leaflets extract in scrambled reading
  order and any position-dependent comparison would be checking noise.

One trap common to all of them: when slicing a row's values, **stop at the next row's
label** rather than taking a fixed count. A short row otherwise swallows the following
label, padding the count back to what was expected and defeating the very check meant
to catch it.

Anchor row patterns on whichever end of the row is **typed and fixed-width**. Swift's
rows have ragged engine prose on the left and a fixed run of metres/integers/`kg` on the
right, so every pattern anchors right and never parses the left at all.

## What Adria's survey found

Kept because it is still the pattern for a JS-driven catalogue, and some manufacturer
will have one.

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
