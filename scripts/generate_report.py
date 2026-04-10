#!/usr/bin/env python3
"""Stage 6 – Professional HTML Report Generation with Embedded Visualisations.

Reads the data quality JSON and optimization results JSON produced by earlier
pipeline stages, generates matplotlib charts encoded as base64, and compiles
everything into a self-contained HTML report.
"""

import json
import argparse
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless backend – no display needed
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from datetime import datetime
import sys


def generate_scatter_chart(results_data):
    """
    Generates a scatter plot of Average Daily Demand vs Recommended Safety Stock,
    coloured by product category. Returns a base64-encoded PNG string.
    """
    skus, demand, safety_stock, categories = [], [], [], []

    for item in results_data["sku_results"]:
        skus.append(item["sku_id"])
        demand.append(item["avg_daily_demand"])
        safety_stock.append(item["recommended_safety_stock"])
        categories.append(item["category"])

    df = pd.DataFrame({
        "SKU": skus, "Demand": demand,
        "SafetyStock": safety_stock, "Category": categories
    })

    plt.figure(figsize=(10, 6))
    unique_cats = df["Category"].unique()
    colors = plt.cm.get_cmap("tab10", len(unique_cats))

    for i, cat in enumerate(unique_cats):
        subset = df[df["Category"] == cat]
        plt.scatter(subset["Demand"], subset["SafetyStock"],
                    label=cat, color=colors(i), s=100, alpha=0.7, edgecolors="k")

    plt.title("Inventory Policy: Avg Daily Demand vs. Recommended Safety Stock", fontsize=14)
    plt.xlabel("Average Daily Demand (units)", fontsize=12)
    plt.ylabel("Recommended Safety Stock (units)", fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(title="Category", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_wmape_bar_chart(results_data):
    """
    Generates a grouped bar chart comparing GBR vs Fourier Seasonal WMAPE per SKU.
    Returns a base64-encoded PNG string.
    """
    skus = [item["sku_id"].replace("SKU_", "") for item in results_data["sku_results"]]
    xgb = [item["gbr_wmape"] for item in results_data["sku_results"]]
    prophet = [item["fourier_wmape"] for item in results_data["sku_results"]]

    x = range(len(skus))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar([i - width/2 for i in x], xgb, width, label="Gradient Boosted Trees", color="#e74c3c", alpha=0.8)
    ax.bar([i + width/2 for i in x], prophet, width, label="Fourier Seasonal", color="#3498db", alpha=0.8)

    ax.set_ylabel("WMAPE", fontsize=12)
    ax.set_xlabel("SKU", fontsize=12)
    ax.set_title("Model Comparison: GBR vs Fourier Seasonal WMAPE by SKU", fontsize=14)
    ax.set_xticks(list(x))
    ax.set_xticklabels(skus, rotation=45, ha="right", fontsize=8)
    ax.axhline(y=0.30, color="red", linestyle="--", alpha=0.5, label="Poor Threshold (0.30)")
    ax.axhline(y=0.15, color="green", linestyle="--", alpha=0.5, label="Excellent Threshold (0.15)")
    ax.legend()
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def classify_archetype(item):
    """Classify a SKU into an archetype based on REFERENCE.md criteria."""
    cv = item["cv_demand"]
    wmape = item["winning_wmape"]
    winner = item["winning_algorithm"]

    if cv < 0.20 and wmape < 0.15:
        return "Stable Baseload"
    elif winner == "Fourier Seasonal":
        return "Highly Seasonal"
    else:
        return "Erratic / Volatile" if wmape > 0.30 else "Moderate Demand"


def generate_html_report(quality_data, optimization_data, output_path):
    """
    Compiles data quality summary, model metrics, visualisations, and business
    interpretations into a self-contained HTML report.
    """
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = optimization_data.get("config", {})
    holdout = config.get("holdout_days", 30)
    z_val = config.get("service_level_z", 1.65)

    # Aggregate metrics
    sku_results = optimization_data["sku_results"]
    total_skus = len(sku_results)
    avg_wmape = sum(r["winning_wmape"] for r in sku_results) / total_skus
    xgb_wins = sum(1 for r in sku_results if r["winning_algorithm"] == "Gradient Boosted Trees")
    prophet_wins = total_skus - xgb_wins

    # Charts
    scatter_b64 = generate_scatter_chart(optimization_data)
    bar_b64 = generate_wmape_bar_chart(optimization_data)

    # SKU detail rows
    sku_rows = ""
    for item in sku_results:
        archetype = classify_archetype(item)
        wmape_color = "#27ae60" if item["winning_wmape"] < 0.15 else (
            "#f39c12" if item["winning_wmape"] < 0.30 else "#e74c3c")
        sku_rows += f"""
        <tr>
            <td>{item['sku_id']}</td>
            <td>{item['category']}</td>
            <td>{archetype}</td>
            <td style="color:{wmape_color};font-weight:bold;">
                {item['winning_algorithm']} ({item['winning_wmape']:.4f})</td>
            <td>{item['avg_daily_demand']:.1f}</td>
            <td><strong>{int(item['recommended_safety_stock'])}</strong></td>
            <td><strong>{int(item['reorder_point'])}</strong></td>
        </tr>"""

    # Recommendations per archetype
    reco_items = ""
    for item in sku_results:
        archetype = classify_archetype(item)
        sku = item["sku_id"]
        lt = item["avg_lead_time_days"]
        if archetype == "Stable Baseload":
            reco_items += f'<li><strong>{sku} (Stable Baseload):</strong> Demand velocity is highly stable. Recommend automated, large-batch replenishment cycles. Safety stock can be minimized to free working capital.</li>\n'
        elif archetype == "Highly Seasonal":
            reco_items += f'<li><strong>{sku} (Highly Seasonal):</strong> Strong seasonal adherence detected. Ensure procurement and warehouse capacity aligned at least {lt:.0f} days ahead of forecasted peak. Taper orders post-peak.</li>\n'
        elif archetype == "Erratic / Volatile":
            reco_items += f'<li><strong>{sku} (Erratic / Volatile):</strong> High volatility and elevated WMAPE. Evaluate for rationalization, make-to-order shift, or accept lower service level (90%) to balance holding costs.</li>\n'
        else:
            reco_items += f'<li><strong>{sku} (Moderate Demand):</strong> Standard replenishment recommended. Review quarterly for trend shifts.</li>\n'

    # Quality summary
    q_status = quality_data.get("status", "Unknown")
    q_rows = quality_data.get("row_count", "N/A")
    q_cols = quality_data.get("column_count", "N/A")
    q_warnings = quality_data.get("warnings", [])
    q_errors = quality_data.get("errors", [])

    warnings_html = "".join(f"<li>{w}</li>" for w in q_warnings) if q_warnings else "<li>None</li>"
    errors_html = "".join(f"<li style='color:red'>{e}</li>" for e in q_errors) if q_errors else "<li>None</li>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inventory Optimization &amp; Forecasting Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #2980b9; margin-top: 30px; }}
        h3 {{ color: #34495e; }}
        .summary-box {{ background-color: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin-bottom: 20px; }}
        .config-box {{ background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 30px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; font-weight: bold; color: #2c3e50; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .visualisation {{ text-align: center; margin: 30px 0; }}
        img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; padding: 5px; }}
        .footer {{ margin-top: 50px; font-size: 0.8em; color: #7f8c8d; text-align: center; border-top: 1px solid #ddd; padding-top: 20px; }}
    </style>
</head>
<body>

    <h1>Inventory Optimization &amp; Forecasting Report</h1>
    <p><strong>Generated:</strong> {run_date}</p>

    <div class="config-box">
        <strong>Run Configuration:</strong> Holdout = {holdout} days | Service Level Z = {z_val} | Target Service Level = {["90%","95%","99%"][([1.28,1.65,2.33].index(z_val)) if z_val in [1.28,1.65,2.33] else 1]}
    </div>

    <div class="summary-box">
        <h2>1. Executive Summary</h2>
        <p>This automated analysis optimized inventory policies for <strong>{total_skus} SKUs</strong>
        across the enterprise supply chain. The pipeline dynamically selected the best performing
        predictive model per SKU, achieving an average WMAPE of <strong>{avg_wmape:.4f}</strong>.</p>
        <ul>
            <li><strong>Model Selection:</strong> Gradient Boosted Trees (GBR) won for {xgb_wins} SKUs, while Fourier Seasonal model was optimal for {prophet_wins} SKUs.</li>
            <li><strong>Service Level Target:</strong> Policies calibrated to Z = {z_val}.</li>
        </ul>
    </div>

    <h2>2. Methodology</h2>
    <p>The analytics pipeline executed a multi-algorithm champion/challenger methodology.
    For each SKU, both <strong>Gradient Boosted Trees</strong> (sklearn GBR with lag/rolling features)
    and a <strong>Fourier Seasonal Model</strong> (Ridge regression on yearly + weekly Fourier harmonics)
    were evaluated on a <strong>{holdout}-day holdout</strong> validation set using WMAPE.
    The winning model's demand statistics drive safety stock and reorder point calculations
    using the standard enterprise formulation from REFERENCE.md.</p>

    <h2>3. Data Quality Summary</h2>
    <p>Dataset: <strong>{q_rows} records</strong> across <strong>{q_cols} columns</strong>.
    Validation Status: <strong>{q_status}</strong></p>
    <h3>Warnings</h3><ul>{warnings_html}</ul>
    <h3>Errors</h3><ul>{errors_html}</ul>

    <h2>4. Results &amp; Visualisations</h2>
    <div class="visualisation">
        <img src="data:image/png;base64,{scatter_b64}" alt="Demand vs Safety Stock Scatter Plot">
        <p><em>Figure 1: Distribution of Recommended Safety Stock relative to average daily demand.</em></p>
    </div>
    <div class="visualisation">
        <img src="data:image/png;base64,{bar_b64}" alt="WMAPE Comparison Bar Chart">
        <p><em>Figure 2: GBR vs Fourier Seasonal WMAPE comparison by SKU. Green = Excellent (&lt;0.15), Red = Poor (&gt;0.30).</em></p>
    </div>

    <h2>5. Validation Metrics &amp; Inventory Policy Data</h2>
    <table>
        <thead>
            <tr>
                <th>SKU ID</th><th>Category</th><th>Archetype</th>
                <th>Winning Model (WMAPE)</th><th>Avg Daily Demand</th>
                <th>Safety Stock</th><th>Reorder Point</th>
            </tr>
        </thead>
        <tbody>{sku_rows}</tbody>
    </table>

    <h2>6. Business Interpretation &amp; Recommendations</h2>
    <ul>{reco_items}</ul>

    <h2>7. Assumptions &amp; Limitations</h2>
    <ul>
        <li>Lead times assumed normally distributed; historical supplier performance used as future proxy.</li>
        <li>Service level target ({z_val}) applies uniformly across all SKU categories — future iterations should incorporate margin-weighted targets.</li>
        <li>Demand forecasts are point estimates; no prediction intervals are generated in this version.</li>
        <li>Fourier seasonal model assumes additive seasonality; multiplicative patterns may be under-captured.</li>
    </ul>

    <h2>8. Data Appendix</h2>
    <p>Full per-SKU statistics are embedded in the results JSON artefact accompanying this report.</p>

    <div class="footer">
        Automated LLM-Powered Data Analytics Skill | System-Generated Report | {run_date}
    </div>

</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html_content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate HTML Analytics Report")
    parser.add_argument("--quality", required=True, help="Path to data quality JSON")
    parser.add_argument("--results", required=True, help="Path to optimization results JSON")
    parser.add_argument("--output", required=True, help="Path to save HTML report")
    args = parser.parse_args()

    try:
        with open(args.quality, "r") as f:
            quality_data = json.load(f)

        with open(args.results, "r") as f:
            optimization_data = json.load(f)

        generate_html_report(quality_data, optimization_data, args.output)
        print(f"Professional HTML report successfully generated at: {args.output}")

    except Exception as e:
        print(f"Failed to generate report: {e}")
        sys.exit(1)
