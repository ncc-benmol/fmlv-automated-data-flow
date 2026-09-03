# Run schedule — field guide

`schedule.csv` is the master list of automated runs. One row per scheduled item. It's
a plain CSV so it can be opened and edited directly in Excel (or any spreadsheet
app) — add a row for a new schedule, delete one to stop it, or flip `enabled` to
pause/resume without deleting anything.

The web app's `/schedules` page shows this file's contents (plus, for each row, when
it last actually ran and when it's next due) but is **read-only** — this CSV is the
one place schedules are created or changed.

## Columns

| Column | Required | Values | Notes |
|---|---|---|---|
| `schedule_id` | yes | short text, unique | A human-readable label for this schedule row (e.g. `adria-full-weekly`). Only used for display and to tell rows apart — not looked up anywhere else. |
| `manufacturer_id` | yes | integer | Must match a `manufacturer_id` in `manufacturers.csv`. One manufacturer per schedule row — to cover several manufacturers, add one row each. |
| `ranges` | | comma-separated range names, or blank | Which model range(s) to run, e.g. `Matrix` or `Matrix, Sonic`. **Blank means the whole manufacturer** — every range. Only adapters that publish named ranges (see each adapter's `DEFAULT_RANGES`) support this; leave blank for manufacturers where it doesn't apply. |
| `first_run` | yes | `YYYY-MM-DD HH:MM` (Europe/London, 24-hour clock) | The first time this schedule should fire. If this is in the past when the app starts, the run fires at the next scheduler check rather than being skipped. |
| `frequency_value` | yes | positive integer | How often to repeat, paired with `frequency_unit` — e.g. `1` + `days` = daily, `7` + `days` = weekly. |
| `frequency_unit` | yes | `hours` / `days` / `weeks` | The unit for `frequency_value`. |
| `enabled` | yes | `true` / `false` | `false` pauses this schedule without deleting the row — it stays visible on `/schedules` but never fires. |
| `notes` | | free text | Anything worth remembering about why this schedule exists. |

## How "next due" is worked out

There's no separate "last run" column to keep up to date by hand — the app works
this out itself from the existing run history (the same `run` table the "Review
runs" page reads), so this file stays purely declarative:

- If this schedule has never produced a run yet, it's due at `first_run`.
- Otherwise, it's due at *(the start time of its most recent scheduled run)* +
  *(`frequency_value` `frequency_unit`)*.

A scheduled run that fails is **not** retried early — the next attempt still waits
for the normal interval to come round, rather than hammering a flaky source.

## Loading and validation

`src.scheduling.load(path)` reads this file the same way `src.registry.load` reads
`manufacturers.csv`: a bad row is reported as an `Issue` rather than stopping the
whole file from loading. Checked at load time: `manufacturer_id` and `first_run`
are present and parse, `frequency_value` is a positive integer, `frequency_unit` is
one of the three known units, and `schedule_id` is unique across rows.

## `vehicle_class`

Which FMLV product area this row sweeps: `motorhome` (the default when the column is
blank or absent) or `caravan`.

**A manufacturer that builds both needs two rows, not one.** Bailey has a motorhome
adapter and a caravan adapter, and a schedule row names one of them — there is no row
that means "sweep everything Bailey makes". That is deliberate rather than an omission:

* The two are separate FMLV exports with separate schemas, reviewed separately and
  uploaded through separate importers. A single run producing both would have to produce
  two CSVs, and the reviewer would have two different-shaped change queues under one run.
* **Their model years do not roll over together.** Caravan and motorhome ranges are
  announced at different shows, so the cadence that suits one rarely suits the other.

"Due" is worked out per area — a caravan row is not held back by the motorhome row having
run this morning. The one thing still shared is the in-progress guard: only one sweep of
any kind runs against a manufacturer at a time, because both hit the same web server and
we are a guest on it.

An unrecognised value is a warning, not an error, and the row is treated as `motorhome`.
