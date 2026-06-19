"""
build_dashboard.py
==================
Renders a self-contained, interactive HTML dashboard with Plotly.

The output is a single ``dashboard.html`` file with the Plotly library embedded
inline -- no web server and no internet connection are required to open it.

Layout:
    * a header band with the report period,
    * a responsive row of KPI cards (each with a coloured up/down delta),
    * a dark "Key Insights" panel driven by the auto-insight engine,
    * a responsive grid of interactive charts.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.offline import plot as plot_div
from plotly.subplots import make_subplots

from analytics import (
    DANGER,
    PRIMARY,
    SUCCESS,
    ReportData,
    fmt_compact_currency,
    fmt_currency,
    fmt_number,
    fmt_pct,
)

# Ordered, qualitative palette for categorical charts.
CHART_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"]
GRID_COLOR = "#e5e7eb"
TEXT_COLOR = "#334155"


# --------------------------------------------------------------------------- #
# Figure styling
# --------------------------------------------------------------------------- #
def _style(fig: go.Figure, height: int = 340) -> go.Figure:
    """Apply a consistent, clean theme to a figure."""
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(family="Inter, 'Segoe UI', sans-serif", color=TEXT_COLOR, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hoverlabel=dict(font_size=12),
    )
    fig.update_xaxes(gridcolor=GRID_COLOR, zeroline=False)
    fig.update_yaxes(gridcolor=GRID_COLOR, zeroline=False)
    return fig


def _to_div(fig: go.Figure) -> str:
    """Serialise a figure to an embeddable ``<div>`` (no inline plotly.js)."""
    return plot_div(
        fig,
        output_type="div",
        include_plotlyjs=False,
        config={"displayModeBar": False, "responsive": True},
    )


# --------------------------------------------------------------------------- #
# Individual charts
# --------------------------------------------------------------------------- #
def chart_daily(data: ReportData) -> str:
    """Combo chart: daily revenue (bars) with a 7-day average and orders line."""
    d = data.daily
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_bar(
        x=d["date"], y=d["revenue"], name="Revenue",
        marker_color=PRIMARY, opacity=0.55,
        hovertemplate="%{x|%b %d}<br>Revenue: $%{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        x=d["date"], y=d["revenue_ma7"], name="Revenue (7d avg)",
        mode="lines", line=dict(color=PRIMARY, width=3),
        hovertemplate="%{x|%b %d}<br>7d avg: $%{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        x=d["date"], y=d["orders"], name="Orders",
        mode="lines", line=dict(color=SUCCESS, width=2, dash="dot"),
        secondary_y=True,
        hovertemplate="%{x|%b %d}<br>Orders: %{y}<extra></extra>",
    )
    fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
    fig.update_yaxes(title_text="Orders", secondary_y=True, showgrid=False)
    return _to_div(_style(fig, height=360))


def chart_channel_revenue(data: ReportData) -> str:
    """Revenue by acquisition channel."""
    c = data.channel.sort_values("revenue")
    fig = go.Figure(
        go.Bar(
            x=c["revenue"], y=c["channel"], orientation="h",
            marker_color=PRIMARY,
            text=[fmt_compact_currency(v) for v in c["revenue"]],
            textposition="auto",
            hovertemplate="%{y}<br>Revenue: $%{x:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Revenue ($)")
    return _to_div(_style(fig))


def chart_category_donut(data: ReportData) -> str:
    """Revenue share by product category."""
    c = data.category
    fig = go.Figure(
        go.Pie(
            labels=c["category"], values=c["revenue"], hole=0.58,
            marker=dict(colors=CHART_COLORS),
            textinfo="label+percent", textposition="outside",
            hovertemplate="%{label}<br>$%{value:,.0f} (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False)
    return _to_div(_style(fig))


def chart_roas(data: ReportData) -> str:
    """ROAS by paid channel, coloured by performance vs. the blended average."""
    paid = data.channel.dropna(subset=["roas"]).sort_values("roas")
    blended = data.kpis["roas"]
    colors = [SUCCESS if v >= blended else DANGER for v in paid["roas"]]

    fig = go.Figure(
        go.Bar(
            x=paid["channel"], y=paid["roas"], marker_color=colors,
            text=[f"{v:.1f}x" for v in paid["roas"]], textposition="auto",
            hovertemplate="%{x}<br>ROAS: %{y:.2f}x<extra></extra>",
        )
    )
    # Reference line for the blended ROAS.
    fig.add_hline(
        y=blended, line_dash="dash", line_color=TEXT_COLOR,
        annotation_text=f"Blended {blended:.1f}x",
        annotation_position="top left",
    )
    fig.update_yaxes(title_text="ROAS (x)")
    return _to_div(_style(fig))


def chart_country(data: ReportData) -> str:
    """Revenue by destination country (horizontal bar)."""
    c = data.country.sort_values("revenue")
    fig = go.Figure(
        go.Bar(
            x=c["revenue"], y=c["country"], orientation="h",
            marker_color=SUCCESS,
            text=[fmt_compact_currency(v) for v in c["revenue"]],
            textposition="auto",
            hovertemplate="%{y}<br>Revenue: $%{x:,.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Revenue ($)")
    return _to_div(_style(fig))


# --------------------------------------------------------------------------- #
# HTML building blocks
# --------------------------------------------------------------------------- #
def _kpi_card(label: str, value: str, change: float | None = None) -> str:
    """Render a single KPI card; ``change`` (a ratio) drives the delta badge."""
    delta_html = ""
    if change is not None:
        up = change >= 0
        arrow = "&#9650;" if up else "&#9660;"  # solid up/down triangles
        cls = "delta-up" if up else "delta-down"
        delta_html = (
            f'<div class="delta {cls}">{arrow} {fmt_pct(abs(change))}'
            f'<span class="delta-note"> vs prior period</span></div>'
        )
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{delta_html}'
        "</div>"
    )


def _kpi_section(data: ReportData) -> str:
    """Build the full KPI card row."""
    k, pop = data.kpis, data.pop
    cards = [
        _kpi_card("Total Revenue", fmt_compact_currency(k["total_revenue"]),
                  pop["total_revenue"]["change"]),
        _kpi_card("Net Profit", fmt_compact_currency(k["net_profit"]),
                  pop["net_profit"]["change"]),
        _kpi_card("Orders", fmt_number(k["orders"]), pop["orders"]["change"]),
        _kpi_card("Avg Order Value", fmt_currency(k["aov"], 2),
                  pop["aov"]["change"]),
        _kpi_card("Blended ROAS", f"{k['roas']:.1f}x", pop["roas"]["change"]),
        _kpi_card("Gross Margin", fmt_pct(k["gross_margin"])),
        _kpi_card("Ad Spend", fmt_compact_currency(k["total_ad_spend"])),
        _kpi_card("New Customers", fmt_pct(k["new_customer_rate"])),
    ]
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def _insights_section(data: ReportData) -> str:
    """Build the dark Key Insights panel."""
    items = "".join(f"<li>{text}</li>" for text in data.insights)
    return (
        '<div class="insights">'
        '<div class="insights-title">Key Insights '
        '<span class="badge">Auto-generated</span></div>'
        f'<ul>{items}</ul>'
        "</div>"
    )


def _chart_card(title: str, div: str, wide: bool = False) -> str:
    """Wrap a chart div in a titled card."""
    span = " chart-card--wide" if wide else ""
    return (
        f'<div class="chart-card{span}">'
        f'<div class="chart-title">{title}</div>'
        f'{div}'
        "</div>"
    )


# --------------------------------------------------------------------------- #
# Page assembly
# --------------------------------------------------------------------------- #
def _page(data: ReportData, charts: dict[str, str]) -> str:
    """Assemble the complete HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>E-Commerce Performance Dashboard</title>
<script>{get_plotlyjs()}</script>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div>
      <h1>E-Commerce Performance Dashboard</h1>
      <p class="period">Reporting period: {data.period_start} &ndash; {data.period_end}
        &nbsp;&middot;&nbsp; {data.period_days} days</p>
    </div>
    <div class="hero-badge">Automated Report</div>
  </header>

  {_kpi_section(data)}

  {_insights_section(data)}

  <div class="chart-grid">
    {_chart_card("Daily Revenue &amp; Orders", charts["daily"], wide=True)}
    {_chart_card("Revenue by Channel", charts["channel"])}
    {_chart_card("Revenue by Category", charts["category"])}
    {_chart_card("Return on Ad Spend (ROAS)", charts["roas"])}
    {_chart_card("Revenue by Country", charts["country"])}
  </div>

  <footer class="foot">
    Generated automatically from raw order &amp; ad-spend data &middot;
    Python &middot; pandas &middot; Plotly
  </footer>
</div>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Stylesheet
# --------------------------------------------------------------------------- #
_CSS = """
:root{
  --primary:#2563eb; --success:#10b981; --danger:#ef4444;
  --ink:#0f172a; --muted:#64748b; --line:#e5e7eb; --bg:#f1f5f9;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:Inter,'Segoe UI',system-ui,sans-serif; line-height:1.5;
}
.wrap{max-width:1240px; margin:0 auto; padding:28px 20px 48px;}
.hero{
  display:flex; align-items:center; justify-content:space-between; gap:16px;
  background:linear-gradient(135deg,#2563eb 0%,#1e40af 100%);
  color:#fff; border-radius:16px; padding:26px 30px; margin-bottom:22px;
  box-shadow:0 10px 30px rgba(37,99,235,.25);
}
.hero h1{margin:0; font-size:24px; font-weight:700; letter-spacing:-.02em;}
.period{margin:6px 0 0; color:#dbeafe; font-size:14px;}
.hero-badge{
  background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
  padding:8px 14px; border-radius:999px; font-size:13px; font-weight:600;
  white-space:nowrap;
}
.kpi-grid{
  display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:22px;
}
.kpi-card{
  background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:18px 20px; box-shadow:0 1px 2px rgba(15,23,42,.04);
}
.kpi-label{color:var(--muted); font-size:13px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em;}
.kpi-value{font-size:28px; font-weight:700; margin-top:6px; letter-spacing:-.02em;}
.delta{font-size:13px; font-weight:600; margin-top:6px;}
.delta-note{color:var(--muted); font-weight:500;}
.delta-up{color:var(--success);}
.delta-down{color:var(--danger);}
.insights{
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);
  color:#e2e8f0; border-radius:16px; padding:24px 28px; margin-bottom:24px;
  box-shadow:0 10px 30px rgba(15,23,42,.18);
}
.insights-title{font-size:17px; font-weight:700; color:#fff; margin-bottom:12px;}
.badge{
  background:var(--success); color:#06281d; font-size:11px; font-weight:700;
  padding:3px 9px; border-radius:999px; margin-left:8px; vertical-align:middle;
  text-transform:uppercase; letter-spacing:.04em;
}
.insights ul{margin:0; padding-left:20px;}
.insights li{margin:9px 0; font-size:14.5px; color:#cbd5e1;}
.chart-grid{
  display:grid; grid-template-columns:repeat(2,1fr); gap:18px;
}
.chart-card{
  background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:18px 20px; box-shadow:0 1px 2px rgba(15,23,42,.04);
}
.chart-card--wide{grid-column:1 / -1;}
.chart-title{font-size:15px; font-weight:700; margin-bottom:8px; color:var(--ink);}
.foot{text-align:center; color:var(--muted); font-size:13px; margin-top:30px;}
@media (max-width:980px){
  .kpi-grid{grid-template-columns:repeat(2,1fr);}
  .chart-grid{grid-template-columns:1fr;}
  .chart-card--wide{grid-column:auto;}
}
@media (max-width:560px){
  .kpi-grid{grid-template-columns:1fr;}
  .hero{flex-direction:column; align-items:flex-start;}
}
"""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build(data: ReportData, output_path: str | Path = "output/dashboard.html") -> Path:
    """Build the dashboard and write it to ``output_path``."""
    charts = {
        "daily": chart_daily(data),
        "channel": chart_channel_revenue(data),
        "category": chart_category_donut(data),
        "roas": chart_roas(data),
        "country": chart_country(data),
    }
    html = _page(data, charts)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"  - dashboard.html : {size_kb:,.0f} KB (self-contained, offline-ready)")
    return output_path


if __name__ == "__main__":
    from analytics import run_analytics

    build(run_analytics())
