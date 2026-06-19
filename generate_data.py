"""
generate_data.py
=================
Generates realistic synthetic e-commerce data for the reporting pipeline.

Two CSV files are produced inside the ``data/`` directory:

* ``orders.csv``    -- one row per order with revenue, cost and attribution fields.
* ``ad_spend.csv``  -- daily marketing spend per paid channel.

The data is intentionally crafted to look like a real store:

* a weekly purchasing cycle (mid-week peaks, weekend dips),
* a mild upward growth trend over the 90-day window,
* random day-to-day noise,
* channels with *different* return profiles so the analytics layer has
  something interesting to say (e.g. Meta Ads underperforms on ROAS while
  Email is highly efficient).

Everything is driven by a fixed NumPy seed (42) so the generated numbers are
fully reproducible from one run to the next.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SEED = 42
PERIOD_DAYS = 90

CHANNELS = ["Google Ads", "Meta Ads", "Organic Search", "Email", "Direct"]
# Probability that any given order is attributed to a channel.
CHANNEL_WEIGHTS = np.array([0.26, 0.22, 0.20, 0.14, 0.18])

# Channels that incur marketing spend, plus their *target* blended ROAS.
# These targets shape ad_spend so the resulting ROAS values are realistic and
# differentiated (Email very efficient, Meta Ads the weak performer).
PAID_CHANNELS = {
    "Google Ads": 4.8,
    "Meta Ads": 2.6,
    "Email": 8.0,
}

# Probability that an order from a channel comes from a *new* customer.
# Paid acquisition channels skew toward new customers; Email/Direct retain.
CHANNEL_NEW_CUSTOMER_RATE = {
    "Google Ads": 0.48,
    "Meta Ads": 0.45,
    "Organic Search": 0.40,
    "Email": 0.18,
    "Direct": 0.25,
}

CATEGORIES = ["Apparel", "Electronics", "Home & Living", "Beauty", "Accessories"]
CATEGORY_WEIGHTS = np.array([0.30, 0.16, 0.20, 0.18, 0.16])

# Average unit price and gross margin per category.
CATEGORY_PROFILE = {
    "Apparel":       {"price": 55.0,  "margin": 0.55},
    "Electronics":   {"price": 240.0, "margin": 0.30},
    "Home & Living": {"price": 90.0,  "margin": 0.45},
    "Beauty":        {"price": 38.0,  "margin": 0.62},
    "Accessories":   {"price": 32.0,  "margin": 0.58},
}

COUNTRIES = ["US", "UK", "Germany", "Canada", "Australia", "Turkey"]
COUNTRY_WEIGHTS = np.array([0.40, 0.15, 0.12, 0.10, 0.08, 0.15])

DEVICES = ["Mobile", "Desktop", "Tablet"]
DEVICE_WEIGHTS = np.array([0.58, 0.34, 0.08])

# Weekly seasonality multipliers (Mon=0 ... Sun=6).
WEEKDAY_FACTOR = np.array([1.05, 1.12, 1.10, 1.02, 0.95, 0.85, 0.91])

BASE_ORDERS_PER_DAY = 38      # baseline order volume at day 0
DAILY_TREND = 0.0045          # ~+45% compounded growth across the window


# --------------------------------------------------------------------------- #
# Data generation
# --------------------------------------------------------------------------- #
def _build_dates(end_date: date, days: int) -> list[date]:
    """Return an ascending list of ``days`` dates ending on ``end_date``."""
    start = end_date - timedelta(days=days - 1)
    return [start + timedelta(days=i) for i in range(days)]


def _orders_for_day(rng: np.random.Generator, day_index: int, day: date) -> int:
    """Draw a realistic order count for a single day."""
    seasonal = WEEKDAY_FACTOR[day.weekday()]
    trend = (1.0 + DAILY_TREND) ** day_index
    expected = BASE_ORDERS_PER_DAY * seasonal * trend
    # Poisson noise keeps counts integer and naturally over-dispersed.
    return int(rng.poisson(expected))


def generate_orders(rng: np.random.Generator, dates: list[date]) -> pd.DataFrame:
    """Generate the order-level dataset across the full period."""
    records: list[dict] = []
    order_counter = 1

    for day_index, day in enumerate(dates):
        n_orders = _orders_for_day(rng, day_index, day)

        # Vectorised attribute draws for the whole day.
        channels = rng.choice(CHANNELS, size=n_orders, p=CHANNEL_WEIGHTS)
        categories = rng.choice(CATEGORIES, size=n_orders, p=CATEGORY_WEIGHTS)
        countries = rng.choice(COUNTRIES, size=n_orders, p=COUNTRY_WEIGHTS)
        devices = rng.choice(DEVICES, size=n_orders, p=DEVICE_WEIGHTS)
        # Basket size skewed toward 1-2 items.
        items = rng.choice([1, 2, 3, 4, 5], size=n_orders,
                           p=[0.46, 0.28, 0.14, 0.08, 0.04])

        for i in range(n_orders):
            category = categories[i]
            profile = CATEGORY_PROFILE[category]

            # Unit price varies around the category average; revenue scales
            # with basket size.
            unit_price = profile["price"] * rng.lognormal(mean=0.0, sigma=0.18)
            revenue = round(unit_price * items[i], 2)

            # COGS derived from the category margin with a little variation.
            effective_margin = np.clip(
                profile["margin"] + rng.normal(0, 0.03), 0.10, 0.85
            )
            cogs = round(revenue * (1.0 - effective_margin), 2)

            channel = channels[i]
            new_customer = int(
                rng.random() < CHANNEL_NEW_CUSTOMER_RATE[channel]
            )

            records.append(
                {
                    "order_id": f"ORD-{order_counter:06d}",
                    "date": day.isoformat(),
                    "channel": channel,
                    "category": category,
                    "country": countries[i],
                    "device": devices[i],
                    "items": int(items[i]),
                    "revenue": revenue,
                    "cogs": cogs,
                    "new_customer": new_customer,
                }
            )
            order_counter += 1

    return pd.DataFrame.from_records(records)


def generate_ad_spend(rng: np.random.Generator, orders: pd.DataFrame) -> pd.DataFrame:
    """
    Derive daily ad spend per paid channel from the realised revenue.

    Spend is back-solved from each channel's target ROAS plus noise, which
    keeps the resulting ROAS values realistic and differentiated.
    """
    paid_orders = orders[orders["channel"].isin(PAID_CHANNELS)]
    daily_rev = (
        paid_orders.groupby(["date", "channel"])["revenue"].sum().reset_index()
    )

    records: list[dict] = []
    for _, row in daily_rev.iterrows():
        target_roas = PAID_CHANNELS[row["channel"]]
        noise = rng.lognormal(mean=0.0, sigma=0.12)
        spend = round((row["revenue"] / target_roas) * noise, 2)
        records.append(
            {"date": row["date"], "channel": row["channel"], "spend": spend}
        )

    spend_df = pd.DataFrame.from_records(records)
    return spend_df.sort_values(["date", "channel"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def generate(data_dir: str | Path = "data",
             end_date: date | None = None,
             days: int = PERIOD_DAYS) -> dict[str, Path]:
    """
    Generate ``orders.csv`` and ``ad_spend.csv`` and write them to ``data_dir``.

    Returns a mapping of logical name -> written file path.
    """
    rng = np.random.default_rng(SEED)
    end_date = end_date or date.today()
    dates = _build_dates(end_date, days)

    orders = generate_orders(rng, dates)
    ad_spend = generate_ad_spend(rng, orders)

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    orders_path = data_dir / "orders.csv"
    spend_path = data_dir / "ad_spend.csv"
    orders.to_csv(orders_path, index=False)
    ad_spend.to_csv(spend_path, index=False)

    print(
        f"  - orders.csv     : {len(orders):,} orders "
        f"({dates[0].isoformat()} -> {dates[-1].isoformat()})"
    )
    print(f"  - ad_spend.csv   : {len(ad_spend):,} daily channel rows")

    return {"orders": orders_path, "ad_spend": spend_path}


if __name__ == "__main__":
    generate()
