# Python input and output contract

This describes the Python CLI on the current default branch. The browser edition
is independent and has the limitations listed below.

## CSV input

Use UTF-8 CSV; a UTF-8 byte-order mark is accepted. Required headers are
`invoice_id,client,email,service,amount,status`. Header names are case-sensitive.
Extra named columns are ignored. Python's CSV reader supports quoted fields,
including commas and newlines within a quoted value.

The CLI fails early when a required header is absent. A record with missing cells
is treated as having empty values and is sent to the issue queue when invalid.
Other valid records continue through the pipeline.

| Field | Current behavior |
| --- | --- |
| `invoice_id` | Required after trimming. Accepted IDs must be safe filenames on Windows and POSIX: no path separators, drive prefixes, forbidden filename characters, control characters, trailing periods or Windows device basenames. Safe Unicode, internal spaces and periods are retained. Repeated IDs among accepted records are flagged. |
| `client`, `service` | Required after trimming. HTML output escapes these values. |
| `email` | Trimmed and lowercased; checked for a simple address shape, without delivery verification. |
| `amount` | Must be a finite decimal greater than zero. Exported invoice amounts use two decimal places. Currency is fixed to USD; no tax calculation or exchange conversion is performed. |
| `status` | Trimmed and lowercased; accepted values are `paid` and `pending`. |

Issue row numbers count CSV records from two, including the header position. For a
multiline quoted value, that position is not necessarily the physical file line.

## Outputs

Each run writes `clean_invoices.csv`, `issues.csv`, `summary.json`, `dashboard.html`
and a PDF under `invoices/` for each accepted record. Inspect the issue queue before
using the clean export. The sample dataset is fictional and produces six processed
records, four accepted records, two issues, a USD 2,290 total and four PDFs.

Use a fresh output directory per run. Reusing a directory overwrites the summary
and CSV files but keeps PDFs for invoices that disappeared from the input. Automatic
cleanup of obsolete PDFs is not implemented.

## Limits

The PDF writer uses a basic Latin-1 font encoding and replaces unsupported text
characters. Unicode filenames are accepted, but that does not establish Unicode
PDF text rendering. Branding, tax rules, email delivery and hosted storage require
additional implementation.

The browser edition currently uses a simpler CSV parser, JavaScript numeric
calculations and separate validation. It downloads clean CSV; PDF creation belongs
to the Python CLI. Quoted-field parsing, duplicate-ID handling and rounding parity
need further work before treating the editions as interchangeable.
