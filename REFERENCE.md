# Domain Knowledge Reference: Inventory Optimization & Demand Forecasting

This document serves as the absolute source of truth for supply chain mathematical formulas, algorithm selection criteria, SKU archetypes, and business recommendation templates. **Do not hallucinate supply chain logic; rely strictly on the definitions provided below.**

## 1. Core Mathematical Formulas

### Safety Stock (SS)
Safety stock acts as a buffer against both demand volatility and supply chain lead time variability. The calculation utilizes the standard enterprise formulation:

$$SS = Z \cdot \sqrt{(\bar{L} \cdot \sigma_d^2) + (\bar{D}^2 \cdot \sigma_L^2)}$$

Where:
* $Z$ = Service Level Factor (Z-score)
* $\bar{L}$ = Average Lead Time (Days)
* $\sigma_d$ = Standard Deviation of Daily Demand
* $\bar{D}$ = Average Daily Demand
* $\sigma_L$ = Standard Deviation of Lead Time

### Reorder Point (ROP)
The inventory level that triggers a replenishment order.

$$ROP = (\bar{D} \cdot \bar{L}) + SS$$

## 2. Industry Benchmarks & Target Thresholds

* **Service Level (Z-Scores):**
  * 90% Service Level: $Z = 1.28$ (Used for low-margin, highly substitutable items)
  * 95% Service Level: $Z = 1.65$ (Standard default for most FMCG categories)
  * 99% Service Level: $Z = 2.33$ (Used for high-margin, critical, or "never-out" SKUs)
* **WMAPE (Weighted Mean Absolute Percentage Error) Thresholds:**
  * $< 15\%$: Excellent forecast accuracy.
  * $15\% - 30\%$: Acceptable accuracy; standard for seasonal or promotional items.
  * $> 30\%$: Poor accuracy; indicates highly erratic demand or missing feature data.

## 3. Algorithm Selection Criteria

The pipeline executes a champion/challenger model utilizing two distinct algorithms. The selection of the winning algorithm provides insight into the underlying demand behavior:

* **Fourier Seasonal Model (Fourier+Trend Ridge Regression) — labelled "Fourier Seasonal" in outputs:**
  * **Implementation:** A Ridge regression model fitted on a linear trend term plus yearly (period = 365.25 days) and weekly (period = 7 days) Fourier harmonics (3 orders each), totalling 14 features. This uses an additive decomposition of trend + multi-period seasonality to isolate calendar-driven patterns.
  * **When it wins:** Indicates the SKU is driven heavily by calendar events, strict day-of-week patterns, or macro-annual seasonality (e.g., holiday spikes for chilled proteins or summer spikes for beverages).
  * **Strengths:** Robust to missing data (interpolated prior to fitting); mathematically isolates seasonality from macro trends via explicit Fourier decomposition.
* **Gradient Boosted Trees (sklearn GradientBoostingRegressor) — labelled "Gradient Boosted Trees" in outputs:**
  * **Implementation:** `sklearn.ensemble.GradientBoostingRegressor` with 300 estimators, max depth 5, learning rate 0.05, and 80% subsample ratio. Trained on engineered lag features (1, 7, 14, 28-day), rolling statistics (7, 14, 28-day mean & std), and calendar features (day-of-week, month, day-of-year, week-of-year).
  * **When it wins:** Indicates the SKU is driven by recent momentum, sudden trend shifts, or complex non-linear interactions captured in the lag features and rolling averages.
  * **Strengths:** Excellent for erratic items, viral products, or items undergoing sudden market shifts.

## 4. SKU Archetypes & Interpretation Frameworks

When translating the raw numbers into business insights, categorize the SKUs into the following archetypes based on their data profile:

* **Stable Baseload:**
  * *Profile:* Low demand volatility ($\sigma_d < 20\%$ of $\bar{D}$), WMAPE $< 15\%$.
  * *Interpretation:* Highly predictable demand.
* **Highly Seasonal:**
  * *Profile:* Fourier Seasonal Model selected as the winning model; clear demand peaks during specific calendar months.
  * *Interpretation:* Demand is strictly tied to calendar events or weather patterns.
* **Erratic / Volatile:**
  * *Profile:* High demand volatility, WMAPE $> 30\%$, Gradient Boosted Trees often selected.
  * *Interpretation:* Demand is unpredictable, prone to sudden spikes or drops.

## 5. Recommendation Templates

When generating the final report recommendations, apply the following logic based on the SKU archetype:

* **For Stable Baseload SKUs:** > "Demand velocity for [SKU] is highly stable. We recommend optimizing for operational efficiency by establishing automated, large-batch replenishment cycles. Safety stock can be safely minimized to free up working capital without risking stockouts."
* **For Highly Seasonal SKUs:** > "Forecasts indicate strong seasonal adherence for [SKU]. Ensure procurement and warehouse capacity are aligned at least [Lead Time] days ahead of the forecasted peak. Taper replenishment orders sharply immediately following the peak to avoid excess post-season inventory."
* **For Erratic / Volatile SKUs:** > "Given the high volatility and elevated WMAPE for [SKU], maintaining a 95% service level requires heavily inflated safety stock, tying up capital. We recommend evaluating this SKU for potential rationalization, shifting to a make-to-order model, or accepting a lower target service level (e.g., 90%) to balance inventory holding costs."