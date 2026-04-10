#!/usr/bin/env python3
"""Synthetic Data Generator for Inventory Optimization Skill.

Generates realistic FMCG supply-chain datasets with controllable properties:
- Trend, seasonality, noise, and lead-time variation per SKU
- Optional data-quality defects (nulls, negatives, missing columns) for failure testing

Usage examples:
    # Generate a clean 15-SKU dataset (Jan 2024 – Mar 2026)
    python scripts/generate_synthetic_data.py --output data/dataset_run2.csv --seed 99 --n_skus 15

    # Generate a deliberately bad dataset for failure-scenario testing
    python scripts/generate_synthetic_data.py --output data/bad_data.csv --seed 42 --inject_bad_data
"""

import argparse
import numpy as np
import pandas as pd


# ── SKU catalogue ─────────────────────────────────────────────────────────────
# Each tuple: (sku_id, category, base_demand, unit_cost, base_lead_time,
#              seasonality_type, noise_level)

CATALOGUE_A = [
    ("SKU_101_CANNED_CHICKEN",   "Ambient Proteins",  500, 2.50, 12, "flat",     0.10),
    ("SKU_102_PEANUT_BUTTER",    "Ambient Grocery",   800, 3.20, 10, "flat",     0.08),
    ("SKU_103_WHITE_RICE_5KG",   "Ambient Grocery",  1200, 5.50, 18, "flat",     0.12),
    ("SKU_104_CANNED_BEANS",     "Ambient Grocery",   650, 1.10, 13, "flat",     0.09),
    ("SKU_105_PASTA_500G",       "Ambient Grocery",  1500, 1.50, 11, "flat",     0.07),
    ("SKU_201_BBQ_SAUCE",        "Condiments",        250, 2.80,  8, "summer",   0.15),
    ("SKU_202_HOT_DOGS_8PK",     "Chilled Proteins",  350, 4.50,  5, "summer",   0.20),
    ("SKU_203_CHARCOAL_BAG",     "Outdoor/Seasonal",  200, 8.99, 26, "summer",   0.25),
    ("SKU_204_LEMONADE_MIX",     "Beverages",         300, 3.00, 11, "summer",   0.18),
    ("SKU_205_SUNSCREEN_SPF50",  "Health & Beauty",   150, 9.50, 19, "summer",   0.30),
    ("SKU_301_WHOLE_TURKEY",     "Frozen Proteins",   100,22.00, 36, "holiday",  0.35),
    ("SKU_302_CRANBERRY_SAUCE",  "Ambient Grocery",    80, 1.80, 17, "holiday",  0.30),
    ("SKU_303_BAKING_CHOCOLATE", "Baking Needs",      200, 4.20, 11, "holiday",  0.22),
    ("SKU_304_EGGNOG_1L",        "Chilled Dairy",     120, 3.50,  3, "holiday",  0.40),
    ("SKU_305_GIFT_CHOCOLATE_BOX","Confectionery",    180,15.00, 19, "holiday",  0.28),
    ("SKU_401_SPICY_SNACK_MIX",  "Snacks",           270, 1.75,  7, "trending", 0.15),
    ("SKU_402_PROTEIN_BAR_VANILLA","Health & Beauty", 340, 2.10, 21, "trending", 0.12),
    ("SKU_403_ENERGY_DRINK_BERRY","Beverages",        620, 1.50,  8, "trending", 0.10),
    ("SKU_404_KETO_CRACKERS",    "Snacks",            190, 4.00, 12, "erratic",  0.45),
    ("SKU_405_LIMITED_EDITION_CHIPS","Snacks",        250, 1.99,  8, "erratic",  0.50),
]

CATALOGUE_B = [
    ("SKU_501_ORGANIC_MILK_1L",  "Chilled Dairy",     900, 2.80,  4, "flat",     0.08),
    ("SKU_502_ALMOND_BUTTER",    "Ambient Grocery",   400, 6.50, 14, "flat",     0.10),
    ("SKU_503_SPARKLING_WATER",  "Beverages",        1100, 0.90,  7, "summer",   0.12),
    ("SKU_504_ICE_CREAM_TUB",   "Frozen Desserts",   450, 5.00,  6, "summer",   0.25),
    ("SKU_505_GRILLING_SPICE",   "Condiments",        180, 3.50, 10, "summer",   0.20),
    ("SKU_506_FROZEN_PIZZA",     "Frozen Meals",      700, 4.20,  8, "flat",     0.11),
    ("SKU_507_CINNAMON_ROLLS",   "Baking Needs",      250, 3.80, 12, "holiday",  0.30),
    ("SKU_508_PUMPKIN_SPICE_MIX","Beverages",         100, 4.50, 15, "holiday",  0.40),
    ("SKU_509_CANDY_CANE_PKG",   "Confectionery",     150,12.00, 20, "holiday",  0.35),
    ("SKU_510_PLANT_PROTEIN_PWD","Health & Beauty",   500, 8.00, 18, "trending", 0.14),
    ("SKU_511_KOMBUCHA_GINGER",  "Beverages",         350, 3.20,  6, "trending", 0.16),
    ("SKU_512_OATMEAL_CUPS",     "Ambient Grocery",   600, 1.60,  9, "flat",     0.09),
    ("SKU_513_DRIED_MANGO",      "Snacks",            220, 5.50, 11, "erratic",  0.42),
    ("SKU_514_INSTANT_RAMEN_12PK","Ambient Grocery",  850, 3.00, 13, "trending", 0.10),
    ("SKU_515_COCONUT_WATER",    "Beverages",         480, 2.20,  7, "summer",   0.15),
]


def _seasonal_multiplier(doy, stype):
    """Return a multiplicative seasonal factor for a given day-of-year."""
    if stype == "flat":
        return 1.0
    elif stype == "summer":
        # Peak Jun-Aug (doy 150-240)
        return 1.0 + 2.5 * np.exp(-0.5 * ((doy - 195) / 30) ** 2)
    elif stype == "holiday":
        # Peak Nov-Dec (doy 305-355)
        return 1.0 + 4.0 * np.exp(-0.5 * ((doy - 340) / 20) ** 2)
    elif stype == "trending":
        return 1.0   # trend handled separately
    elif stype == "erratic":
        return 1.0   # pure noise
    return 1.0


def generate_dataset(catalogue, start_date, end_date, seed, n_skus=None):
    """Generate a clean synthetic inventory dataset."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start_date, end_date, freq="D")

    if n_skus and n_skus < len(catalogue):
        catalogue = catalogue[:n_skus]

    rows = []
    for sku_id, category, base_demand, unit_cost, base_lt, stype, noise in catalogue:
        trend_slope = rng.uniform(-0.05, 0.15) if stype == "trending" else rng.uniform(-0.02, 0.02)
        for i, d in enumerate(dates):
            doy = d.dayofyear
            dow = d.dayofweek

            seasonal = _seasonal_multiplier(doy, stype)
            trend = 1.0 + trend_slope * (i / len(dates))
            dow_effect = 1.05 if dow < 5 else 0.85
            random_noise = rng.normal(1.0, noise)

            demand = base_demand * seasonal * trend * dow_effect * random_noise
            if stype == "erratic":
                # Occasional spikes
                if rng.random() < 0.03:
                    demand *= rng.uniform(2.0, 4.0)

            demand = max(0.0, round(demand, 1))

            lt_variation = max(1, round(base_lt + rng.normal(0, base_lt * 0.15)))

            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "sku_id": sku_id,
                "category": category,
                "sales_volume": demand,
                "unit_cost": unit_cost,
                "lead_time_days": lt_variation,
            })

    return pd.DataFrame(rows)


def inject_defects(df, seed):
    """Inject data-quality defects for failure-scenario testing."""
    rng = np.random.RandomState(seed)
    df = df.copy()

    # 1. Inject ~40% nulls in sales_volume (should trigger >30% threshold)
    null_mask = rng.random(len(df)) < 0.40
    df.loc[null_mask, "sales_volume"] = np.nan

    # 2. Inject negative values in unit_cost
    neg_mask = rng.random(len(df)) < 0.05
    df.loc[neg_mask, "unit_cost"] = -1 * df.loc[neg_mask, "unit_cost"]

    # 3. Inject lead_time_days = 0 (violates >= 1 constraint)
    zero_lt = rng.random(len(df)) < 0.03
    df.loc[zero_lt, "lead_time_days"] = 0

    return df


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic inventory data.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--n_skus", type=int, default=None, help="Limit number of SKUs.")
    parser.add_argument("--catalogue", choices=["A", "B"], default="A",
                        help="SKU catalogue to use (A=original 20 SKUs, B=alternative 15 SKUs).")
    parser.add_argument("--start_date", default="2023-01-01", help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end_date", default="2026-03-31", help="End date (YYYY-MM-DD).")
    parser.add_argument("--inject_bad_data", action="store_true",
                        help="Inject data-quality defects for failure testing.")
    args = parser.parse_args()

    cat = CATALOGUE_A if args.catalogue == "A" else CATALOGUE_B
    df = generate_dataset(cat, args.start_date, args.end_date, args.seed, args.n_skus)

    if args.inject_bad_data:
        df = inject_defects(df, args.seed)
        print(f"[WARNING] Bad data injected: ~40% nulls in sales_volume, negative costs, zero lead times.")

    df.to_csv(args.output, index=False)
    print(f"Dataset generated: {len(df)} rows, {df['sku_id'].nunique()} SKUs → {args.output}")


if __name__ == "__main__":
    main()
