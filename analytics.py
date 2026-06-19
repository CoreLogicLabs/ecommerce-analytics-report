"""
analytics.py
============
The analytical core of the pipeline -- it turns raw CSV data into business
KPIs, breakdowns and, most importantly, *plain-English insights*.

The public entry point is :func:`run_analytics`, which returns a fully
populated :class:`ReportData` object consumed by both the HTML dashboard and
the PDF report builders.

The auto-insight engine (:func:`generate_insights`) is what makes the report
feel "smart": instead of only showing numbers, it inspects the metrics and
writes recommendations such as which channel to scale and which one is a
candidate for budget reallocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Brand palette (shared with the builders for a consistent look)
# --------------------------------------------------------------------------- #
PRIMARY = "#2563eb"   # blue
SUCCESS = "#10b981"   # green
DANGER = "#ef4444"    # red
WARNING = "#f59e0b"   # amber

PAID_CHANNELS = ["Google Ads", "Meta Ads", "Email"]


# --------------------------------------------------------------------------- #
# Formatting helpers (re-used by the dashboard and PDF builders)
# --------------------------------------------------------------------------- #
def fmt_currency(value: float, decimals: int = 0) -> str:
    """Format a number as USD, e.g. ``$1,234`` or ``$1,234.50``."""
    return f"${value:,.{decimals}f}"


def fmt_compact_currency(value: float) -> str:
    """Format large amounts compactly, e.g. ``$1.2M`` / ``$45.3K``."""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def fmt_pct(value: float, decimals: int = 1, signed: bool = False) -> str:
    """Format a ratio (0.123) as a percentage string (``12.3%``)."""
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value * 100:.{decimals}f}%"


def fmt_number(value: float) -> str:
    """Format an integer-like number with thousands separators."""
    return f"{value:,.0f}"


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class ReportData:
    """Everything the report builders need, computed once."""

    period_start: str
    period_end: str
    period_days: int

    kpis: dict = field(default_factory=dict)
    # metric -> {"first": float, "second": float, "change": float}
    pop: dict = field(default_factory=dict)

    channel: pd.DataFrame = field(default_factory=pd.DataFrame)
    category: pd.DataFrame = field(default_factory=pd.DataFrame)
    country: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily: pd.DataFrame = field(default_factory=pd.DataFrame)

    insights: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_data(data_dir: str | Path = "data") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and lightly clean the two source CSV files."""
    data_dir = Path(data_dir)
    orders = pd.read_csv(data_dir / "orders.csv", parse_dates=["date"])
    ad_spend = pd.read_csv(data_dir / "ad_spend.csv", parse_dates=["date"])

    # Derived per-order economics, computed once and reused everywhere.
    orders["gross_profit"] = orders["revenue"] - orders["cogs"]
    return orders, ad_spend


# --------------------------------------------------------------------------- #
# KPI computation
# --------------------------------------------------------------------------- #
def compute_kpis(orders: pd.DataFrame, ad_spend: pd.DataFrame) -> dict:
    """Compute the headline KPIs for the whole period."""
    total_revenue = orders["revenue"].sum()
    total_cogs = orders["cogs"].sum()
    gross_profit = total_revenue - total_cogs
    total_ad_spend = ad_spend["spend"].sum()
    net_profit = gross_profit - total_ad_spend
    n_orders = len(orders)

    return {
        "total_revenue": total_revenue,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "total_ad_spend": total_ad_spend,
        "orders": n_orders,
        "aov": total_revenue / n_orders if n_orders else 0.0,
        "new_customer_rate": orders["new_customer"].mean() if n_orders else 0.0,
        # Blended ROAS: every revenue dollar against every ad dollar.
        "roas": total_revenue / total_ad_spend if total_ad_spend else 0.0,
        "gross_margin": gross_profit / total_revenue if total_revenue else 0.0,
    }


def compute_period_over_period(orders: pd.DataFrame,
                               ad_spend: pd.DataFrame) -> dict:
    """
    Compare the second half of the period against the first half.

    The window is split by its calendar midpoint; each metric reports the two
    half-totals and the percentage change between them.
    """
    midpoint = orders["date"].min() + (
        orders["date"].max() - orders["date"].min()
    ) / 2

    def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        return df[df["date"] <= midpoint], df[df["date"] > midpoint]

    o_first, o_second = split(orders)
    s_first, s_second = split(ad_spend)

    def metrics(o: pd.DataFrame, s: pd.DataFrame) -> dict:
        rev = o["revenue"].sum()
        spend = s["spend"].sum()
        n = len(o)
        return {
            "total_revenue": rev,
            "orders": n,
            "aov": rev / n if n else 0.0,
            "gross_profit": o["gross_profit"].sum(),
            "net_profit": o["gross_profit"].sum() - spend,
            "roas": rev / spend if spend else 0.0,
        }

    first, second = metrics(o_first, s_first), metrics(o_second, s_second)

    pop: dict = {}
    for metric, first_val in first.items():
        second_val = second[metric]
        change = (second_val - first_val) / first_val if first_val else 0.0
        pop[metric] = {"first": first_val, "second": second_val, "change": change}
    return pop


# --------------------------------------------------------------------------- #
# Breakdowns
# --------------------------------------------------------------------------- #
def channel_performance(orders: pd.DataFrame,
                        ad_spend: pd.DataFrame) -> pd.DataFrame:
    """Revenue, orders, AOV, spend and ROAS per acquisition channel."""
    grp = orders.groupby("channel").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "count"),
        gross_profit=("gross_profit", "sum"),
    )
    spend = ad_spend.groupby("channel")["spend"].sum()
    grp["spend"] = spend.reindex(grp.index).fillna(0.0)

    grp["aov"] = grp["revenue"] / grp["orders"]
    # ROAS only defined where there is spend (paid channels).
    grp["roas"] = grp.apply(
        lambda r: r["revenue"] / r["spend"] if r["spend"] > 0 else float("nan"),
        axis=1,
    )
    grp["revenue_share"] = grp["revenue"] / grp["revenue"].sum()
    return grp.sort_values("revenue", ascending=False).reset_index()


def category_performance(orders: pd.DataFrame) -> pd.DataFrame:
    """Revenue, gross profit and margin per product category."""
    grp = orders.groupby("category").agg(
        revenue=("revenue", "sum"),
        gross_profit=("gross_profit", "sum"),
        orders=("order_id", "count"),
    )
    grp["margin"] = grp["gross_profit"] / grp["revenue"]
    grp["revenue_share"] = grp["revenue"] / grp["revenue"].sum()
    return grp.sort_values("revenue", ascending=False).reset_index()


def country_performance(orders: pd.DataFrame) -> pd.DataFrame:
    """Revenue and orders per destination country."""
    grp = orders.groupby("country").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "count"),
    )
    grp["revenue_share"] = grp["revenue"] / grp["revenue"].sum()
    return grp.sort_values("revenue", ascending=False).reset_index()


def daily_trend(orders: pd.DataFrame, ad_spend: pd.DataFrame) -> pd.DataFrame:
    """Per-day revenue, orders, gross profit and ad spend."""
    daily = orders.groupby("date").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "count"),
        gross_profit=("gross_profit", "sum"),
    )
    spend = ad_spend.groupby("date")["spend"].sum()
    daily["spend"] = spend.reindex(daily.index).fillna(0.0)
    daily = daily.reset_index()
    # 7-day moving average smooths the weekly cycle for trend visualisation.
    daily["revenue_ma7"] = daily["revenue"].rolling(7, min_periods=1).mean()
    return daily


# --------------------------------------------------------------------------- #
# The insight engine
# --------------------------------------------------------------------------- #
def generate_insights(kpis: dict,
                      pop: dict,
                      channel: pd.DataFrame,
                      category: pd.DataFrame,
                      country: pd.DataFrame) -> list[str]:
    """
    Translate the numbers into a ranked list of plain-English insights.

    Each statement is generated from thresholds and comparisons so the wording
    adapts to whatever the data actually shows.
    """
    insights: list[str] = []

    # 1) Overall revenue trajectory (period over period).
    rev_change = pop["total_revenue"]["change"]
    if rev_change >= 0.02:
        insights.append(
            f"Revenue is trending up: the second half of the period grew "
            f"{fmt_pct(rev_change, signed=True)} versus the first half, "
            f"reaching {fmt_compact_currency(pop['total_revenue']['second'])}."
        )
    elif rev_change <= -0.02:
        insights.append(
            f"Revenue softened by {fmt_pct(rev_change, signed=True)} in the "
            f"second half of the period -- worth investigating demand or "
            f"seasonality drivers."
        )
    else:
        insights.append(
            "Revenue stayed essentially flat across the two halves of the "
            "period, indicating stable but stagnant demand."
        )

    # 2) Profitability headline.
    insights.append(
        f"The store generated {fmt_compact_currency(kpis['net_profit'])} in net "
        f"profit after {fmt_compact_currency(kpis['total_ad_spend'])} of ad "
        f"spend, at a {fmt_pct(kpis['gross_margin'])} gross margin and a "
        f"blended ROAS of {kpis['roas']:.1f}x."
    )

    # 3) Best and worst paid channel by ROAS -> the budget recommendation.
    #    Benchmarked against the spend-weighted average across *paid* channels
    #    (not the blended ROAS, which is inflated by free organic/direct sales).
    paid = channel.dropna(subset=["roas"]).sort_values("roas", ascending=False)
    if len(paid) >= 2:
        paid_benchmark = paid["revenue"].sum() / paid["spend"].sum()
        best, worst = paid.iloc[0], paid.iloc[-1]
        insights.append(
            f"{best['channel']} is the most efficient paid channel at "
            f"{best['roas']:.1f}x ROAS -- the strongest candidate to scale "
            f"budget into."
        )
        if worst["roas"] < paid_benchmark:
            insights.append(
                f"{worst['channel']} is underperforming at {worst['roas']:.1f}x "
                f"ROAS, below the {paid_benchmark:.1f}x paid-channel average -- a "
                f"candidate for budget reallocation toward higher-return "
                f"channels."
            )

    # 4) Top revenue channel and its share.
    top_channel = channel.iloc[0]
    insights.append(
        f"{top_channel['channel']} is the largest revenue driver, contributing "
        f"{fmt_pct(top_channel['revenue_share'])} of total sales "
        f"({fmt_compact_currency(top_channel['revenue'])})."
    )

    # 5) Category economics: biggest seller vs. highest margin.
    top_cat = category.iloc[0]
    best_margin_cat = category.sort_values("margin", ascending=False).iloc[0]
    insights.append(
        f"{top_cat['category']} leads category revenue with "
        f"{fmt_compact_currency(top_cat['revenue'])} "
        f"({fmt_pct(top_cat['revenue_share'])} of sales)."
    )
    if best_margin_cat["category"] != top_cat["category"]:
        insights.append(
            f"{best_margin_cat['category']} is the most profitable category at "
            f"{fmt_pct(best_margin_cat['margin'])} gross margin -- promoting it "
            f"more aggressively could lift blended profitability."
        )

    # 6) Geographic concentration.
    top_country = country.iloc[0]
    insights.append(
        f"{top_country['country']} is the top market at "
        f"{fmt_pct(top_country['revenue_share'])} of revenue; the remaining "
        f"{len(country) - 1} markets offer room for geographic diversification."
    )

    # 7) New vs. returning customer mix.
    ncr = kpis["new_customer_rate"]
    if ncr >= 0.45:
        insights.append(
            f"New customers make up {fmt_pct(ncr)} of orders -- acquisition is "
            f"strong, but retention programs could improve lifetime value."
        )
    elif ncr <= 0.30:
        insights.append(
            f"Only {fmt_pct(ncr)} of orders come from new customers, pointing to "
            f"a loyal repeat base but limited top-of-funnel growth."
        )
    else:
        insights.append(
            f"The customer mix is balanced at {fmt_pct(ncr)} new customers, a "
            f"healthy blend of acquisition and retention."
        )

    # 8) AOV movement over the period.
    aov_change = pop["aov"]["change"]
    if abs(aov_change) >= 0.03:
        direction = "increased" if aov_change > 0 else "declined"
        insights.append(
            f"Average order value {direction} {fmt_pct(abs(aov_change))} over the "
            f"period to {fmt_currency(pop['aov']['second'], 2)}, "
            f"{'supporting' if aov_change > 0 else 'pressuring'} margin."
        )

    return insights


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_analytics(data_dir: str | Path = "data") -> ReportData:
    """Load the data, compute everything and return a :class:`ReportData`."""
    orders, ad_spend = load_data(data_dir)

    kpis = compute_kpis(orders, ad_spend)
    pop = compute_period_over_period(orders, ad_spend)
    channel = channel_performance(orders, ad_spend)
    category = category_performance(orders)
    country = country_performance(orders)
    daily = daily_trend(orders, ad_spend)
    insights = generate_insights(kpis, pop, channel, category, country)

    report = ReportData(
        period_start=orders["date"].min().strftime("%b %d, %Y"),
        period_end=orders["date"].max().strftime("%b %d, %Y"),
        period_days=orders["date"].dt.normalize().nunique(),
        kpis=kpis,
        pop=pop,
        channel=channel,
        category=category,
        country=country,
        daily=daily,
        insights=insights,
    )

    print(f"  - KPIs computed  : {fmt_compact_currency(kpis['total_revenue'])} "
          f"revenue, {kpis['orders']:,} orders, {kpis['roas']:.1f}x ROAS")
    print(f"  - Insights       : {len(insights)} auto-generated statements")
    return report


if __name__ == "__main__":
    run_analytics()
