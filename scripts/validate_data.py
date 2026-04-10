import pandas as pd
import numpy as np
import argparse
import json
import sys
import os

def profile_and_validate(df):
    """
    Profiles the dataset and validates against expected supply chain schema rules.
    Returns a dictionary containing the quality summary and any critical warnings.
    """
    quality_report = {
        "status": "PASS",
        "row_count": len(df),
        "column_count": len(df.columns),
        "warnings": [],
        "errors": [],
        "column_profiles": {}
    }

    # 1. Column Existence Check
    expected_columns = ['date', 'sku_id', 'category', 'sales_volume', 'unit_cost', 'lead_time_days']
    missing_cols = [col for col in expected_columns if col not in df.columns]
    if missing_cols:
        quality_report["status"] = "FAIL"
        quality_report["errors"].append(f"Missing required columns: {missing_cols}")
        return quality_report

    # 2. Duplicate Check
    duplicate_count = int(df.duplicated().sum())
    if duplicate_count > 0:
        quality_report["warnings"].append(f"Found {duplicate_count} duplicate rows.")

    # 3. Column Profiling & Validation
    for col in expected_columns:
        col_data = df[col]
        null_count = int(col_data.isnull().sum())
        null_pct = round((null_count / len(df)) * 100, 2)
        
        profile = {
            "dtype": str(col_data.dtype),
            "null_count": null_count,
            "null_percentage": null_pct
        }

        # Numeric Profiling & Constraints
        if pd.api.types.is_numeric_dtype(col_data):
            profile["min"] = float(col_data.min()) if not pd.isna(col_data.min()) else None
            profile["max"] = float(col_data.max()) if not pd.isna(col_data.max()) else None
            profile["mean"] = float(col_data.mean()) if not pd.isna(col_data.mean()) else None
            
            # Constraint: No negative sales or costs
            if col in ['sales_volume', 'unit_cost'] and profile["min"] is not None and profile["min"] < 0:
                quality_report["errors"].append(f"Column '{col}' contains negative values.")
                quality_report["status"] = "FAIL"
                
            # Constraint: Lead time must be >= 1
            if col == 'lead_time_days' and profile["min"] is not None and profile["min"] < 1:
                quality_report["errors"].append(f"Column '{col}' contains lead times < 1 day.")
                quality_report["status"] = "FAIL"

        # Categorical Profiling
        elif pd.api.types.is_object_dtype(col_data) or pd.api.types.is_string_dtype(col_data):
            profile["unique_values"] = int(col_data.nunique())

        # Date Profiling
        if col == 'date':
            try:
                df['date'] = pd.to_datetime(df['date'])
                profile["min_date"] = df['date'].min().strftime('%Y-%m-%d')
                profile["max_date"] = df['date'].max().strftime('%Y-%m-%d')
            except Exception as e:
                quality_report["errors"].append("Date column is not parseable.")
                quality_report["status"] = "FAIL"

        # Threshold rules
        if null_pct > 30.0:
            quality_report["errors"].append(f"Column '{col}' exceeds 30% null threshold ({null_pct}%).")
            quality_report["status"] = "FAIL"
        elif null_pct > 0:
            quality_report["warnings"].append(f"Column '{col}' has {null_pct}% null values. Imputation required.")

        quality_report["column_profiles"][col] = profile

    return quality_report

def main():
    """
    Main execution function. Accepts CLI arguments for input data and output JSON path.
    """
    parser = argparse.ArgumentParser(description="Validate and profile supply chain dataset.")
    parser.add_argument("--input", required=True, help="Path to the input CSV data file.")
    parser.add_argument("--output", required=True, help="Path to save the JSON data quality report.")
    args = parser.parse_args()

    try:
        # Load the dataset
        if not os.path.exists(args.input):
            raise FileNotFoundError(f"Input file not found at {args.input}")
            
        df = pd.read_csv(args.input)
        
        # Run profiling
        report = profile_and_validate(df)
        
        # Save structured output
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=4)
            
        print(f"Validation complete. Status: {report['status']}")
        print(f"Report saved to: {args.output}")
        
        # If the status is FAIL, exit with a non-zero code to halt the pipeline
        if report["status"] == "FAIL":
            sys.exit(1)
            
    except Exception as e:
        error_report = {
            "status": "CRITICAL_FAILURE",
            "error_message": str(e)
        }
        with open(args.output, 'w') as f:
            json.dump(error_report, f, indent=4)
        print(f"Critical execution error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()