from __future__ import annotations

import sys
from pathlib import Path

import pytest

from invoice_automation import cli


def test_reused_output_has_an_actionable_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sample = Path(__file__).parents[1] / "sample_data" / "invoices.csv"
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "previous-run.txt"
    marker.write_text("keep this run", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["invoice-automation", str(sample), "--output", str(output)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "choose a new or empty directory" in capsys.readouterr().err
    assert marker.read_text(encoding="utf-8") == "keep this run"


@pytest.mark.parametrize(
    "contents",
    [
        'invoice_id,client,email,service,amount,status\nID,"Unfinished\n',
        "invoice_id,client,email,service,amount,status,amount\n",
    ],
)
def test_malformed_input_has_a_cli_error_without_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    contents: str,
) -> None:
    source = tmp_path / "input.csv"
    source.write_text(contents, encoding="utf-8")
    output = tmp_path / "output"
    monkeypatch.setattr(sys, "argv", ["invoice-automation", str(source), "--output", str(output)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert not output.exists()


def test_cli_reports_sum_of_rounded_invoice_cents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "invoice_id,client,email,service,amount,status\n"
        "A,Example,a@example.com,Reporting,1.005,paid\n"
        "B,Example,a@example.com,Reporting,2.005,paid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["invoice-automation", str(source), "--output", str(tmp_path / "output")]
    )

    cli.main()

    assert "total USD 3.00" in capsys.readouterr().out
