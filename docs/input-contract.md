# Input and output contract

The Python CLI and browser edition follow these CSV, validation and money rules.
Shared synthetic cases in `tests/fixtures/contract.json` run in both test suites.
This establishes the covered behavior; edition-specific limits remain below.

## CSV input

Use UTF-8 CSV; a leading UTF-8 byte-order mark is accepted. Required headers are
`invoice_id,client,email,service,amount,status`. Header names are case-sensitive and
are not trimmed. Column order may vary. Extra named columns are ignored. Duplicate
column names fail early rather than silently replacing a value.

Both editions support quoted commas, doubled quotes and newlines within quoted
fields, with LF or CRLF record endings. Empty physical lines are skipped; a quoted
empty field or a comma-only record is still a record to validate. Missing cells
become empty values. A record with more cells than the header is flagged. Other
valid records continue through the pipeline.

Missing required headers or malformed quoting fail the whole input before the CLI
creates outputs. The browser shows an input error and clears its previous results
and downloadable records. Editing the browser input disables download until the
next successful validation run, so an old export cannot be mistaken for an edit.

| Field | Behavior |
| --- | --- |
| `invoice_id` | Required after trimming, at most 251 UTF-8 bytes to leave room for the `.pdf` suffix within a common 255-byte filename component. IDs must be safe filenames on Windows and POSIX: no path separators, drive prefixes, forbidden filename characters, control characters, trailing periods or Windows device basenames. Safe Unicode, internal spaces and periods are retained. Repeated IDs are compared in uppercase, conservatively rejecting case variants that could overwrite the same Windows PDF. Only accepted records reserve an ID; an earlier invalid row does not block a later valid one. |
| `client`, `service` | Required after trimming. HTML output displays these values as text. |
| `email` | Trimmed and lowercased; checked for a simple address shape, without delivery verification. |
| `amount` | ASCII decimal or scientific notation, optionally signed, finite and greater than zero. No currency symbols, group separators, hexadecimal or underscores. An explicit exponent must be between -1000 and 1000. The raw value must not exceed USD 999,999,999,999.99 and must round to at least USD 0.01. |
| `status` | Trimmed and lowercased; accepted values are `paid` and `pending`. |

Issue row numbers count nonblank CSV records from two, including the header
position. For a multiline quoted value, that position is not necessarily the
physical file line.

## Money

Each accepted amount is rounded to two decimal places using **round half to even**
before it is exported or included in the total. For example, `1.005` becomes
`1.00`, `1.015` becomes `1.02`, and `2.675` becomes `2.68`. Two invoices with
`1.005` and `2.005` total `3.00`. A value such as `0.005` rounds to zero and is
flagged, so no zero-value invoice is accepted.

Both editions sum integer cents, avoiding floating point drift and intermediate
decimal-context rounding. The browser uses `BigInt`; Python uses integers and an
explicit decimal rounding context independent of the caller. Currency is fixed
to USD; no tax calculation or exchange conversion is performed.

Python's `AutomationResult` and `summary.json` include `clean_total_decimal`, an
exact two-decimal string. The existing numeric `clean_total` field remains for
compatibility and may be approximate for very large totals. Use
`clean_total_decimal` for exact accounting. CLI and HTML display use the exact
total, including cents.

## Outputs

Each CLI run writes `clean_invoices.csv`, `issues.csv`, `summary.json`,
`dashboard.html` and a PDF under `invoices/` for each accepted record. The browser
downloads clean CSV. Exported email/status are normalized, amounts always have two
decimal places, and CSV quoting preserves commas, quotes and newlines.

Text beginning with `=`, `+`, `-` or `@` is prefixed with an apostrophe in CSV
exports to reduce spreadsheet formula execution. This deliberate export-only
change also applies to issue CSV text; HTML and PDF retain the validated text.
Consumers that require the original text should account for that prefix. Inspect
the issue queue before using the clean export.

The fictional sample produces six processed records, four accepted records, two
issues, a USD 2,290.00 total and four PDFs in the Python edition.

Use a new or empty output directory per CLI run. A non-empty directory is rejected
before any output changes, so PDFs from different runs cannot be mixed with a new
summary or export. Existing files are never automatically deleted.

## Limits

The editions use independent parsers and are not interchangeable in every
environment. The browser accepts pasted text and depends on a modern browser with
`BigInt`; Python reads UTF-8 files and has its CSV library's field-size limit. CSV
can preserve embedded newlines, but browser textareas normalize CRLF inside pasted
values to LF. Unicode casing rules and filesystem limits may also vary by runtime
or operating system; the filename checks do not promise every filesystem alias or
maximum path-length check. Large inputs remain subject to available memory.

The PDF writer uses a basic Latin-1 font encoding and replaces unsupported text
characters; it also has a simple fixed layout. Unicode filenames do not establish
Unicode PDF text rendering. Branding, tax rules, email delivery and hosted storage
require additional implementation. PDF creation belongs to the Python CLI.
