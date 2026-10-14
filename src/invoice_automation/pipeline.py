from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = {"invoice_id", "client", "email", "service", "amount", "status"}
VALID_STATUSES = {"paid", "pending"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UNSAFE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_STEMS = (
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{number}" for number in "123456789¹²³"}
    | {f"LPT{number}" for number in "123456789¹²³"}
)


@dataclass(frozen=True)
class CleanInvoice:
    invoice_id: str
    client: str
    email: str
    service: str
    amount: str
    status: str


@dataclass(frozen=True)
class Issue:
    row_number: int
    invoice_id: str
    reason: str


@dataclass(frozen=True)
class AutomationResult:
    rows_read: int
    ready_rows: int
    flagged_rows: int
    clean_total: float
    currency: str
    output_directory: Path


def run_automation(input_path: Path, output_directory: Path) -> AutomationResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    invoices_directory = output_directory / "invoices"
    invoices_directory.mkdir(exist_ok=True)

    clean_rows, issues = _read_and_validate(input_path)
    total = sum(Decimal(row.amount) for row in clean_rows)

    _write_csv(output_directory / "clean_invoices.csv", clean_rows)
    _write_issues(output_directory / "issues.csv", issues)
    for invoice in clean_rows:
        _write_invoice_pdf(invoices_directory / f"{invoice.invoice_id}.pdf", invoice)

    result = AutomationResult(
        rows_read=len(clean_rows) + len(issues),
        ready_rows=len(clean_rows),
        flagged_rows=len(issues),
        clean_total=float(total),
        currency="USD",
        output_directory=output_directory,
    )
    (output_directory / "summary.json").write_text(
        json.dumps({**asdict(result), "output_directory": str(output_directory)}, indent=2),
        encoding="utf-8",
    )
    (output_directory / "dashboard.html").write_text(
        _dashboard_html(result, clean_rows, issues), encoding="utf-8"
    )
    return result


def _read_and_validate(input_path: Path) -> tuple[list[CleanInvoice], list[Issue]]:
    clean_rows: list[CleanInvoice] = []
    issues: list[Issue] = []
    seen_ids: set[str] = set()

    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

        for row_number, raw in enumerate(reader, start=2):
            # DictReader uses None for cells missing from a truncated row.
            raw = {column: raw.get(column) or "" for column in REQUIRED_COLUMNS}
            invoice_id = raw["invoice_id"].strip()
            reasons: list[str] = []
            try:
                amount = Decimal(raw["amount"].strip())
                if not amount.is_finite():
                    reasons.append("amount must be finite")
                elif amount <= 0:
                    reasons.append("amount must be greater than zero")
            except InvalidOperation:
                amount = Decimal(0)
                reasons.append("amount is not a number")

            email = raw["email"].strip().lower()
            if not EMAIL_PATTERN.match(email):
                reasons.append("email is missing or invalid")
            if not invoice_id:
                reasons.append("invoice_id is required")
            elif (
                invoice_id in {".", ".."}
                or UNSAFE_FILENAME_PATTERN.search(invoice_id)
                or invoice_id.endswith((".", " "))
                or invoice_id.partition(".")[0].rstrip(" ").upper() in WINDOWS_RESERVED_STEMS
            ):
                reasons.append("invoice_id must be a safe filename")
            elif invoice_id in seen_ids:
                reasons.append("invoice_id is duplicated")
            status = raw["status"].strip().lower()
            if status not in VALID_STATUSES:
                reasons.append("status must be paid or pending")
            if not raw["client"].strip() or not raw["service"].strip():
                reasons.append("client and service are required")

            if reasons:
                issues.append(Issue(row_number, invoice_id, "; ".join(reasons)))
                continue

            seen_ids.add(invoice_id)
            clean_rows.append(
                CleanInvoice(
                    invoice_id=invoice_id,
                    client=raw["client"].strip(),
                    email=email,
                    service=raw["service"].strip(),
                    amount=f"{amount:.2f}",
                    status=status,
                )
            )
    return clean_rows, issues


def _write_csv(path: Path, rows: list[CleanInvoice]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CleanInvoice.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def _write_issues(path: Path, issues: list[Issue]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Issue.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(issue) for issue in issues)


def _write_invoice_pdf(path: Path, invoice: CleanInvoice) -> None:
    fields = [
        ("Invoice", invoice.invoice_id),
        ("Client", invoice.client),
        ("Email", invoice.email),
        ("Service", invoice.service),
        ("Amount", f"USD {invoice.amount}"),
        ("Status", invoice.status.title()),
    ]
    lines = ["BT", "/F1 22 Tf", "72 770 Td", "(Invoice-ready output) Tj", "/F1 11 Tf"]
    lines.extend(["0 -24 Td", "(Generated from validated sample billing data.) Tj"])
    for label, value in fields:
        lines.extend(["0 -30 Td", f"({_pdf_text(label + ': ' + value)}) Tj"])
    lines.append("ET")
    stream = "\n".join(lines).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    path.write_bytes(pdf)


def _pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _dashboard_html(
    result: AutomationResult, clean_rows: list[CleanInvoice], issues: list[Issue]
) -> str:
    invoice_rows = "".join(
        f"<tr><td>{html.escape(row.invoice_id)}</td><td>{html.escape(row.client)}</td>"
        f"<td>{html.escape(row.service)}</td><td>${html.escape(row.amount)}</td>"
        f"<td><span class='badge'>{html.escape(row.status)}</span></td></tr>"
        for row in clean_rows
    )
    issue_rows = "".join(
        f"<li><strong>Row {issue.row_number}</strong> — {html.escape(issue.reason)}</li>"
        for issue in issues
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Invoice automation report</title><style>
body{{font:16px Inter,Arial,sans-serif;background:#f7f8fc;color:#15213a;margin:0;padding:48px}}
main{{max-width:1100px;margin:auto}}p{{color:#5f6b80}}.eyebrow{{color:#4f46e5;font-weight:700}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}}.card,table,.issues{{background:white;border:1px solid #e3e7ef;border-radius:16px;box-shadow:0 12px 35px #1f2a4410}}
.card{{padding:24px}}.card strong{{font-size:34px;display:block}}table{{width:100%;border-collapse:collapse;overflow:hidden}}th,td{{padding:16px;text-align:left;border-bottom:1px solid #edf0f5}}th{{background:#eef2ff;color:#3730a3}}.badge{{background:#dcfce7;color:#166534;padding:5px 9px;border-radius:999px}}.issues{{padding:22px;margin-top:20px}}li{{margin:9px 0}}@media(max-width:700px){{body{{padding:20px}}.stats{{grid-template-columns:1fr}}}}
</style></head><body><main><div class="eyebrow">AUTOMATION RUN / SAFE SAMPLE DATA</div>
<h1>Invoice & report automation</h1><p>Validated billing rows, issue tracking, clean exports, and printable PDF invoices.</p>
<section class="stats"><div class="card"><strong>{result.rows_read}</strong>rows processed</div><div class="card"><strong>{result.ready_rows}</strong>invoice-ready</div><div class="card"><strong>${result.clean_total:,.0f}</strong>validated total</div></section>
<table><thead><tr><th>Invoice</th><th>Client</th><th>Service</th><th>Amount</th><th>Status</th></tr></thead><tbody>{invoice_rows}</tbody></table>
<section class="issues"><h2>{result.flagged_rows} rows require review</h2><ul>{issue_rows}</ul></section>
</main></body></html>"""
