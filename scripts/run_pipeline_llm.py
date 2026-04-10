#!/usr/bin/env python3
"""LLM-Powered Pipeline Orchestrator — Uses Groq API for Insight Generation.

This runner integrates a real LLM (via Groq) into the analytics pipeline.
The LLM handles:
  - Stage 5: Reads optimization results + REFERENCE.md, generates business insights
  - Stage 6: Generates executive summary narrative for the HTML report

All LLM prompts, responses, token usage, and latency are logged in the execution trace.

Prerequisites:
    export GROQ_API_KEY="gsk_..."
    pip install groq

Usage:
    python3 scripts/run_pipeline_llm.py
    python3 scripts/run_pipeline_llm.py --model llama-3.3-70b-versatile
    python3 scripts/run_pipeline_llm.py --run 1   # run only scenario 1
"""

import subprocess
import json
import os
import sys
import time
import argparse
from datetime import datetime

try:
    from groq import Groq
except ImportError:
    print("ERROR: groq package not installed. Run: pip install groq")
    sys.exit(1)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg, trace):
    """Append a timestamped entry to the trace log and print to console."""
    entry = {"timestamp": datetime.now().isoformat(), "message": msg}
    trace.append(entry)
    print(f"  [{entry['timestamp']}] {msg}")


def log_llm_call(trace, stage, prompt, response_text, model, usage, latency):
    """Log a full LLM call with prompt, response, token usage, and latency."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "LLM_CALL",
        "stage": stage,
        "model": model,
        "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt,
        "response_preview": response_text[:1000] + "..." if len(response_text) > 1000 else response_text,
        "full_response_length": len(response_text),
        "token_usage": {
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        },
        "latency_seconds": round(latency, 2),
    }
    trace.append(entry)
    print(f"  [{entry['timestamp']}] LLM_CALL: {stage} | Model: {model} | "
          f"Tokens: {entry['token_usage']['total_tokens']} | Latency: {latency:.2f}s")


def save_trace(trace, path):
    """Persist the full execution trace to a JSON file."""
    with open(path, "w") as f:
        json.dump(trace, f, indent=2)
    print(f"  Trace saved → {path}")


# ── Shell command runner ──────────────────────────────────────────────────────

def run_command(cmd, trace, stage_name):
    """Execute a shell command, capture output, and record in trace."""
    log(f"STAGE START: {stage_name}", trace)
    log(f"  Command: {cmd}", trace)

    t0 = time.time()
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=BASE_DIR)
    elapsed = round(time.time() - t0, 2)

    log(f"  Exit code: {result.returncode} | Duration: {elapsed}s", trace)
    if result.stdout.strip():
        log(f"  STDOUT: {result.stdout.strip()[:500]}", trace)
    if result.stderr.strip():
        log(f"  STDERR: {result.stderr.strip()[:300]}", trace)

    return result.returncode, result.stdout, result.stderr


# ── LLM-powered stages ───────────────────────────────────────────────────────

def load_reference_md():
    """Load REFERENCE.md as context for the LLM."""
    ref_path = os.path.join(BASE_DIR, "REFERENCE.md")
    with open(ref_path, "r") as f:
        return f.read()


def llm_generate_insights(client, model, results_data, reference_md, trace):
    """Stage 5: Use Groq LLM to generate business insights from optimization results."""
    # Build a concise summary of results for the prompt
    sku_summary = []
    for sku in results_data["sku_results"]:
        sku_summary.append({
            "sku_id": sku["sku_id"],
            "category": sku["category"],
            "avg_daily_demand": sku["avg_daily_demand"],
            "cv_demand": sku["cv_demand"],
            "winning_algorithm": sku["winning_algorithm"],
            "winning_wmape": sku["winning_wmape"],
            "recommended_safety_stock": sku["recommended_safety_stock"],
            "reorder_point": sku["reorder_point"],
            "avg_lead_time_days": sku["avg_lead_time_days"],
        })

    config = results_data.get("config", {})

    prompt = f"""You are a senior supply chain analyst. Analyse the following inventory optimization results
and generate business insights following the domain knowledge in REFERENCE.md.

## REFERENCE.md (Domain Knowledge)
{reference_md}

## Pipeline Configuration
- Holdout validation: {config.get('holdout_days', 30)} days
- Service level Z-score: {config.get('service_level_z', 1.65)}

## SKU Optimization Results
{json.dumps(sku_summary, indent=2)}

## Instructions
For each SKU:
1. Classify it into an archetype from REFERENCE.md Section 4 (Stable Baseload, Highly Seasonal, or Erratic/Volatile) based on its CV, WMAPE, and winning algorithm.
2. Interpret what the winning algorithm choice means for the SKU's demand pattern (refer to Section 3).
3. Generate a specific business recommendation using the templates in REFERENCE.md Section 5.
4. Flag any SKUs with WMAPE > 0.30 as requiring special attention.

Format your response as a structured analysis with clear sections per SKU archetype group.
End with an overall portfolio summary and top 3 actionable priorities."""

    t0 = time.time()
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a supply chain analytics expert. Provide precise, data-driven insights grounded strictly in the REFERENCE.md domain knowledge provided. Do not hallucinate metrics or benchmarks."},
            {"role": "user", "content": prompt}
        ],
        model=model,
        temperature=0.3,
        max_tokens=3000,
    )
    latency = time.time() - t0

    response_text = chat_completion.choices[0].message.content
    usage = chat_completion.usage

    log_llm_call(trace, "Stage 5: Insight Generation", prompt, response_text, model, usage, latency)

    return response_text


def llm_generate_executive_summary(client, model, results_data, quality_data, insights, trace):
    """Use Groq LLM to generate the executive summary narrative for the report."""
    sku_results = results_data["sku_results"]
    total_skus = len(sku_results)
    avg_wmape = sum(r["winning_wmape"] for r in sku_results) / total_skus
    xgb_wins = sum(1 for r in sku_results if r["winning_algorithm"] == "Gradient Boosted Trees")
    prophet_wins = total_skus - xgb_wins
    config = results_data.get("config", {})

    prompt = f"""Write a concise executive summary (3-4 paragraphs) for an inventory optimization report.

Key metrics:
- {total_skus} SKUs analysed
- Average WMAPE: {avg_wmape:.4f}
- Gradient Boosted Trees won for {xgb_wins} SKUs, Fourier Seasonal model won for {prophet_wins} SKUs
- Service level target: Z = {config.get('service_level_z', 1.65)}
- Holdout validation period: {config.get('holdout_days', 30)} days
- Data quality status: {quality_data.get('status', 'PASS')} with {len(quality_data.get('warnings', []))} warnings

The LLM-generated insights identified these patterns:
{insights[:1500]}

Write for a VP of Supply Chain. Be specific with numbers. Mention which SKU categories need attention."""

    t0 = time.time()
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are writing a professional executive summary for an enterprise inventory optimization report. Be concise, data-driven, and actionable."},
            {"role": "user", "content": prompt}
        ],
        model=model,
        temperature=0.2,
        max_tokens=1000,
    )
    latency = time.time() - t0

    response_text = chat_completion.choices[0].message.content
    usage = chat_completion.usage

    log_llm_call(trace, "Stage 6: Executive Summary Generation", prompt, response_text, model, usage, latency)

    return response_text


# ── Report generation with LLM content ────────────────────────────────────────

def generate_llm_enhanced_report(quality_data, results_data, llm_insights, llm_exec_summary, output_path):
    """Generate HTML report with LLM-produced insights injected."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64
    from io import BytesIO

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = results_data.get("config", {})
    holdout = config.get("holdout_days", 30)
    z_val = config.get("service_level_z", 1.65)
    sku_results = results_data["sku_results"]
    total_skus = len(sku_results)
    avg_wmape = sum(r["winning_wmape"] for r in sku_results) / total_skus
    xgb_wins = sum(1 for r in sku_results if r["winning_algorithm"] == "Gradient Boosted Trees")
    prophet_wins = total_skus - xgb_wins

    # ── Chart 1: Scatter ──
    fig, ax = plt.subplots(figsize=(10, 6))
    cats = list(set(r["category"] for r in sku_results))
    cmap = plt.colormaps.get_cmap("tab10")
    for i, cat in enumerate(cats):
        subset = [r for r in sku_results if r["category"] == cat]
        ax.scatter([r["avg_daily_demand"] for r in subset],
                   [r["recommended_safety_stock"] for r in subset],
                   label=cat, color=cmap(i), s=100, alpha=0.7, edgecolors="k")
    ax.set_title("Avg Daily Demand vs. Recommended Safety Stock", fontsize=14)
    ax.set_xlabel("Average Daily Demand (units)")
    ax.set_ylabel("Recommended Safety Stock (units)")
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(title="Category", bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
    plt.tight_layout()
    buf = BytesIO(); plt.savefig(buf, format="png", dpi=120); plt.close(); buf.seek(0)
    scatter_b64 = base64.b64encode(buf.read()).decode("utf-8")

    # ── Chart 2: WMAPE bar ──
    fig, ax = plt.subplots(figsize=(12, 6))
    skus = [r["sku_id"].replace("SKU_", "") for r in sku_results]
    xgb_vals = [r["gbr_wmape"] for r in sku_results]
    pro_vals = [r["fourier_wmape"] for r in sku_results]
    x = range(len(skus)); w = 0.35
    ax.bar([i - w/2 for i in x], xgb_vals, w, label="Gradient Boosted Trees", color="#e74c3c", alpha=0.8)
    ax.bar([i + w/2 for i in x], pro_vals, w, label="Fourier Seasonal", color="#3498db", alpha=0.8)
    ax.axhline(y=0.30, color="red", linestyle="--", alpha=0.5, label="Poor (0.30)")
    ax.axhline(y=0.15, color="green", linestyle="--", alpha=0.5, label="Excellent (0.15)")
    ax.set_ylabel("WMAPE"); ax.set_title("Model Comparison: GBR vs Fourier Seasonal WMAPE")
    ax.set_xticks(list(x)); ax.set_xticklabels(skus, rotation=45, ha="right", fontsize=8)
    ax.legend(); plt.tight_layout()
    buf = BytesIO(); plt.savefig(buf, format="png", dpi=120); plt.close(); buf.seek(0)
    bar_b64 = base64.b64encode(buf.read()).decode("utf-8")

    # ── SKU table ──
    sku_rows = ""
    for item in sku_results:
        cv = item["cv_demand"]; wmape = item["winning_wmape"]; winner = item["winning_algorithm"]
        if cv < 0.20 and wmape < 0.15:
            arch = "Stable Baseload"
        elif winner == "Fourier Seasonal":
            arch = "Highly Seasonal"
        elif wmape > 0.30:
            arch = "Erratic / Volatile"
        else:
            arch = "Moderate Demand"
        color = "#27ae60" if wmape < 0.15 else ("#f39c12" if wmape < 0.30 else "#e74c3c")
        sku_rows += f"""<tr>
            <td>{item['sku_id']}</td><td>{item['category']}</td><td>{arch}</td>
            <td style="color:{color};font-weight:bold">{winner} ({wmape:.4f})</td>
            <td>{item['avg_daily_demand']:.1f}</td>
            <td><strong>{int(item['recommended_safety_stock'])}</strong></td>
            <td><strong>{int(item['reorder_point'])}</strong></td></tr>"""

    # Quality section
    q_warnings = "".join(f"<li>{w}</li>" for w in quality_data.get("warnings", [])) or "<li>None</li>"
    q_errors = "".join(f"<li style='color:red'>{e}</li>" for e in quality_data.get("errors", [])) or "<li>None</li>"

    # Convert LLM markdown to basic HTML
    import re
    def md_to_html(text):
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'^### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'(<li>.*?</li>\n?)+', lambda m: '<ul>' + m.group(0) + '</ul>', text)
        text = text.replace('\n\n', '</p><p>').replace('\n', '<br>')
        return f'<p>{text}</p>'

    insights_html = md_to_html(llm_insights)
    exec_summary_html = md_to_html(llm_exec_summary)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM-Powered Inventory Optimization Report</title>
<style>
body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #2980b9; margin-top: 30px; }}
h3 {{ color: #34495e; }}
.summary-box {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 20px 0; }}
.llm-box {{ background: #f0f7ff; border-left: 4px solid #8e44ad; padding: 15px; margin: 20px 0; }}
.llm-badge {{ display: inline-block; background: #8e44ad; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; margin-left: 8px; }}
.config-box {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 15px 0 30px; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f2f2f2; font-weight: bold; color: #2c3e50; }}
tr:hover {{ background: #f5f5f5; }}
.vis {{ text-align: center; margin: 30px 0; }}
img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; padding: 5px; }}
.footer {{ margin-top: 50px; font-size: 0.8em; color: #7f8c8d; text-align: center; border-top: 1px solid #ddd; padding-top: 20px; }}
</style>
</head>
<body>

<h1>LLM-Powered Inventory Optimization &amp; Forecasting Report</h1>
<p><strong>Generated:</strong> {run_date} <span class="llm-badge">Groq LLM Enhanced</span></p>

<div class="config-box">
<strong>Run Configuration:</strong> Holdout = {holdout} days | Service Level Z = {z_val} | SKUs = {total_skus}
</div>

<div class="summary-box">
<h2>1. Executive Summary <span class="llm-badge">LLM Generated</span></h2>
{exec_summary_html}
</div>

<h2>2. Methodology</h2>
<p>The pipeline ran a champion/challenger competition between <strong>Gradient Boosted Trees</strong>
(sklearn GBR with lag/rolling features) and a <strong>Fourier Seasonal Model</strong> (Ridge regression
on yearly + weekly Fourier harmonics) over a <strong>{holdout}-day holdout</strong>. WMAPE determined
the winner per SKU. Safety stock and reorder points were computed using the enterprise formulation
from REFERENCE.md. Business insights were generated by an LLM (Groq) grounded in REFERENCE.md domain knowledge.</p>

<h2>3. Data Quality Summary</h2>
<p>Rows: <strong>{quality_data.get('row_count', 'N/A')}</strong> | Columns: <strong>{quality_data.get('column_count', 'N/A')}</strong> | Status: <strong>{quality_data.get('status', 'N/A')}</strong></p>
<h3>Warnings</h3><ul>{q_warnings}</ul>
<h3>Errors</h3><ul>{q_errors}</ul>

<h2>4. Results &amp; Visualisations</h2>
<div class="vis"><img src="data:image/png;base64,{scatter_b64}" alt="Scatter"><p><em>Figure 1: Demand vs Safety Stock by category.</em></p></div>
<div class="vis"><img src="data:image/png;base64,{bar_b64}" alt="WMAPE Comparison"><p><em>Figure 2: GBR vs Fourier Seasonal WMAPE. Green=Excellent, Red=Poor.</em></p></div>

<h2>5. Validation Metrics &amp; Inventory Policy</h2>
<p>Average WMAPE: <strong>{avg_wmape:.4f}</strong> | GBR wins: {xgb_wins} | Fourier wins: {prophet_wins}</p>
<table><thead><tr><th>SKU</th><th>Category</th><th>Archetype</th><th>Winner (WMAPE)</th><th>Avg Demand</th><th>Safety Stock</th><th>ROP</th></tr></thead>
<tbody>{sku_rows}</tbody></table>

<h2>6. Business Interpretation &amp; Recommendations <span class="llm-badge">LLM Generated</span></h2>
<div class="llm-box">{insights_html}</div>

<h2>7. Assumptions &amp; Limitations</h2>
<ul>
<li>Lead times assumed normally distributed; historical supplier data used as future proxy.</li>
<li>Uniform service level Z={z_val} across all SKUs — margin-weighted targets recommended for future iterations.</li>
<li>LLM insights are grounded in REFERENCE.md but should be reviewed by domain experts before action.</li>
<li>Fourier model assumes additive seasonality; multiplicative patterns may be under-captured.</li>
</ul>

<div class="footer">
LLM-Powered Data Analytics Skill | Groq API | {run_date}
</div>
</body></html>"""

    with open(output_path, "w") as f:
        f.write(html)


# ── Failure report (no LLM needed) ────────────────────────────────────────────

def generate_failure_report(quality, run_dir, scenario, trace):
    """Generate a brief HTML report explaining why the pipeline halted."""
    errors = quality.get("errors", [])
    warnings = quality.get("warnings", [])
    errors_html = "".join(f"<li style='color:red'><strong>{e}</strong></li>" for e in errors)
    warnings_html = "".join(f"<li style='color:orange'>{w}</li>" for w in warnings)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Pipeline Failure Report — {scenario['name']}</title>
<style>body {{ font-family: 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
h1 {{ color: #c0392b; }} .box {{ background: #fdf2f2; border-left: 4px solid #e74c3c; padding: 15px; margin: 20px 0; }}</style>
</head><body>
<h1>Pipeline Failure Report</h1>
<p><strong>Scenario:</strong> {scenario['name']}<br>
<strong>Dataset:</strong> {scenario['data_path']}<br>
<strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<div class="box">
<h2>Validation Status: FAIL</h2>
<p>The data validation stage detected critical issues. The pipeline correctly halted.</p>
<h3>Critical Errors</h3><ul>{errors_html}</ul>
<h3>Warnings</h3><ul>{warnings_html if warnings_html else '<li>None</li>'}</ul>
</div>
<h2>How to Fix</h2>
<ul>
<li>Ensure all required columns exist: <code>date, sku_id, category, sales_volume, unit_cost, lead_time_days</code></li>
<li>No column should have &gt;30% null values.</li>
<li><code>sales_volume</code> and <code>unit_cost</code> must be non-negative.</li>
<li><code>lead_time_days</code> must be &ge; 1.</li>
</ul>
</body></html>"""

    path = os.path.join(run_dir, "failure_report.html")
    with open(path, "w") as f:
        f.write(html)
    log(f"Failure report generated → {path}", trace)


# ── Main scenario runner ──────────────────────────────────────────────────────

def run_scenario(scenario, client, model):
    """Execute a single end-to-end pipeline scenario with LLM integration."""
    name = scenario["name"]
    run_dir = os.path.join(OUTPUT_DIR, scenario["run_id"])
    os.makedirs(run_dir, exist_ok=True)

    trace = []
    log(f"{'='*60}", trace)
    log(f"PIPELINE RUN: {name}", trace)
    log(f"Run ID: {scenario['run_id']} | LLM Model: {model}", trace)
    log(f"Output directory: {run_dir}", trace)
    log(f"{'='*60}", trace)

    data_path = scenario["data_path"]
    quality_path = os.path.join(run_dir, "quality_report.json")
    results_path = os.path.join(run_dir, "optimization_results.json")
    report_path = os.path.join(run_dir, "final_inventory_report.html")

    # ── Optional: Generate synthetic data ──
    if scenario.get("generate_data_cmd"):
        rc, _, _ = run_command(scenario["generate_data_cmd"], trace, "Data Generation")
        if rc != 0:
            log("CRITICAL: Data generation failed. Aborting.", trace)
            save_trace(trace, os.path.join(run_dir, "execution_trace.json"))
            return False

    # ── Stage 1: Data Validation ──
    cmd = f"python3 scripts/validate_data.py --input {data_path} --output {quality_path}"
    rc, _, _ = run_command(cmd, trace, "Stage 1: Data Validation & Profiling")

    if os.path.exists(quality_path):
        with open(quality_path) as f:
            quality = json.load(f)
        log(f"  Quality Status: {quality.get('status', 'UNKNOWN')}", trace)
        for w in quality.get("warnings", []):
            log(f"  [WARNING] {w}", trace)
        for e in quality.get("errors", []):
            log(f"  [ERROR] {e}", trace)
    else:
        quality = {"status": "CRITICAL_FAILURE"}

    if quality.get("status") in ("FAIL", "CRITICAL_FAILURE"):
        log("PIPELINE HALTED: Data validation failed.", trace)
        if quality.get("status") == "FAIL":
            log("This is EXPECTED for failure-scenario runs.", trace)
        save_trace(trace, os.path.join(run_dir, "execution_trace.json"))
        generate_failure_report(quality, run_dir, scenario, trace)
        return False

    # ── Stage 2 & 3: Feature Engineering & Modelling ──
    holdout = scenario.get("holdout_days", 30)
    z_val = scenario.get("service_level_z", 1.65)
    cmd = (f"python3 scripts/forecast_and_optimize.py --input {data_path} "
           f"--output {results_path} --holdout_days {holdout} --service_level_z {z_val}")
    rc, _, _ = run_command(cmd, trace, "Stage 2 & 3: Feature Engineering & Modelling")

    if rc != 0:
        log("PIPELINE HALTED: Forecast/optimize script failed.", trace)
        save_trace(trace, os.path.join(run_dir, "execution_trace.json"))
        return False

    # ── Stage 4: Result Validation ──
    log("STAGE START: Stage 4: Result Validation", trace)
    with open(results_path) as f:
        results = json.load(f)
    n_skus = len(results.get("sku_results", []))
    log(f"  Validated {n_skus} SKU results.", trace)

    for sku in results["sku_results"]:
        if sku.get("winning_wmape", 0) > 0.30:
            log(f"  [FLAG] {sku['sku_id']}: WMAPE={sku['winning_wmape']:.4f} > 0.30", trace)

    missing = [s["sku_id"] for s in results["sku_results"] if "winning_algorithm" not in s]
    if missing:
        log(f"  [ERROR] Missing winning_algorithm: {missing}", trace)
    else:
        log(f"  All {n_skus} SKUs validated.", trace)

    # ── Stage 5: LLM Insight Generation (GROQ) ──
    log("STAGE START: Stage 5: LLM Insight Generation (Groq)", trace)
    reference_md = load_reference_md()

    try:
        llm_insights = llm_generate_insights(client, model, results, reference_md, trace)
        # Save raw LLM output as intermediate artifact
        insights_path = os.path.join(run_dir, "llm_insights.md")
        with open(insights_path, "w") as f:
            f.write(llm_insights)
        log(f"  LLM insights saved → {insights_path}", trace)
    except Exception as e:
        log(f"  [ERROR] LLM insight generation failed: {e}", trace)
        llm_insights = "(LLM insight generation failed — see trace for details)"

    # ── Stage 6: LLM Executive Summary + Report Generation ──
    log("STAGE START: Stage 6: LLM Report Generation (Groq)", trace)

    try:
        llm_exec_summary = llm_generate_executive_summary(
            client, model, results, quality, llm_insights, trace)
        summary_path = os.path.join(run_dir, "llm_executive_summary.md")
        with open(summary_path, "w") as f:
            f.write(llm_exec_summary)
        log(f"  LLM executive summary saved → {summary_path}", trace)
    except Exception as e:
        log(f"  [ERROR] LLM summary generation failed: {e}", trace)
        llm_exec_summary = "(LLM summary generation failed)"

    generate_llm_enhanced_report(quality, results, llm_insights, llm_exec_summary, report_path)
    log(f"PIPELINE COMPLETE: Report → {report_path}", trace)
    save_trace(trace, os.path.join(run_dir, "execution_trace.json"))
    return True


# ── Scenario definitions ──────────────────────────────────────────────────────

SCENARIOS = [
    {
        "run_id": "run1_default_20sku",
        "name": "Run 1: Original 20-SKU Dataset — Default Params (95% SL, 30-day holdout)",
        "data_path": "data/synthetic_inventory_data.csv",
        "holdout_days": 30,
        "service_level_z": 1.65,
        "generate_data_cmd": None,
    },
    {
        "run_id": "run2_alt_15sku_99sl",
        "name": "Run 2: Alternative 15-SKU Dataset — Aggressive Params (99% SL, 45-day holdout)",
        "data_path": "data/dataset_run2.csv",
        "holdout_days": 45,
        "service_level_z": 2.33,
        "generate_data_cmd": (
            "python3 scripts/generate_synthetic_data.py "
            "--output data/dataset_run2.csv --seed 99 --catalogue B "
            "--start_date 2023-06-01 --end_date 2026-03-31"
        ),
    },
    {
        "run_id": "run3_bad_data_failure",
        "name": "Run 3: Corrupted Dataset — Failure Scenario (Expected: Pipeline Halts)",
        "data_path": "data/bad_data.csv",
        "holdout_days": 30,
        "service_level_z": 1.65,
        "generate_data_cmd": (
            "python3 scripts/generate_synthetic_data.py "
            "--output data/bad_data.csv --seed 42 --catalogue A --n_skus 5 "
            "--start_date 2024-01-01 --end_date 2025-12-31 --inject_bad_data"
        ),
    },
]


def main():
    parser = argparse.ArgumentParser(description="LLM-Powered Inventory Optimization Pipeline")
    parser.add_argument("--model", default="llama-3.3-70b-versatile",
                        help="Groq model ID (default: llama-3.3-70b-versatile)")
    parser.add_argument("--run", type=int, choices=[1, 2, 3], default=None,
                        help="Run only a specific scenario (1, 2, or 3)")
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY environment variable not set.")
        print("  export GROQ_API_KEY='gsk_...'")
        sys.exit(1)

    client = Groq(api_key=api_key)
    model = args.model

    print("=" * 70)
    print("  INVENTORY OPTIMIZATION SKILL — LLM-POWERED PIPELINE RUNNER")
    print(f"  Groq Model: {model}")
    print(f"  Scenarios: {'All 3' if args.run is None else f'Run {args.run} only'}")
    print("=" * 70)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    scenarios = SCENARIOS if args.run is None else [SCENARIOS[args.run - 1]]

    summary = []
    for scenario in scenarios:
        print(f"\n{'─'*70}")
        print(f"  Starting: {scenario['name']}")
        print(f"{'─'*70}\n")

        success = run_scenario(scenario, client, model)
        summary.append({
            "run_id": scenario["run_id"],
            "name": scenario["name"],
            "success": success,
            "model": model,
            "output_dir": os.path.join(OUTPUT_DIR, scenario["run_id"]),
        })

    print(f"\n{'='*70}")
    print("  EXECUTION SUMMARY")
    print(f"{'='*70}")
    for s in summary:
        status = "SUCCESS" if s["success"] else "HALTED (expected for failure scenario)"
        print(f"  [{status}] {s['name']}")
        print(f"           → {s['output_dir']}")

    summary_path = os.path.join(OUTPUT_DIR, "run_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Run summary → {summary_path}")


if __name__ == "__main__":
    main()
