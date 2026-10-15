from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path

REQUIRED_COLUMNS = {"invoice_id", "client", "email", "service", "amount", "status"}
VALID_STATUSES = {"paid", "pending"}
AMOUNT_PATTERN = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE]([+-]?[0-9]+))?$")
NONFINITE_PATTERN = re.compile(r"^[+-]?(?:inf(?:inity)?|s?nan[0-9]*)$", re.IGNORECASE)
MAX_AMOUNT = Decimal("999999999999.99")
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
    clean_total_decimal: str
    currency: str
    output_directory: Path


def run_automation(input_path: Path, output_directory: Path) -> AutomationResult:
    if output_directory.exists():
        if not output_directory.is_dir():
            raise ValueError(f"Output path is not a directory: {output_directory}")
        if any(output_directory.iterdir()):
            raise ValueError(
                f"Output directory is not empty: {output_directory}; "
                "choose a new or empty directory to preserve previous runs."
            )

    clean_rows, issues = _read_and_validate(input_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    invoices_directory = output_directory / "invoices"
    invoices_directory.mkdir(exist_ok=True)

    total_cents = sum(int(row.amount.replace(".", "")) for row in clean_rows)
    total = _format_cents(total_cents)

    _write_csv(output_directory / "clean_invoices.csv", clean_rows)
    _write_issues(output_directory / "issues.csv", issues)
    for invoice in clean_rows:
        _write_invoice_pdf(invoices_directory / f"{invoice.invoice_id}.pdf", invoice)

    result = AutomationResult(
        rows_read=len(clean_rows) + len(issues),
        ready_rows=len(clean_rows),
        flagged_rows=len(issues),
        clean_total=float(total),
        clean_total_decimal=total,
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


def _format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _normalize_amount(value: str) -> str:
    text = value.strip()
    if NONFINITE_PATTERN.fullmatch(text):
        raise ValueError("amount must be finite")
    match = AMOUNT_PATTERN.fullmatch(text)
    if not match:
        raise ValueError("amount is not a number")
    exponent = (match.group(1) or "0").lstrip("+-").lstrip("0") or "0"
    if len(exponent) > 4 or int(exponent) > 1000:
        raise ValueError("amount exponent must be between -1000 and 1000")
    amount = Decimal(text)
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    if amount > MAX_AMOUNT:
        raise ValueError("amount must not exceed USD 999999999999.99")
    # Do not inherit a caller's precision or rounding mode. The bounded amount
    # has at most 14 significant digits once rounded to cents.
    with localcontext(Context(prec=20, rounding=ROUND_HALF_EVEN)):
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        raise ValueError("amount must round to at least USD 0.01")
    return f"{rounded:.2f}"


def _read_and_validate(input_path: Path) -> tuple[list[CleanInvoice], list[Issue]]:
    try:
        return _read_records(input_path)
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV: {exc}") from None


def _read_records(input_path: Path) -> tuple[list[CleanInvoice], list[Issue]]:
    clean_rows: list[CleanInvoice] = []
    issues: list[Issue] = []
    seen_ids: set[str] = set()

    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = (cells for cells in csv.reader(handle, strict=True) if cells)
        headers = next(reader, [])
        missing = REQUIRED_COLUMNS - set(headers)
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        if len(headers) != len(set(headers)):
            raise ValueError("Duplicate column names are not allowed")

        for row_number, cells in enumerate(reader, start=2):
            extra_cells = len(cells) > len(headers)
            raw = {
                column: cells[headers.index(column)] if headers.index(column) < len(cells) else ""
                for column in REQUIRED_COLUMNS
            }
            invoice_id = raw["invoice_id"].strip()
            reasons: list[str] = []
            if extra_cells:
                reasons.append("row has more cells than header")
            try:
                amount = _normalize_amount(raw["amount"])
            except ValueError as exc:
                amount = ""
                reasons.append(str(exc))

            email = raw["email"].strip().lower()
            if not EMAIL_PATTERN.match(email):
                reasons.append("email is missing or invalid")
            if not invoice_id:
                reasons.append("invoice_id is required")
            elif len(invoice_id.encode("utf-8")) > 251:
                reasons.append("invoice_id must be at most 251 UTF-8 bytes")
            elif (
                invoice_id in {".", ".."}
                or UNSAFE_FILENAME_PATTERN.search(invoice_id)
                or invoice_id.endswith((".", " "))
                or invoice_id.partition(".")[0].rstrip(" ").upper() in WINDOWS_RESERVED_STEMS
            ):
                reasons.append("invoice_id must be a safe filename")
            elif invoice_id.upper() in seen_ids:
                reasons.append("invoice_id is duplicated")
            status = raw["status"].strip().lower()
            if status not in VALID_STATUSES:
                reasons.append("status must be paid or pending")
            if not raw["client"].strip() or not raw["service"].strip():
                reasons.append("client and service are required")

            if reasons:
                issues.append(Issue(row_number, invoice_id, "; ".join(reasons)))
                continue

            seen_ids.add(invoice_id.upper())
            clean_rows.append(
                CleanInvoice(
                    invoice_id=invoice_id,
                    client=raw["client"].strip(),
                    email=email,
                    service=raw["service"].strip(),
                    amount=amount,
                    status=status,
                )
            )
    return clean_rows, issues


def _write_csv(path: Path, rows: list[CleanInvoice]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CleanInvoice.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(
            {key: _spreadsheet_text(value) for key, value in asdict(row).items()} for row in rows
        )


def _spreadsheet_text(value: str) -> str:
    # CSV quoting protects structure; an apostrophe also protects spreadsheet
    # users from executing a supplied formula when they open the export.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _write_issues(path: Path, issues: list[Issue]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Issue.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(
            {
                key: _spreadsheet_text(value) if isinstance(value, str) else value
                for key, value in asdict(issue).items()
            }
            for issue in issues
        )


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
<section class="stats"><div class="card"><strong>{result.rows_read}</strong>rows processed</div><div class="card"><strong>{result.ready_rows}</strong>invoice-ready</div><div class="card"><strong>${Decimal(result.clean_total_decimal):,.2f}</strong>validated total</div></section>
<table><thead><tr><th>Invoice</th><th>Client</th><th>Service</th><th>Amount</th><th>Status</th></tr></thead><tbody>{invoice_rows}</tbody></table>
<section class="issues"><h2>{result.flagged_rows} rows require review</h2><ul>{issue_rows}</ul></section>
</main></body></html>"""
