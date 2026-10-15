# Contributing to LedgerFlow

LedgerFlow helps people who prepare recurring billing files validate a CSV, inspect
exceptions and produce invoice-ready output. Useful contributions make this workflow
more reliable or easier to complete.

## Set up the Python edition

Fork this repository, clone your fork and create a branch for the change. Use Python
3.11 or newer, then run these commands from the repository root:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
invoice-automation sample_data/invoices.csv --output output
python -m pytest -q
python -m ruff check .
```

The fictional sample should produce six processed rows, four invoice-ready rows,
two flagged rows, a USD 2,290 total and four PDFs. Inspect `output/issues.csv`,
`output/summary.json` and `output/dashboard.html`. Use a fresh output directory for
each run: non-empty directories are rejected to preserve previous reports and
invoice PDFs. Choose another directory with `--output output-next` for a second run.

## Check the browser edition

The browser edition is a separate implementation in `site/index.html`. It validates
CSV data and downloads a clean CSV; PDF generation belongs to the Python edition.
It currently supports a simpler CSV format than Python's parser.

```sh
python -m http.server 8000 --directory site
```

Open <http://localhost:8000>. Verify the sample totals, exceptions, editing, sample
restoration and downloaded CSV. A shared feature needs checks in both editions;
passing Python tests alone does not verify browser behavior.

## Report a reproducible problem

Search existing [issues](https://github.com/rongali-commits/invoice-report-automation/issues)
and pull requests before starting. Include the edition, version or commit, relevant
Python/browser version, a small fictional input, reproduction steps, expected output
and actual output. Replace client names and billing information with synthetic data.

For a feature request, describe the workflow that is difficult today and how the
proposed change helps. Discuss larger changes in an issue before implementation.

## Submit a change

Keep the patch focused. For a bug fix, add a regression that demonstrates the original
failure and passes with the fix. Preserve the sample results and existing behavior
outside the intended change. Run the checks above and describe what you verified,
including any limitations.

Explain the cause and the before/after behavior in the pull request. Review each
change and be ready to answer questions about the behavior and validation.
Contributions are reviewed for usefulness and correctness; no one needs to star or
follow the project to participate.
