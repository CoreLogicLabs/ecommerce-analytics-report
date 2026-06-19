"""
build_pdf.py
============
Renders a polished, multi-page PDF report with ReportLab.

Static charts are produced with Matplotlib (Agg backend) and embedded as
images, while the document structure -- cover band, KPI table, insights,
channel/category tables -- is laid out with ReportLab's Platypus framework.

Note on glyphs: the report deliberately avoids Unicode sub/superscripts and
arrow symbols, which render as black boxes in ReportLab's standard fonts.
Deltas are shown as coloured ``+/-`` percentages instead.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend -- no display required
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from analytics import (
    ReportData,
    fmt_compact_currency,
    fmt_currency,
    fmt_number,
    fmt_pct,
)

# --------------------------------------------------------------------------- #
# Palette (ReportLab / Matplotlib colour objects)
# --------------------------------------------------------------------------- #
PRIMARY = colors.HexColor("#2563eb")
PRIMARY_DARK = colors.HexColor("#1e40af")
INK = colors.HexColor("#0f172a")
SUCCESS = colors.HexColor("#10b981")
DANGER = colors.HexColor("#ef4444")
MUTED = colors.HexColor("#64748b")
ROW_ALT = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#e5e7eb")

MPL_PRIMARY = "#2563eb"
MPL_SUCCESS = "#10b981"
MPL_PALETTE = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"]

CONTENT_WIDTH = A4[0] - 4 * cm  # page width minus left+right margins


# --------------------------------------------------------------------------- #
# Paragraph styles
# --------------------------------------------------------------------------- #
def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BannerTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=24, textColor=colors.white, leading=28, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "BannerSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=11, textColor=colors.HexColor("#dbeafe"), leading=15,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=base["Normal"], fontName="Helvetica",
            fontSize=9.5, textColor=MUTED, leading=13,
        ),
        "section": ParagraphStyle(
            "Section", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=13, textColor=colors.white, leading=16, alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, textColor=INK, leading=15,
        ),
        "insight": ParagraphStyle(
            "Insight", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, textColor=INK, leading=15,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=INK, leading=12,
        ),
    }


# --------------------------------------------------------------------------- #
# Matplotlib charts -> PNG files
# --------------------------------------------------------------------------- #
def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def chart_daily(data: ReportData, path: Path) -> Path:
    """Daily revenue with its 7-day moving average."""
    d = data.daily
    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    ax.bar(d["date"], d["revenue"], color=MPL_PRIMARY, alpha=0.35, label="Daily revenue")
    ax.plot(d["date"], d["revenue_ma7"], color=MPL_PRIMARY, lw=2.4, label="7-day average")
    ax.set_ylabel("Revenue ($)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.grid(axis="y", color="#e5e7eb", lw=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.yaxis.set_major_formatter(lambda x, _: f"${x/1000:.0f}K")
    fig.autofmt_xdate()
    return _save(fig, path)


def chart_channel(data: ReportData, path: Path) -> Path:
    """Revenue by channel (horizontal bar)."""
    c = data.channel.sort_values("revenue")
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.barh(c["channel"], c["revenue"], color=MPL_PRIMARY)
    ax.set_xlabel("Revenue ($)")
    ax.grid(axis="x", color="#e5e7eb", lw=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.xaxis.set_major_formatter(lambda x, _: f"${x/1000:.0f}K")
    return _save(fig, path)


def chart_category(data: ReportData, path: Path) -> Path:
    """Revenue share by category (donut)."""
    c = data.category
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    wedges, _, autotexts = ax.pie(
        c["revenue"], labels=c["category"], autopct="%1.0f%%",
        colors=MPL_PALETTE, startangle=90, pctdistance=0.78,
        wedgeprops=dict(width=0.42, edgecolor="white"),
        textprops=dict(fontsize=8.5),
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(8)
        t.set_fontweight("bold")
    ax.set(aspect="equal")
    return _save(fig, path)


def chart_roas(data: ReportData, path: Path) -> Path:
    """ROAS by paid channel vs. the blended average."""
    paid = data.channel.dropna(subset=["roas"]).sort_values("roas")
    blended = data.kpis["roas"]
    bar_colors = [MPL_SUCCESS if v >= blended else "#ef4444" for v in paid["roas"]]
    fig, ax = plt.subplots(figsize=(9.5, 2.8))
    bars = ax.bar(paid["channel"], paid["roas"], color=bar_colors, width=0.5)
    ax.axhline(blended, color="#64748b", ls="--", lw=1.2)
    ax.text(len(paid) - 0.5, blended, f" Blended {blended:.1f}x",
            va="bottom", ha="right", color="#64748b", fontsize=8.5)
    ax.bar_label(bars, fmt="%.1fx", padding=3, fontsize=9)
    ax.set_ylabel("ROAS (x)")
    ax.grid(axis="y", color="#e5e7eb", lw=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _save(fig, path)


# --------------------------------------------------------------------------- #
# Flowable helpers
# --------------------------------------------------------------------------- #
def _banner(data: ReportData, st: dict) -> Table:
    """Full-width coloured cover band with the report title."""
    inner = [
        [Paragraph("E-Commerce Performance Report", st["title"])],
        [Paragraph(
            f"Reporting period: {data.period_start} &ndash; {data.period_end} "
            f"&nbsp;&bull;&nbsp; {data.period_days} days", st["subtitle"])],
    ]
    t = Table(inner, colWidths=[CONTENT_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("LEFTPADDING", (0, 0), (-1, -1), 22),
        ("RIGHTPADDING", (0, 0), (-1, -1), 22),
        ("TOPPADDING", (0, 0), (0, 0), 22),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 20),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    return t


def _section_bar(text: str, st: dict) -> Table:
    """A coloured section heading band."""
    t = Table([[Paragraph(text, st["section"])]], colWidths=[CONTENT_WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _styled_table(rows: list[list], col_widths: list[float],
                  extra: list | None = None) -> Table:
    """Build a table with the shared corporate styling."""
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
    ]
    if extra:
        style.extend(extra)
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# Content sections
# --------------------------------------------------------------------------- #
def _kpi_table(data: ReportData, st: dict) -> Table:
    """Executive-summary KPI table with period-over-period deltas."""
    k, pop = data.kpis, data.pop
    header = ["Metric", "Value", "vs Prior Period"]

    def delta(metric: str) -> tuple[str, colors.Color | None]:
        change = pop[metric]["change"]
        sign = "+" if change >= 0 else "-"
        return f"{sign}{fmt_pct(abs(change))}", (SUCCESS if change >= 0 else DANGER)

    spec = [
        ("Total Revenue", fmt_currency(k["total_revenue"]), "total_revenue"),
        ("Gross Profit", fmt_currency(k["gross_profit"]), "gross_profit"),
        ("Net Profit (after ad spend)", fmt_currency(k["net_profit"]), "net_profit"),
        ("Total Ad Spend", fmt_currency(k["total_ad_spend"]), None),
        ("Orders", fmt_number(k["orders"]), "orders"),
        ("Average Order Value", fmt_currency(k["aov"], 2), "aov"),
        ("Blended ROAS", f"{k['roas']:.2f}x", "roas"),
        ("Gross Margin", fmt_pct(k["gross_margin"]), None),
        ("New Customer Rate", fmt_pct(k["new_customer_rate"]), None),
    ]

    rows = [header]
    delta_colors: list[tuple[int, colors.Color]] = []
    for idx, (label, value, metric) in enumerate(spec, start=1):
        if metric:
            text, color = delta(metric)
        else:
            text, color = "--", MUTED
        rows.append([label, value, text])
        delta_colors.append((idx, color))

    extra = [("TEXTCOLOR", (2, i), (2, i), c) for i, c in delta_colors]
    extra.append(("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"))
    return _styled_table(rows, [CONTENT_WIDTH * 0.45, CONTENT_WIDTH * 0.30,
                                CONTENT_WIDTH * 0.25], extra)


def _insights_list(data: ReportData, st: dict) -> ListFlowable:
    items = [
        ListItem(Paragraph(text, st["insight"]), leftIndent=10,
                 value="bullet", bulletColor=PRIMARY)
        for text in data.insights
    ]
    return ListFlowable(items, bulletType="bullet", bulletColor=PRIMARY,
                        leftIndent=14, bulletFontSize=8)


def _channel_table(data: ReportData, st: dict) -> Table:
    header = ["Channel", "Revenue", "Orders", "AOV", "Ad Spend", "ROAS"]
    rows = [header]
    for _, r in data.channel.iterrows():
        roas = "--" if r["roas"] != r["roas"] else f"{r['roas']:.2f}x"  # NaN check
        spend = "--" if r["spend"] == 0 else fmt_currency(r["spend"])
        rows.append([
            r["channel"], fmt_currency(r["revenue"]), fmt_number(r["orders"]),
            fmt_currency(r["aov"], 2), spend, roas,
        ])
    w = CONTENT_WIDTH
    return _styled_table(
        rows, [w * 0.26, w * 0.18, w * 0.13, w * 0.15, w * 0.16, w * 0.12])


def _category_table(data: ReportData, st: dict) -> Table:
    header = ["Category", "Revenue", "Gross Profit", "Margin", "Share"]
    rows = [header]
    for _, r in data.category.iterrows():
        rows.append([
            r["category"], fmt_currency(r["revenue"]),
            fmt_currency(r["gross_profit"]), fmt_pct(r["margin"]),
            fmt_pct(r["revenue_share"]),
        ])
    w = CONTENT_WIDTH
    return _styled_table(
        rows, [w * 0.28, w * 0.20, w * 0.22, w * 0.15, w * 0.15])


def _image(path: Path, width: float = CONTENT_WIDTH) -> Image:
    """Embed a PNG scaled to ``width`` while preserving aspect ratio."""
    img = Image(str(path))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width
    img.drawHeight = width * ratio
    return img


# --------------------------------------------------------------------------- #
# Page furniture (footer + page numbers)
# --------------------------------------------------------------------------- #
def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2 * cm, 1.0 * cm,
                      "E-Commerce Performance Report  |  Automated analytics pipeline")
    canvas.drawRightString(A4[0] - 2 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build(data: ReportData, output_path: str | Path = "output/report.pdf") -> Path:
    """Build the PDF report and write it to ``output_path``."""
    st = _styles()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Charts are rendered to a throwaway directory and embedded during build.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        img_daily = chart_daily(data, tmp / "daily.png")
        img_channel = chart_channel(data, tmp / "channel.png")
        img_category = chart_category(data, tmp / "category.png")
        img_roas = chart_roas(data, tmp / "roas.png")

        story = [
            _banner(data, st),
            Spacer(1, 14),
            _section_bar("Executive Summary", st),
            Spacer(1, 8),
            _kpi_table(data, st),
            Spacer(1, 16),
            _section_bar("Key Insights", st),
            Spacer(1, 8),
            _insights_list(data, st),
            PageBreak(),

            _section_bar("Revenue Trend", st),
            Spacer(1, 8),
            _image(img_daily),
            Spacer(1, 6),
            _image(img_roas),
            PageBreak(),

            _section_bar("Channel Performance", st),
            Spacer(1, 8),
            _image(img_channel, width=CONTENT_WIDTH * 0.62),
            Spacer(1, 8),
            _channel_table(data, st),
            Spacer(1, 18),
            _section_bar("Category Performance", st),
            Spacer(1, 8),
            _image(img_category, width=CONTENT_WIDTH * 0.62),
            Spacer(1, 8),
            _category_table(data, st),
        ]

        doc = SimpleDocTemplate(
            str(output_path), pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=1.6 * cm, bottomMargin=1.8 * cm,
            title="E-Commerce Performance Report",
            author="Automated Reporting Pipeline",
        )
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    size_kb = output_path.stat().st_size / 1024
    print(f"  - report.pdf     : {size_kb:,.0f} KB ({doc.page} pages)")
    return output_path


if __name__ == "__main__":
    from analytics import run_analytics

    build(run_analytics())
