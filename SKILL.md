# SKILL: Enterprise Inventory Optimization & Demand Forecasting

## 1. Skill Overview
This skill orchestrates a complete, multi-algorithm analytics pipeline to optimize inventory levels and forecast demand for Fast-Moving Consumer Goods (FMCG). It ingests daily SKU-level time-series data, profiles for data quality, engineers temporal features, evaluates competing predictive models (Gradient Boosted Trees vs. Fourier Seasonal), calculates safety stock using statistical variance, and generates a professional HTML report.

**Prerequisites:** Ensure the LLM has access to the `./scripts` directory and `./REFERENCE.md` in the workspace.

---

## 2. Expected Inputs

**A. Dataset Input:**
* **Format:** CSV file.
* **Required Columns:** `date`, `sku_id`, `category`, `sales_volume`, `unit_cost`, `lead_time_days`.
* **Location:** e.g., `data/synthetic_inventory_data.csv`.

**B. Configuration Parameters (Optional defaults provided):**
* `holdout_days`: Number of days for model validation (Default: 30).
* `service_level_z`: Target service level for safety stock (Default: 1.65 for 95%).

---

## 3. Mandatory Execution Pipeline

You **must** execute the following six stages sequentially. Do not skip steps. Halt execution immediately if a step throws a critical error.

### Stage 1: Data Validation & Profiling
**Objective:** Profile the incoming dataset, check for null values, and enforce zero-bound constraints.
1.  **Execute Command:** `python scripts/validate_data.py --input data/synthetic_inventory_data.csv --output quality_report.json`
2.  **Validation Rule:** Read `quality_report.json`. 
    * If `"status": "FAIL"`, halt execution and report the exact errors to the user. Do not proceed to modelling.
    * If `"warnings"` exist regarding null values, inform the user that these will be handled via linear interpolation in Stage 2.

### Stage 2 & 3: Feature Engineering & Multi-Algorithm Modelling
**Objective:** Transform raw data into analysis-ready lag features, and run a champion/challenger forecasting competition. 
*(Note: Feature engineering, imputation, and modelling are bundled into a single script for computational efficiency).*
1.  **Execute Command:**
    `python scripts/forecast_and_optimize.py --input data/synthetic_inventory_data.csv --output optimization_results.json`
2.  **Output Expectation:** The script runs both Gradient Boosted Trees and Fourier Seasonal on a 30-day validation holdout. It computes the WMAPE for both, selects the winning model per SKU, and calculates `recommended_safety_stock` and `reorder_point`.

### Stage 4: Result Validation
**Objective:** Verify the optimization script executed successfully and the metrics are within acceptable bounds.
1.  **Validation Rule:** Read `optimization_results.json`.
    * Verify every SKU has a `"winning_algorithm"` (either "Gradient Boosted Trees" or "Fourier Seasonal").
    * Consult `REFERENCE.md` Section 2. If any SKU has a `"winning_wmape"` > 0.30, flag it internally for the interpretation stage as "Poor Accuracy / High Volatility."

### Stage 5: Insight Generation & Business Interpretation
**Objective:** Translate the mathematical outputs from Stage 4 into actionable supply chain insights. **Do not hallucinate; you must consult `REFERENCE.md`.**
1.  **Action:** Review the `"sku_results"` array in `optimization_results.json`.
2.  **Interpretation Logic:** For each SKU, determine its archetype based on `REFERENCE.md` Section 4 (e.g., Stable Baseload, Highly Seasonal, Erratic).
3.  **Drafting:** Draft standard business recommendations utilizing the exact templates provided in `REFERENCE.md` Section 5. *Hold these drafted insights in context; they will be structurally embedded in the final HTML report.*

### Stage 6: Professional Report Generation
**Objective:** Compile the validation summary, model metrics, visualisations, and your drafted business interpretations into a final HTML document.
1.  **Execute Command:**
    `python scripts/generate_report.py --quality quality_report.json --results optimization_results.json --output final_inventory_report.html`
2.  **Final Validation:** Confirm `final_inventory_report.html` has been successfully created.
3.  **User Output:** Present a brief executive summary of the pipeline execution to the user, highlighting the average WMAPE achieved and the total number of SKUs optimized. Provide instructions on how to access the generated HTML report.