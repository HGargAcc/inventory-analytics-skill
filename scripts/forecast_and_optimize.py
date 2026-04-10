#!/usr/bin/env python3
"""Stage 2 & 3 – Feature Engineering, Multi-Algorithm Forecasting & Inventory Optimization.

Uses GradientBoostingRegressor (sklearn) as the tree-based challenger
and a Fourier+Trend seasonal model as the seasonality-based challenger
"""

import argparse, json, warnings
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge

warnings.filterwarnings("ignore")

# ── helpers ──────────────────────────────────────────────────────────────────

def wmape(actual, predicted):
    actual, predicted = np.array(actual, dtype=float), np.array(predicted, dtype=float)
    mask = actual != 0
    if mask.sum() == 0:
        return 1.0
    return float(np.sum(np.abs(actual[mask] - predicted[mask])) / np.sum(np.abs(actual[mask])))


def build_features(series: pd.DataFrame) -> pd.DataFrame:
    df = series.copy().sort_values("date").set_index("date").asfreq("D")
    df["sales_volume"] = df["sales_volume"].interpolate(method="linear")
    df["lead_time_days"] = df["lead_time_days"].interpolate(method="linear")

    for lag in [1, 7, 14, 28]:
        df[f"lag_{lag}"] = df["sales_volume"].shift(lag)
    for win in [7, 14, 28]:
        df[f"roll_mean_{win}"] = df["sales_volume"].shift(1).rolling(win).mean()
        df[f"roll_std_{win}"] = df["sales_volume"].shift(1).rolling(win).std()

    df["dow"] = df.index.dayofweek
    df["month"] = df.index.month
    df["day_of_year"] = df.index.dayofyear
    df["week_of_year"] = df.index.isocalendar().week.astype(int)
    df = df.dropna()
    return df


def run_gbr(train_df, test_df, feature_cols, target="sales_volume"):
    model = GradientBoostingRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.05,
        subsample=0.8, random_state=42
    )
    model.fit(train_df[feature_cols], train_df[target])
    preds = model.predict(test_df[feature_cols])
    preds = np.maximum(preds, 0)
    score = wmape(test_df[target].values, preds)
    return score, preds


def run_fourier_seasonal(sku_daily: pd.DataFrame, holdout_days: int):
    """Fourier-based seasonal decomposition model (Prophet stand-in).
    Uses yearly + weekly Fourier terms + linear trend, fit with Ridge regression.
    """
    pdf = sku_daily[["date", "sales_volume"]].copy().sort_values("date").reset_index(drop=True)
    pdf["sales_volume"] = pdf["sales_volume"].interpolate(method="linear").ffill().bfill()
    pdf["t"] = (pdf["date"] - pdf["date"].min()).dt.days
    cutoff_date = pdf["date"].max() - pd.Timedelta(days=holdout_days)
    train = pdf[pdf["date"] <= cutoff_date].copy()
    test = pdf[pdf["date"] > cutoff_date].copy()

    def fourier_features(t_vals):
        X = np.column_stack([t_vals, np.ones(len(t_vals))])
        for period in [365.25, 7]:
            for k in range(1, 4):
                X = np.column_stack([
                    X,
                    np.sin(2 * np.pi * k * t_vals / period),
                    np.cos(2 * np.pi * k * t_vals / period),
                ])
        return X

    X_train = fourier_features(train["t"].values)
    X_test = fourier_features(test["t"].values)

    model = Ridge(alpha=1.0)
    model.fit(X_train, train["sales_volume"].values)
    preds = model.predict(X_test)
    preds = np.maximum(preds, 0)
    score = wmape(test["sales_volume"].values, preds)
    return score, preds


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--holdout_days", type=int, default=30)
    parser.add_argument("--service_level_z", type=float, default=1.65)
    args = parser.parse_args()

    df = pd.read_csv(args.input, parse_dates=["date"])
    skus = sorted(df["sku_id"].unique())

    results = {
        "config": {"holdout_days": args.holdout_days, "service_level_z": args.service_level_z},
        "sku_results": []
    }

    sample = build_features(df[df["sku_id"] == skus[0]])
    feature_cols = [c for c in sample.columns
                    if c not in ["sales_volume", "unit_cost", "category", "sku_id", "lead_time_days"]]

    for sku in skus:
        print(f"Processing {sku} ...")
        sku_raw = df[df["sku_id"] == sku].copy()
        category = sku_raw["category"].iloc[0]
        unit_cost = float(sku_raw["unit_cost"].iloc[0])

        featured = build_features(sku_raw)
        cutoff = featured.index.max() - pd.Timedelta(days=args.holdout_days)
        train = featured[featured.index <= cutoff]
        test = featured[featured.index > cutoff]

        xgb_wmape, _ = run_gbr(train, test, feature_cols)
        prophet_wmape, _ = run_fourier_seasonal(sku_raw, args.holdout_days)

        if prophet_wmape <= xgb_wmape:
            winning = "Fourier Seasonal"
            winning_wmape = prophet_wmape
        else:
            winning = "Gradient Boosted Trees"
            winning_wmape = xgb_wmape

        Z = args.service_level_z
        avg_daily_demand = float(sku_raw["sales_volume"].mean())
        std_daily_demand = float(sku_raw["sales_volume"].std())
        avg_lead_time = float(sku_raw["lead_time_days"].mean())
        std_lead_time = float(sku_raw["lead_time_days"].std())

        safety_stock = Z * np.sqrt(
            (avg_lead_time * std_daily_demand ** 2) +
            (avg_daily_demand ** 2 * std_lead_time ** 2)
        )
        reorder_point = (avg_daily_demand * avg_lead_time) + safety_stock

        cv = std_daily_demand / avg_daily_demand if avg_daily_demand else 0

        results["sku_results"].append({
            "sku_id": sku,
            "category": category,
            "unit_cost": unit_cost,
            "avg_daily_demand": round(avg_daily_demand, 2),
            "std_daily_demand": round(std_daily_demand, 2),
            "cv_demand": round(cv, 4),
            "avg_lead_time_days": round(avg_lead_time, 2),
            "std_lead_time_days": round(std_lead_time, 2),
            "gbr_wmape": round(xgb_wmape, 4),
            "fourier_wmape": round(prophet_wmape, 4),
            "winning_algorithm": winning,
            "winning_wmape": round(winning_wmape, 4),
            "recommended_safety_stock": round(safety_stock, 0),
            "reorder_point": round(reorder_point, 0),
            "service_level_z": Z,
        })

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
