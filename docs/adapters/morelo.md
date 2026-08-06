# Morelo — site survey and adapter notes

Surveyed 6 August 2026, against price list **model year 2027-2** (`morelo_preisliste_2027-2_260804_GB.pdf`).

Morelo is the second manufacturer surveyed, and it is close to the opposite of Adria in
every respect that matters. Worth stating plainly, because it undercuts the "expect two
fetches per product" hypothesis in [`README.md`](README.md):

| | Adria | Morelo |
|---|---|---|
| JavaScript needed | Yes (Livewire, scroll-triggered) | **No, anywhere** |
| Documents per product | 2 (JSON + per-product PDF) | **2 for the whole catalogue** |
| Where the specs live | Per-configuration PDF | One price list PDF, one page per 1–2 floorplans |
| Where the price lives | AJAX JSON | The same PDF page |
| Hard part | Finding the data at all | Reading a two-column table without swapping the columns |

61 floorplans across 11 ranges, all from one 100-page document, with two plain
`Fetcher` calls and no browser.

## Where the data is

**The model pages are not usable.** `/en/models/palace` and its siblings give
range-level figures only — "8.69 – 9.79 m long", "from €285,900" — spanning every
floorplan in the range. Nothing per-product. They were checked first and set aside.

**The price list PDF is everything.** `/en/buy-and-rent/catalogues-and-price-lists`
links a catalogue and a price list in seven languages. The English price list has, for
each range, a run of `TECHNICAL SPECIFICATIONS` pages carrying one or two floorplans
each:

```
PALACE 85 L PALACE 88 LB
WEIGHT
Technically permissible max. weight (kg)1   7.490    7.490
Mass in running order (kg)1                 5.570    5.680
Payload (kg)1                               1.920    1.810
DIMENSIONS
Total length (mm)                           8.690    8.990
...
                                      312.500,00 € 320.550,00 €
```

That is MTPLM, MIRO, payload, length, width, height, base chassis and price — as plain
extractable text, not images. It fills every numeric FMLV field the Adria adapter fills
except berths and seats.

**The URL is not stable and must not be hardcoded.** The filename carries both a model
year and a publication date (`2027-2`, `260804`). The adapter reads the catalogues page
each run and matches the link. One trap, caught by a test: the containing directory is
`kataloge_preislisten`, so matching "preisliste" anywhere in the path cheerfully returns
the *catalogue* — a glossy brochure with no spec tables. The match is anchored on the
`morelo_preisliste_` filename instead.

## The real difficulty: column order

The parsing problem here is not finding the numbers. It is keeping each column attached
to the right floorplan — and this is a **silent** failure mode. Swap two columns of a
Morelo page and you get two plausible, internally consistent motorhomes with each
other's weights and prices. Nothing downstream would flag it; a reviewer would see a
believable price change and accept it.

Three separate traps, all real in this document, and each one's obvious fix breaks
another:

1. **Reading order is sometimes reversed.** On page 58 (Palace Liner 103 GSB / 110 GSB)
   and page 75, pypdf emits the *right-hand* model name first. Pairing names to columns
   by reading order swaps both products.
2. **So use x-coordinates — except they're sometimes missing.** On page 54 (Palace Liner
   88 LB / 90 M) and several others, pypdf resolves one name run to (0, 0) rather than
   its real position. Sorting on that moves it to the front of a page whose reading
   order was already correct, breaking pages that previously worked.
3. **Names appear where names aren't.** The `MORELO LOFT ALKOVEN` heading is followed on
   the next line by the footnote `1) see back`, which a newline-crossing match reads as
   a floorplan called "1".

What the adapter settled on: **take names in reading order, and re-sort by x only when
every name on the page has a genuine position to sort on.** Reading order is correct
wherever coordinates are unavailable; coordinates correct it wherever they exist. Name
matching is confined to a single line.

`fetch.pdf.extract_positioned_text` was added for this. It is manufacturer-agnostic —
multi-column spec tables in PDFs are not going to be a Morelo-only problem — so it sits
with the other fetch utilities rather than in the adapter, the same call `Adria` made
with `BrowserFetcher.fetch_with_capture`.

### The arithmetic check

Morelo publishes all three of max weight, mass in running order and payload, and they
are related: `payload == max weight − MIRO`. The parser checks it and drops any product
where it fails.

This is not a data-quality opinion about Morelo's figures — it is the parser checking
its own column alignment, since the three numbers are read from three different rows.
It holds for all 61 products in 2027-2, so a future failure means the document's shape
has changed rather than that Morelo has published a typo. Note the limit: it catches
*misaligned* columns, not *mislabelled* ones. A pure name swap leaves the arithmetic
intact, which is why the ordering logic above has to be right on its own.

Two smaller parsing points, both with a test:

- Optional chassis uprating is written in brackets — `5.600 (5.990)`. The bracketed
  figure is dropped: FMLV wants the vehicle as specified, and counting it would double
  the column count.
- Footnote markers abut the label with no space, and are *not* always digits — on the
  Alkoven pages the same marker extracts as U+FFFD. Allowing only digits silently cost
  those pages every weight.

## Known gaps

- **Berths and seats are not extracted, because Morelo does not publish them here.** The
  price list gives bed *dimensions* (`Rear bed (mm) 2 x 2.000 x 1.060`), not a berth
  count. Inferring "2 berths" from a bed size is a guess, and a guess proposed to a
  reviewer is worse than a blank. Both fields stay `None`. If FMLV needs them, the
  glossy catalogue or a direct question to Morelo is the route — not this PDF.
- **Prices are converted from euros at a fixed rate** (`EUR_TO_GBP_RATE` in the
  adapter), on Ben's instruction, the alternative having been to leave price empty. This
  is the weakest data in the adapter and it will go stale: the rate is a constant that
  needs revisiting, and it is *baked into every proposed price change*. Two mitigations:
  every converted price carries the original euro figure, the rate and its date in its
  provenance snippet, so a reviewer sees the derivation and can overrule it; and the
  rate is one greppable constant rather than an expression. Worth a proper decision
  before Morelo goes anywhere near a real FMLV upload — a live rate lookup, an agreed
  fixed annual rate, or a UK importer's own sterling list price if one exists.
- **These are German-market, left-hand-drive prices including 20% VAT**, for purchase
  and registration in Germany. Whether that is the right basis for FMLV at all is a
  question for Francis, not one the adapter can answer.
- Ranges are discovered from the PDF's own headings rather than hardcoded, so a new
  range needs no code change — but the `RANGES` table maps PDF spelling to display
  name, and a genuinely new range name would need adding there.

## What this says about the general pattern

[`README.md`](README.md)'s hypothesis after Adria was "expect two fetches per product".
Morelo says: **expect that to vary enormously, and check for a single published price
list first.** It is the cheapest possible source — one fetch, no browser, no
per-product work — and for a manufacturer that publishes one, it is likely to be more
complete than the website. The website was the *worse* source here.

The revised first question for manufacturer three is therefore: *does this manufacturer
publish a price list or brochure PDF with a technical-specification section?* Only if
not is it worth surveying the site's rendering behaviour. Swift, surveyed next, has the
same shape — a specification table at the back of one brochure.
