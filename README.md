# E-Commerce Automated Reporting Pipeline

Turn raw e-commerce data into a polished, client-ready report — automatically.

This project takes raw order and ad-spend data and, in a single command,
produces **two deliverables**:

1. An **interactive HTML dashboard** (self-contained, opens in any browser — no
   server, no internet connection required).
2. A **professional multi-page PDF report** (print-ready, corporate styling).

It is built as a demonstration of a productized service: *"give me your data,
get back an automated report."* The analytics layer doesn't just crunch
numbers — it **writes the insights for you** in plain English, highlighting
which channels to scale, which to cut, and where the growth is coming from.

---

## ✨ What it produces

| Deliverable | File | Highlights |
|-------------|------|-----------|
| Interactive dashboard | `output/dashboard.html` | KPI cards with up/down deltas, dark "Key Insights" panel, 5 interactive Plotly charts, fully responsive |
| PDF report | `output/report.pdf` | Cover band, executive KPI table, auto-insights, channel & category tables, embedded charts, page numbers |

### Key Insights engine

The standout feature is the **automatic insight generator**. Instead of leaving
the reader to interpret the charts, the pipeline inspects the metrics and writes
recommendations such as:

> - *Google Ads is the most efficient paid channel at 4.8x ROAS — the strongest
>   candidate to scale budget into.*
> - *Meta Ads is underperforming at 2.6x ROAS, below the blended average — a
>   candidate for budget reallocation toward higher-return channels.*
> - *Beauty is the most profitable category at 62% gross margin — promoting it
>   more aggressively could lift blended profitability.*

These sentences are generated dynamically from thresholds and comparisons, so
the wording adapts to whatever the data actually shows.

---

## 🚀 Quick start

```bash
# 1. (optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run the full pipeline
python main.py
```

Then open `output/dashboard.html` in your browser and `output/report.pdf` in any
PDF viewer.

### Console output

```
================================================================
  E-COMMERCE AUTOMATED REPORTING PIPELINE
================================================================
[12:00:01] Step 1/4  Generating synthetic e-commerce data
  - orders.csv     : 3,900 orders (...)
  - ad_spend.csv   : 270 daily channel rows
[12:00:01] Step 2/4  Computing KPIs and generating insights
  - KPIs computed  : $0.7M revenue, 3,900 orders, 4.0x ROAS
  - Insights       : 9 auto-generated statements
[12:00:02] Step 3/4  Building interactive HTML dashboard
  - dashboard.html : ~4,700 KB (self-contained, offline-ready)
[12:00:03] Step 4/4  Building professional PDF report
  - report.pdf     : ~250 KB (4 pages)
================================================================
```

---

## 🧱 Architecture

The pipeline is split into focused, independently runnable modules:

```
ecommerce-report/
├── generate_data.py   # Realistic synthetic data generator (numpy, seed=42)
├── analytics.py       # KPI engine + auto-insight generator  ← the "brain"
├── build_dashboard.py # Interactive HTML dashboard (Plotly)
├── build_pdf.py       # Professional PDF report (ReportLab + Matplotlib)
├── main.py            # Orchestrates all stages, logs each step
├── requirements.txt
├── README.md
├── data/              # Generated CSVs (orders.csv, ad_spend.csv)
└── output/            # Generated dashboard.html and report.pdf
```

Data flows in one direction:

```
generate_data ──▶ data/*.csv ──▶ analytics.run_analytics() ──▶ ReportData
                                                                  │
                                          ┌───────────────────────┴───────────┐
                                          ▼                                   ▼
                                 build_dashboard.build()             build_pdf.build()
                                          │                                   │
                                          ▼                                   ▼
                                 output/dashboard.html                output/report.pdf
```

`analytics.py` computes everything once and returns a single `ReportData`
object, so both builders render from an identical, consistent source of truth.

Every module also runs standalone for quick iteration, e.g.:

```bash
python generate_data.py     # just regenerate the CSVs
python build_dashboard.py   # rebuild only the dashboard
```

---

## 📊 What gets measured

**Headline KPIs:** total revenue, gross profit, net profit (after ad spend),
total ad spend, orders, average order value (AOV), new-customer rate, blended
ROAS, and gross margin.

**Analyses:**

- **Period-over-period** — the second half of the window vs. the first half,
  with % change on every key metric.
- **Channel performance** — revenue, orders, AOV and ROAS per channel
  (Google Ads, Meta Ads, Organic Search, Email, Direct).
- **Category breakdown** — revenue, gross profit and margin per category.
- **Geographic split** — revenue by country.
- **Daily trend** — revenue, orders and a 7-day moving average.

---

## 🗂️ The synthetic data

`generate_data.py` produces a realistic 90-day dataset so the demo is
self-contained. The data is engineered to *look real*:

- a weekly purchasing cycle (mid-week peaks, weekend dips),
- a mild upward growth trend,
- random day-to-day noise,
- channels with deliberately different return profiles so the insight engine has
  meaningful findings to report.

Everything is seeded (`numpy`, seed `42`) for fully reproducible output.

**Swapping in real data:** replace the two CSVs in `data/` with your own
`orders.csv` and `ad_spend.csv` (matching the column schema below) and run
`python analytics.py`-driven steps — no other code changes are required.

| `orders.csv` | `ad_spend.csv` |
|--------------|----------------|
| `order_id, date, channel, category, country, device, items, revenue, cogs, new_customer` | `date, channel, spend` |

---

## 🛠️ Tech stack

| Concern | Library |
|---------|---------|
| Data generation & wrangling | **NumPy**, **pandas** |
| Interactive dashboard | **Plotly** (embedded inline — no CDN dependency) |
| Static charts for print | **Matplotlib** |
| PDF generation | **ReportLab** |

Pure Python, no database and no external services. The HTML dashboard is fully
self-contained: the Plotly library is embedded directly in the file, so it works
offline and can be emailed as a single attachment.

---

## 💡 Why this matters (for clients)

Most businesses sit on order data they never turn into decisions. This pipeline
shows how that gap is closed automatically: raw export in, branded report out,
with the analysis written for you. It is straightforward to adapt to a real
store's export, schedule on a weekly cadence, or extend with new KPIs and chart
types.

---

## 📄 License

Provided as a portfolio / demonstration project. Feel free to adapt it for your
own use.
