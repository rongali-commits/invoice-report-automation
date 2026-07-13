from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from invoice_automation import run_automation


def test_sample_pipeline_generates_auditable_outputs(tmp_path: Path) -> None:
    sample = Path(__file__).parents[1] / "sample_data" / "invoices.csv"

    result = run_automation(sample, tmp_path)

    assert result.rows_read == 6
    assert result.ready_rows == 4
    assert result.flagged_rows == 2
    assert result.clean_total == 2290.0
    assert len(list((tmp_path / "invoices").glob("*.pdf"))) == 4
    assert (tmp_path / "invoices" / "INV-1001.pdf").read_bytes().startswith(b"%PDF")
    assert json.loads((tmp_path / "summary.json").read_text())["ready_rows"] == 4

    with (tmp_path / "issues.csv").open(newline="", encoding="utf-8") as handle:
        issues = list(csv.DictReader(handle))
    assert "email is missing or invalid" in issues[0]["reason"]


def test_missing_columns_fail_early(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("client,amount\nExample,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required columns"):
        run_automation(invalid, tmp_path / "output")

