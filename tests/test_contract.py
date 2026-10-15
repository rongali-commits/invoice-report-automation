from __future__ import annotations

import csv
import json
from dataclasses import asdict
from decimal import ROUND_UP, Inexact, localcontext
from pathlib import Path

import pytest

from invoice_automation import pipeline, run_automation

CASES = json.loads((Path(__file__).parent / "fixtures" / "contract.json").read_text("utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_browser_and_cli_contract(tmp_path: Path, case: dict) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(case["csv"].encode("utf-8"))
    output = tmp_path / "output"
    if "error" in case:
        with pytest.raises(ValueError, match=case["error"]):
            run_automation(source, output)
        assert not output.exists()
        return

    clean, issues = pipeline._read_and_validate(source)
    assert [asdict(row) for row in clean] == case["clean"]
    assert [asdict(issue) for issue in issues] == case["issues"]
    # A maximum-length component can exceed a Windows full-path limit under
    # pytest's long temporary directory. That OS boundary is documented.
    if case.get("validation_only"):
        return
    result = run_automation(source, output)
    assert result.rows_read == len(case["clean"]) + len(case["issues"])
    assert result.clean_total_decimal == case["total"]
    summary = json.loads((output / "summary.json").read_text("utf-8"))
    assert summary["clean_total_decimal"] == case["total"]
    assert isinstance(summary["clean_total"], (float, int))
    assert len(list((output / "invoices").glob("*.pdf"))) == len(case["clean"])
    with (output / "clean_invoices.csv").open(newline="", encoding="utf-8") as handle:
        exported = list(csv.DictReader(handle))
    expected = [
        {
            name: "'" + value if value.startswith(("=", "+", "-", "@")) else value
            for name, value in row.items()
        }
        for row in case["clean"]
    ]
    assert exported == expected


def test_money_does_not_inherit_decimal_context(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        "A,Example,a@example.com,Reporting,1.005,paid\n"
        "B,Example,a@example.com,Reporting,1.015,paid\n",
        encoding="utf-8",
    )
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        result = run_automation(source, tmp_path / "output")
    assert result.clean_total_decimal == "2.02"
    assert "$2.02" in (result.output_directory / "dashboard.html").read_text("utf-8")


def test_case_variants_never_overwrite_the_first_pdf(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        "INV-1,First,a@example.com,Reporting,1,paid\n"
        "inv-1,Second,a@example.com,Reporting,2,paid\n",
        encoding="utf-8",
    )
    result = run_automation(source, tmp_path / "output")
    assert (result.ready_rows, result.flagged_rows) == (1, 1)
    assert b"First" in (result.output_directory / "invoices" / "INV-1.pdf").read_bytes()


def test_dashboard_escapes_input_and_shows_cents(tmp_path: Path) -> None:
    case = next(case for case in CASES if case["name"] == "safe_text_and_formula_export")
    source = tmp_path / "input.csv"
    source.write_bytes(case["csv"].encode("utf-8"))
    result = run_automation(source, tmp_path / "output")
    dashboard = (result.output_directory / "dashboard.html").read_text("utf-8")
    assert "<img src=x onerror=alert(1)>" not in dashboard
    assert "&lt;img src=x onerror=alert(1)&gt;" in dashboard
    assert "$3.00" in dashboard
