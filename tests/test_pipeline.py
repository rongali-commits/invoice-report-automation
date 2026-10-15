from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from invoice_automation import pipeline, run_automation


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

    assert not (tmp_path / "output").exists()


def test_output_reuse_preserves_every_file_from_the_previous_run(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    header = "invoice_id,client,email,service,amount,status\n"
    source.write_text(header + "OLD,Example,a@example.com,Reporting,10,paid\n", encoding="utf-8")
    output = tmp_path / "output"
    run_automation(source, output)
    before = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    source.write_text(header + "NEW,Example,a@example.com,Reporting,20,paid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Output directory is not empty"):
        run_automation(source, output)

    after = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    assert after == before
    assert not (output / "invoices" / "NEW.pdf").exists()


def test_output_path_cannot_replace_an_existing_file(tmp_path: Path) -> None:
    sample = Path(__file__).parents[1] / "sample_data" / "invoices.csv"
    output = tmp_path / "notes.txt"
    output.write_text("keep this file", encoding="utf-8")

    with pytest.raises(ValueError, match="Output path is not a directory"):
        run_automation(sample, output)

    assert output.read_text(encoding="utf-8") == "keep this file"


@pytest.mark.parametrize("amount", ["Infinity", "-Infinity", "NaN", "sNaN"])
def test_nonfinite_amounts_are_queued_without_blocking_valid_rows(
    tmp_path: Path, amount: str
) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        f"BAD,Example,a@example.com,Reporting,{amount},paid\n"
        "GOOD,Example,a@example.com,Reporting,12.50,pending\n",
        encoding="utf-8",
    )

    result = run_automation(source, tmp_path / "output")

    assert (result.rows_read, result.ready_rows, result.flagged_rows) == (2, 1, 1)
    assert result.clean_total == 12.50
    summary = json.loads(
        (result.output_directory / "summary.json").read_text(encoding="utf-8"),
        parse_constant=lambda value: pytest.fail(f"Non-standard JSON constant: {value}"),
    )
    assert summary["clean_total"] == 12.50
    with (result.output_directory / "issues.csv").open(newline="", encoding="utf-8") as handle:
        issue = next(csv.DictReader(handle))
    assert issue["row_number"] == "2"
    assert "amount" in issue["reason"]
    assert sorted(path.name for path in (result.output_directory / "invoices").glob("*.pdf")) == [
        "GOOD.pdf"
    ]


@pytest.mark.parametrize(
    "short_row",
    [
        "BAD,Example,a@example.com,Reporting,10",
        "BAD,Example,a@example.com,Reporting",
    ],
)
def test_truncated_rows_are_queued_and_following_rows_still_run(
    tmp_path: Path, short_row: str
) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        f"{short_row}\n"
        "GOOD,Example,a@example.com,Reporting,12.50,pending\n",
        encoding="utf-8",
    )

    result = run_automation(source, tmp_path / "output")

    assert (result.rows_read, result.ready_rows, result.flagged_rows) == (2, 1, 1)
    assert result.clean_total == 12.50
    with (result.output_directory / "issues.csv").open(newline="", encoding="utf-8") as handle:
        issue = next(csv.DictReader(handle))
    assert issue["row_number"] == "2"
    assert "status" in issue["reason"]
    assert sorted(path.name for path in (result.output_directory / "invoices").glob("*.pdf")) == [
        "GOOD.pdf"
    ]


@pytest.mark.parametrize(
    "invoice_id",
    [
        "../escape",
        "..\\escape",
        "/absolute",
        "C:\\absolute",
        "C:relative",
        ".",
        "..",
        "CON",
        "CONIN$",
        "CONOUT$",
        "nul.txt",
        "COM1",
        "LPT9.txt",
        "trailing.",
        "bad<name",
        "bad|name",
        "bad\x00name",
        "bad\nname",
        "COM¹",
        "LPT².txt",
        "CON .txt",
    ],
)
def test_unsafe_invoice_ids_never_reach_the_pdf_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invoice_id: str
) -> None:
    source = tmp_path / "input.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["invoice_id", "client", "email", "service", "amount", "status"])
        writer.writerow([invoice_id, "Example", "a@example.com", "Reporting", "10", "paid"])
    paths: list[Path] = []
    monkeypatch.setattr(pipeline, "_write_invoice_pdf", lambda path, invoice: paths.append(path))

    result = run_automation(source, tmp_path / "output")

    assert paths == []
    assert (result.ready_rows, result.flagged_rows) == (0, 1)
    with (result.output_directory / "issues.csv").open(newline="", encoding="utf-8") as handle:
        issue = next(csv.DictReader(handle))
    assert issue["invoice_id"] == invoice_id
    assert "invoice_id" in issue["reason"]


@pytest.mark.parametrize(
    "invoice_id",
    ["INV-1001", "invoice_2", "2026.10-01", "CONTRACT-1", "客户 2026.10", ".hidden-invoice"],
)
def test_safe_invoice_ids_generate_pdfs(tmp_path: Path, invoice_id: str) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        f"{invoice_id},Example,a@example.com,Reporting,12.50,paid\n",
        encoding="utf-8",
    )

    result = run_automation(source, tmp_path / "output")

    assert (result.ready_rows, result.flagged_rows) == (1, 0)
    assert result.clean_total == 12.50
    pdf = result.output_directory / "invoices" / f"{invoice_id}.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
