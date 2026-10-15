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
