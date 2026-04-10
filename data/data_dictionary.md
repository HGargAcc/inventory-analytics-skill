# Data Dictionary: Enterprise Inventory Forecasting Dataset

## 1. Overview
This dataset contains daily time-series supply chain records extracted for demand planning, safety stock calculation, and inventory optimization. It captures daily sales volume, historical lead times, and unit costs across a portfolio of FMCG SKUs.

* **Date Range:** January 1, 2023, to March 31, 2026.
* **Granularity:** Daily, SKU-level.

## 2. Column Definitions

| Column Name | Data Type | Description | Validation Constraints |
| :--- | :--- | :--- | :--- |
| `date` | Date (YYYY-MM-DD) | The specific calendar date of the recorded metrics. | Continuous daily sequence expected. |
| `sku_id` | String | Unique alphanumeric identifier for the product. | Cannot be null. |
| `category` | String | The overarching supply chain categorization (e.g., 'Ambient Grocery', 'Chilled Proteins'). | Cannot be null. |
| `sales_volume` | Float/Integer | The total number of units sold on the given date. | Must be $\ge 0$. |
| `unit_cost` | Float | The standard cost to procure or produce one unit of the SKU (in USD). | Must be $> 0$. |
| `lead_time_days` | Integer | The recorded delivery lead time (in days) for orders placed on this date. | Must be $\ge 1$. |