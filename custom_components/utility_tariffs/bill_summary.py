"""The bill so far as one self-contained HTML page, for an email, a card or a printout."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from html import escape

from utility_tariffs_lib.tariff import PeriodBill, TariffDefinition
from utility_tariffs_lib.tariff.engine import Line

_STYLE = """
:root{color-scheme:light dark;--fg:#1c1c1e;--bg:#fff;--line:#d8d8dc;--muted:#6b6b72}
@media(prefers-color-scheme:dark){:root{--fg:#f2f2f4;--bg:#1c1c1e;--line:#3a3a3f;--muted:#a0a0a8}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif}
main{max-width:640px;margin:0 auto}
h1{font-size:1.3rem;margin:0 0 4px}p{margin:4px 0;color:var(--muted)}
table{width:100%;border-collapse:collapse;margin:16px 0}
td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.total td{font-weight:700;border-top:2px solid var(--fg)}
""".strip()


def _money(value: Decimal, currency: str) -> str:
    return f"{value:,.2f} {currency}"


def _label(key: str, line: Line) -> str:
    return line.name or key.replace("_", " ").capitalize()


def statement(key: str, line: Line) -> list[tuple[str, Decimal, bool]]:
    """The lines of a bill as a supplier lists them, flat and in the order they are worked out.

    A wrapper (a sum, or the tree around a saving or a tax) adds no line of its own. A saving
    shows the amount it took off, and a tax the tax it reported. The flag is true for a tax
    already inside the price, which is part of the other lines and not added to them.
    """
    if line.kind == "sum":
        return [row for k, child in line.children.items() for row in statement(k, child)]
    if line.kind in {"adjust", "tax"}:
        inner_line = line.children["of"]
        inner = statement("of", inner_line)
        change = line.tax if line.tax is not None else line.amount
        included = line.kind == "tax" and line.amount == inner_line.amount
        return [*inner, (_label(key, line), change, included)]
    if line.children and line.kind in {"energy_by_band", "tiered_energy", "export_credit"}:
        prefix = "Export " if line.kind == "export_credit" else ""
        return [(f"{prefix}{name}", child.amount, False) for name, child in line.children.items()]
    return [(_label(key, line), line.amount, False)]


def _rows(lines: list[tuple[str, Decimal, bool]], currency: str) -> list[str]:
    return [
        f'<tr><td>{escape(label)}</td><td class="n">{escape(_money(amount, currency))}</td></tr>'
        for label, amount, _included in lines
    ]


def _usage_rows(bill: PeriodBill) -> list[str]:
    return [
        f'<tr><td>{escape(band)}</td><td class="n">{kwh:,.1f} kWh</td></tr>'
        for band, kwh in bill.import_kwh_by_band.items()
    ]


def _when(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


def render_bill_html(bill: PeriodBill, definition: TariffDefinition, title: str) -> str:
    """The bill so far, with the energy used in each band and every line of the bill."""
    currency = definition.currency
    through = bill.through
    lines = statement("bill", bill.priced.root)
    parts = [
        f"<h1>{escape(title)}</h1>",
        f"<p>Bill period {_when(bill.first_day)} to {_when(bill.next_first_day)}. "
        f"Priced to {_when(through)}, {bill.days} of {bill.period_days} days.</p>",
        f"<p>Based on {bill.coverage * 100:.0f}% of the time recorded by your meters.</p>",
        "<table><caption hidden>Energy used</caption><thead><tr><th>Band</th>"
        '<th class="n">Imported</th></tr></thead><tbody>',
        *_usage_rows(bill),
        "</tbody></table>",
        "<table><caption hidden>Bill</caption><thead><tr><th>Line</th>"
        '<th class="n">Amount</th></tr></thead><tbody>',
        *_rows(lines, currency),
        f'<tr class="total"><td>Total so far</td><td class="n">'
        f"{escape(_money(bill.priced.total, currency))}</td></tr>",
        "</tbody></table>",
        "<p>A priced estimate from the energy your meters counted. Your supplier's bill is the one "
        "that counts.</p>",
    ]
    body = "\n".join(parts)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )
