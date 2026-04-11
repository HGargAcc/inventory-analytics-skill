# Inventory Optimization & Demand Forecasting — LLM-Powered Analytics Skill

An end-to-end, LLM-powered data analytics skill that automates inventory optimization and demand forecasting for FMCG supply chains. The skill ingests daily SKU-level time-series data, validates quality, engineers temporal features, runs a champion/challenger forecasting competition (Gradient Boosted Trees vs. Fourier Seasonal), computes safety stock and reorder points, and generates a professional HTML report with LLM-authored business insights via the Groq API.

## Repository Structure

```
inventory-analytics-skill/
├── SKILL.md                        # Core skill instructions — full 6-stage pipeline
├── REFERENCE.md                    # Domain knowledge: formulas, archetypes, benchmarks
├── design_walkthrough.html         # 4-page design decisions document
├── scripts/
│   ├── validate_data.py            # Stage 1: Data profiling & validation
│   ├── forecast_and_optimize.py    # Stage 2-3: Feature engineering & multi-algorithm modelling
│   ├── generate_report.py          # Stage 6: HTML report with embedded charts
│   ├── generate_synthetic_data.py  # Synthetic data generator (2 SKU catalogues + defect injection)
│   └── run_pipeline_llm.py         # Full pipeline orchestrator with Groq LLM integration & tracing
├── data/
│   ├── synthetic_inventory_data.csv  # Primary dataset: 20 SKUs, Jan 2023 – Mar 2026
│   ├── dataset_run2.csv              # Alternative dataset: 15 SKUs (Catalogue B)
│   ├── bad_data.csv                  # Corrupted dataset for failure testing
│   └── data_dictionary.md            # Column definitions & validation constraints
├── templates/
│   └── report_template.html        # Base HTML template for report generation
└── outputs/
    ├── run_summary.json            # Aggregate summary of all 3 runs
    ├── run1_default_20sku/         # Run 1: 20 SKUs, 95% SL, 30-day holdout
    │   ├── execution_trace.json
    │   ├── quality_report.json
    │   ├── optimization_results.json
    │   ├── llm_insights.md
    │   ├── llm_executive_summary.md
    │   └── final_inventory_report.html
    ├── run2_alt_15sku_99sl/        # Run 2: 15 SKUs, 99% SL, 45-day holdout
    │   ├── execution_trace.json
    │   ├── quality_report.json
    │   ├── optimization_results.json
    │   ├── llm_insights.md
    │   ├── llm_executive_summary.md
    │   └── final_inventory_report.html
    └── run3_bad_data_failure/      # Run 3: Corrupted data — pipeline halts as expected
        ├── execution_trace.json
        ├── quality_report.json
        └── failure_report.html
```

## Pipeline Stages

| Stage | Script / Actor | Description |
|-------|---------------|-------------|
| 1. Data Validation | `validate_data.py` | Profiles dataset, enforces schema constraints (non-negative sales, lead time >= 1, <30% nulls). Halts pipeline on failure. |
| 2. Feature Engineering | `forecast_and_optimize.py` | Builds 17 features per SKU: lag values (1/7/14/28-day), rolling stats (mean & std over 7/14/28-day windows), calendar features. |
| 3. Multi-Algorithm Modelling | `forecast_and_optimize.py` | Runs Gradient Boosted Trees (sklearn GBR) vs. Fourier Seasonal (Ridge + Fourier harmonics) on holdout set. Selects winner per SKU by WMAPE. |
| 4. Result Validation | `run_pipeline_llm.py` | Verifies all SKUs have a winning algorithm. Flags WMAPE > 0.30 as poor accuracy. |
| 5. Insight Generation | **Groq LLM** | LLM reads optimization results + REFERENCE.md, classifies SKU archetypes, generates business recommendations. |
| 6. Report Generation | `generate_report.py` + **Groq LLM** | Produces self-contained HTML report with scatter plots, WMAPE bar charts, LLM-authored executive summary. |

## Setup & Installation

### Prerequisites
- Python 3.9+
- A Groq API key ([console.groq.com](https://console.groq.com))

### Install Dependencies

```bash
pip install pandas numpy scikit-learn matplotlib groq
```

### Set API Key

```bash
export GROQ_API_KEY="gsk_your_key_here"
```

## Running the Pipeline

### Run all 3 scenarios (2 success + 1 failure)

```bash
python3 scripts/run_pipeline_llm.py
```

### Run a single scenario

```bash
python3 scripts/run_pipeline_llm.py --run 1    # Default 20-SKU dataset
python3 scripts/run_pipeline_llm.py --run 2    # Alternative 15-SKU dataset
python3 scripts/run_pipeline_llm.py --run 3    # Corrupted data (failure test)
```

### Use a different Groq model

```bash
python3 scripts/run_pipeline_llm.py --model llama-3.1-8b-instant
```

### Run individual scripts manually

```bash
# Stage 1: Validate data
python3 scripts/validate_data.py --input data/synthetic_inventory_data.csv --output quality_report.json

# Stage 2-3: Forecast & optimize
python3 scripts/forecast_and_optimize.py --input data/synthetic_inventory_data.csv --output optimization_results.json --holdout_days 30 --service_level_z 1.65

# Stage 6: Generate report
python3 scripts/generate_report.py --quality quality_report.json --results optimization_results.json --output report.html
```

### Generate new synthetic data

```bash
# Clean dataset with Catalogue B (15 SKUs)
python3 scripts/generate_synthetic_data.py --output data/custom.csv --seed 123 --catalogue B

# Corrupted dataset for testing guardrails
python3 scripts/generate_synthetic_data.py --output data/bad.csv --seed 42 --inject_bad_data
```

## Test Scenarios

| Scenario | Dataset | Parameters | Expected Outcome |
|----------|---------|------------|-----------------|
| **Run 1** | 20 SKUs (Catalogue A), 23,741 rows | holdout=30d, Z=1.65 (95% SL) | Full pipeline success with HTML report |
| **Run 2** | 15 SKUs (Catalogue B), 15,525 rows | holdout=45d, Z=2.33 (99% SL) | Full pipeline success with higher safety stock |
| **Run 3** | 5 SKUs with injected defects (40% nulls, negatives, zero lead times) | holdout=30d, Z=1.65 | Pipeline halts at Stage 1 with failure report |

## Key Design Decisions

- **Deterministic computation, LLM interpretation:** All math runs in Python with fixed seeds. The LLM is used only for narrative insight generation — grounded in REFERENCE.md to prevent hallucination.
- **Fail-fast guardrails:** Pipeline halts on data quality failure rather than producing unreliable forecasts.
- **Full observability:** Every stage, LLM call (prompt, response, tokens, latency), and decision is logged in `execution_trace.json`.
- **No heavy dependencies:** Replaced Facebook Prophet with a Fourier Seasonal model (Ridge + Fourier harmonics) using only sklearn — zero additional installs.

## Algorithms

| Algorithm | Implementation | Best For |
|-----------|---------------|----------|
| **Gradient Boosted Trees** | `sklearn.ensemble.GradientBoostingRegressor` (300 estimators, depth 5, lr 0.05) | Erratic demand, trend shifts, non-linear patterns |
| **Fourier Seasonal** | `sklearn.linear_model.Ridge` on linear trend + yearly/weekly Fourier harmonics (3 orders) | Calendar-driven seasonality, stable periodic patterns |

## Domain Reference

See [REFERENCE.md](REFERENCE.md) for:
- Safety stock & reorder point formulas
- WMAPE threshold benchmarks (Excellent < 0.15, Acceptable < 0.30, Poor > 0.30)
- SKU archetype definitions (Stable Baseload, Highly Seasonal, Erratic/Volatile)
- Business recommendation templates per archetype

---

**AMPBA CT2 Group Assignment Group 2 | April 2026**
