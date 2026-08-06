# Swift Group — site survey and adapter notes

Surveyed 6 August 2026, against the **2026** motorhome and campervan brochures.

Swift is the third manufacturer surveyed and the easiest so far. It also confirms the
revised rule from [Morelo](morelo.md): **look for a brochure before surveying the
website.** Both index pages link a brochure PDF directly — no form, no login — and the
back of each carries a "Specification at a glance" table covering every layout sold.

**30 layouts, four fetches, no browser:**

| Catalogue | Ranges | Layouts |
|---|---|---|
| Motorhomes | Voyager, Trekker, Escape, Kon-Tiki | 20 |
| Campervans | Monza, Trekker, Carrera | 10 |

20 motorhomes matches Swift's own claim on the page ("20 layouts across four
exceptional ranges"), which is a useful independent check that nothing was missed.

## What Swift publishes

This is the richest per-product data of the three manufacturers so far — Swift publishes
**berths, seat belts, overall length/width/height, MTPLM, MRO *and* payload** for every
layout:

```
475 Ford 130 Bhp 165 Bhp Auto 2.0ltr 360Nm 1 4.52m 5 5 7.54m 2.37m 2.98m Thule T4200 4.0m^ Cat C1
475 3550kg+ 3094kg‡ 456kg‡ 2000kg 5500kg THREE Truma Neo 12"
```

Berths and seats are worth calling out: Morelo publishes neither, and Adria's come from
a separate PDF per product. Swift gives both, for every layout, in one table.

The two brochures are laid out differently, and the adapter handles each:

- **Motorhomes** split the data across *two* tables — dimensions and berths in one,
  weights in another — keyed by range and layout number. They are joined on
  `(range, layout)`, not on layout alone: Voyager and Trekker both sell a 540, 584 and
  594, on different weights.
- **Campervans** use one table, and name their models (`Trekker`, `Trekker X`,
  `Trekker XL`) rather than numbering them.

## Parsing approach: anchor on the tail, not the columns

The rows are ragged. A row's *leading* columns are engine prose of unpredictable width —
`Ford 130 Bhp 165 Bhp Auto` against `Ford 165 Bhp Auto N/A` against a campervan row with
no chassis make at all. Counting columns from the left therefore doesn't work.

Its *trailing* columns, though, are a fixed run of typed values: metres, then two
integers, then more metres, then a known literal (`Thule`) or the three `kg` figures. So
every pattern here anchors on that tail and never parses the variable part at all.

Three things that bit, each now covered by a test:

1. **Footnote marks are not confined to the columns you read.** Swift annotates figures
   with `+`, `‡`, `△`, `*` and `#`. Allowing for marks on the three weights that matter
   but not on the trailing trailer/train columns silently dropped *every Escape and
   Kon-Tiki weight* — eight of twenty motorhomes, and the failure looked like "those
   ranges just don't publish weights" rather than like a bug.
2. **A model name isn't always one token.** `Trekker`, `Trekker X` and `Trekker XL` are
   three campervans; a lazy match stops at `Trekker` and collapses them into one,
   losing two products. The adapter anchors the name's end on where the engine columns
   begin, matching a chassis make as a capitalised word of 3+ letters precisely so `X`
   and `XL` aren't mistaken for one.
3. **Range headings are discovered, not hardcoded.** A heading is a short line of
   letters with no figures, sitting above its layout rows. A new Swift range needs no
   code change. Footnotes and the symbol legend share these pages and are skipped by
   the same pass.

As with Morelo, Swift publishes MTPLM, MRO *and* payload, so `payload == MTPLM − MRO`
is a free check — here on the *join* between the motorhome brochure's two tables, where
pairing the wrong layout's weights would be out by tens or hundreds of kg. All 30
products reconcile. A small tolerance is allowed because Swift rounds and annotates some
figures (`*` marks an estimate; `†`/`‡` flag an automatic-transmission adjustment).

## Known gaps

- **No price.** Neither brochure quotes one — the motorhome PDF contains a single `£`,
  in unrelated prose. `rrp_pounds` is therefore never proposed for Swift, so a price
  change on a Swift product will not be caught by this adapter at all. This is the one
  significant gap and it is worth a decision:
  - Swift's own product pages (`/motorhomes/product/42117/swift-kon-tiki/`) were **not**
    surveyed for a price — I ran out of time. That is the first place to look, and if a
    per-layout price is there this becomes a straightforward third fetch.
  - Failing that, Swift is an NCC member (`ncc_member=yes` in the registry), so asking
    them for a price list directly is likely to be quicker than scraping dealers.
- **Campervan berths vs. Swift's own marketing.** The table gives Monza 5 seat belts and
  4 berths; the range page's "Quick View" panel repeats the same figures, so they agree.
  No conflict found, but only spot-checked.
- **The brochure URL is a changing opaque media key** (`/media/noeb4jei/...`), so it is
  re-discovered from the index page each run. The registry's `brochure_url` column
  records the current one for reference only — the adapter does not read it.
- Swift also makes caravans, deliberately out of scope for this prototype (DESIGN.md §3).

## Running it

Both catalogues by default; `--range` picks one:

```bash
uv run fmlv run Swift --range Campervans
```

Note this is `cli.resolve_ranges` doing its usual job, but a Swift "range" at that level
is a whole *catalogue*, not a model range — the model ranges (Voyager, Carrera, …) come
out of the brochure and can't be selected from the command line.
