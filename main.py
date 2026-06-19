"""
main.py
=======
Pipeline orchestrator.

Runs the four stages end to end and logs each step to the console:

    1. generate_data   -> data/orders.csv, data/ad_spend.csv
    2. analytics       -> KPIs, breakdowns and auto-insights (in memory)
    3. build_dashboard -> output/dashboard.html (interactive)
    4. build_pdf       -> output/report.pdf (print-ready)

Usage:
    python main.py
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import analytics
import build_dashboard
import build_pdf
import generate_data

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")


def _log(message: str) -> None:
    """Print a timestamped log line."""
    print(f"[{datetime.now():%H:%M:%S}] {message}")


def _step(number: int, title: str) -> None:
    _log(f"Step {number}/4  {title}")


def run() -> None:
    """Execute the full reporting pipeline."""
    started = time.perf_counter()
    print("=" * 64)
    print("  E-COMMERCE AUTOMATED REPORTING PIPELINE")
    print("=" * 64)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Generate synthetic source data ------------------------------------ #
    _step(1, "Generating synthetic e-commerce data")
    generate_data.generate(DATA_DIR)

    # 2) Run analytics ------------------------------------------------------ #
    _step(2, "Computing KPIs and generating insights")
    report = analytics.run_analytics(DATA_DIR)

    # 3) Build the interactive dashboard ------------------------------------ #
    _step(3, "Building interactive HTML dashboard")
    dashboard_path = build_dashboard.build(report, OUTPUT_DIR / "dashboard.html")

    # 4) Build the PDF report ---------------------------------------------- #
    _step(4, "Building professional PDF report")
    pdf_path = build_pdf.build(report, OUTPUT_DIR / "report.pdf")

    elapsed = time.perf_counter() - started
    print("-" * 64)
    _log(f"Done in {elapsed:.2f}s. Open your reports:")
    print(f"        Dashboard : {dashboard_path.resolve()}")
    print(f"        PDF report: {pdf_path.resolve()}")
    print("=" * 64)


if __name__ == "__main__":
    run()
