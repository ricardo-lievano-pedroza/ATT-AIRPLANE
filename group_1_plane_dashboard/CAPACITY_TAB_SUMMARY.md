# Plane Capacity Tab - Implementation Summary

## Overview
A new **"Plane Capacity"** tab has been added to your Streamlit dashboard. This tab provides comprehensive visualization and analysis of aircraft seat occupancy and utilization across your entire fleet.

---

## What Was Changed

### 1. **Updated Tab Declaration** (Line 102)
```python
# OLD:
tab1, tab2, tab3 = st.tabs(["Revenue & Tax", "Staff Occupation", "Revenue Anlaysis"])

# NEW:
tab1, tab2, tab3, tab4 = st.tabs(["Revenue & Tax", "Staff Occupation", "Revenue Anlaysis", "Plane Capacity"])
```

### 2. **Added Capacity Data Loader Function** (Lines 90-100)
Added a new cached data loader that reads capacity data from the parquet file:
```python
@st.cache_data(show_spinner="Loading capacity data...")
def get_capacity_data() -> pl.DataFrame:
    """Load capacity data from parquet file"""
    try:
        df = pl.read_parquet(DATA_DIR / "capacity.parquet")
        if "date" in df.columns:
            df = df.with_columns(pl.col("date").str.to_date())
        return df
    except Exception as e:
        st.error(f"Error loading capacity data: {e}")
        return pl.DataFrame()
```

### 3. **Added Plane Capacity Tab Content** (Lines 793-900+)
A complete new tab with 3 main visualizations:

---

## The Three Visualizations

### **Visualization 1: Temporal Analysis - Capacity Over Time**
- **Breakdown by Week**: Line chart showing average capacity percentage across weeks
- **Breakdown by Month**: Bar chart with color gradient showing monthly occupancy trends
- **Breakdown by Day of Week**: Bar chart showing which days of the week have highest/lowest occupancy

**Type**: Multi-tab interface with line and bar charts
**Use Case**: Identify seasonal patterns, peak travel days, and cyclical demand

---

### **Visualization 2: Capacity by Flight ID**
- **Scatter Plot**: Shows each flight with occupancy percentage on Y-axis
  - Bubble size = number of observations
  - Color = occupancy percentage (Viridis scale)
  - Hover shows route ID, max/min capacity
- **Top 10 Table**: Lists top 10 flights by average occupancy

**Type**: Interactive scatter plot + data table
**Use Case**: Identify high-performing and underutilized flights, spot optimization opportunities

---

### **Visualization 3: Capacity by Route ID**
- **Horizontal Bar Chart**: Top 20 routes ranked by average capacity
  - Color gradient (RdYlGn) shows occupancy health
  - Hover shows number of flights and max capacity
  - Sorted from lowest to highest occupancy

**Type**: Horizontal bar chart
**Use Case**: Route-level performance analysis, identify routes needing capacity adjustments

---

## Key Features Added

### **Header Metrics** (4 KPIs)
- Average Occupancy Rate (%)
- Peak Occupancy (%)
- Flights Tracked
- Routes Covered

### **Summary Statistics Section**
- Count of flights with >90% occupancy
- Count of flights with <50% occupancy
- Total routes analyzed

### **Data Transformations**
The capacity data is enriched with temporal columns:
- `week`: ISO week number
- `month`: Month number
- `day_of_week`: Day of week (0=Monday, 6=Sunday)
- `year_month`: YYYY-MM format for grouping

---

## Expected Data Format

The `capacity.parquet` file should contain these columns:
| Column | Type | Description |
|--------|------|-------------|
| `flight_id` | string/int | Unique flight identifier |
| `route_id` | string/int | Route identifier |
| `date` | date | Flight date |
| `capacity_pct` | float | Occupancy percentage (0.0-1.0) |

---

## Integration Notes

✅ **No existing tabs were modified** - All three original tabs remain unchanged
✅ **Uses existing patterns** - Follows the same structure, styling, and caching as other tabs
✅ **Polars + Plotly** - Consistent with the dashboard's tech stack
✅ **Responsive design** - Works on desktop and mobile layouts

---

## How to Use

1. **Load the updated `app.py`** into your project
2. **Ensure `capacity.parquet`** is in the `data/` directory (or adjust `DATA_DIR` path)
3. **Run the dashboard**: `streamlit run app.py`
4. **Navigate to "Plane Capacity"** tab to see all visualizations

---

## Customization Options

You can easily customize:
- **Color scales** in `px.bar()` and `px.scatter()` by changing `color_continuous_scale` parameter
- **Number of routes displayed** (currently top 20) by changing `.head(20)` on the route visualization
- **Temporal aggregation** (currently week/month/day) by adding more tabs or changing grouping
- **Metric thresholds** (currently >90% and <50%) in the summary statistics section

---

## Performance Considerations

- Data is cached using `@st.cache_data` for fast loading on subsequent runs
- Polars operations are optimized for large datasets
- Plotly charts are interactive but lightweight

