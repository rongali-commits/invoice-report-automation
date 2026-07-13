# Invoice & Report Automation

[![CI](https://github.com/rongali-commits/invoice-report-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/rongali-commits/invoice-report-automation/actions/workflows/ci.yml)
[Live application](https://rongali-commits.github.io/invoice-report-automation/) · [Portfolio](https://www.rongalichaitanya.com) · [Discuss a workflow](mailto:hello@rongalichaitanya.com)

A client-style Python workflow that turns recurring billing CSV files into validated exports, an issue queue, run summaries, and printable PDF invoices.

![Generated automation dashboard](docs/screenshot.png)

## Business problem

Operations teams often receive inconsistent spreadsheets, repair rows manually, calculate totals, and create invoices one at a time. That makes a recurring process slow, difficult to audit, and easy to break.

This project demonstrates a safer workflow:

```text
CSV input -> schema checks -> row validation -> clean export + issue queue -> PDF invoices + run summary
```

## Demonstrated outcome

The included fictional dataset produces a repeatable result:

| Measure | Sample run |
| --- | ---: |
| Rows processed | 6 |
| Invoice-ready rows | 4 |
| Rows flagged for review | 2 |
| Validated total | USD 2,290 |
| PDFs generated | 4 |

These are reproducible sample-run measurements, not claims about a real client engagement.

## What it delivers

- required-column and row-level validation;
- normalized email, status, and currency fields;
- clean CSV and separate issue queue;
- one printable PDF per valid invoice;
- JSON run summary and an HTML operations dashboard;
- automated tests for success and failure paths.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
invoice-automation sample_data/invoices.csv --output output
pytest
```

Open `output/dashboard.html` to inspect the run and `output/invoices/` for generated PDFs.

## Expected input

```csv
invoice_id,client,email,service,amount,status
INV-1001,Example Company,accounts@example.com,Monthly reporting,850,paid
```

Accepted statuses are `paid` and `pending`. Invalid rows are never silently discarded; they are written to `issues.csv` with a reason and source row number.

## Repository structure

```text
src/invoice_automation/   validation, output generation, and CLI
site/                     independently hosted browser edition
sample_data/              fictional billing records
tests/                    repeatable pipeline tests
docs/                     verified screenshot
```

## Production handoff

For a real engagement I would adapt column mappings, invoice branding, currency and tax rules, delivery channels, and storage to the client's process. Email or cloud uploads would be added behind explicit credentials and an audit log. No client data, secrets, or third-party API keys are included here.

## License

MIT — see [LICENSE](LICENSE).
