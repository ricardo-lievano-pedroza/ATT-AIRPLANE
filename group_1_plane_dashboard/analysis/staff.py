import polars as pl
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

def load_staff_counts() -> pl.DataFrame:
    return pl.scan_parquet(DATA_DIR / "q1_staff_counts.parquet").collect()

def load_staff_employee_dim() -> pl.DataFrame:
    return pl.scan_parquet(DATA_DIR / "staff_employee_dim.parquet").collect()

def load_staff_monthly_agg() -> pl.DataFrame:
    return pl.scan_parquet(DATA_DIR / "staff_monthly_agg.parquet").collect()

def load_staff_usage() -> pl.DataFrame:
    q3 = pl.scan_parquet(DATA_DIR / "q3_staff_usage.parquet")
    return (
        q3.with_columns(
            pl.col("required_crew").cast(pl.Int64),
            pl.col("used_crew").cast(pl.Int64)
        )
        .collect()
    )

# --- KPIs ---
def staff_global_kpis(counts_df: pl.DataFrame, monthly_df: pl.DataFrame) -> dict:
    total_staff = counts_df["staff_count"].sum()

    # Distance and hours per employee
    emp_stats = (
        monthly_df.lazy()
        .group_by("empno")
        .agg(
            pl.col("total_distance").sum(),
            pl.col("total_minutes").sum()
        )
        .collect()
    )

    # monthly_df is already bucketed to year/month, so the span is derived
    # from the number of distinct months rather than exact departure timestamps
    years = 1.0
    if len(monthly_df) > 0:
        ym = monthly_df.select((pl.col("year") * 12 + pl.col("month")).alias("ym"))
        span_months = ym["ym"].max() - ym["ym"].min() + 1
        years = span_months / 12.0
        if years <= 0:
            years = 1.0

    avg_km = (emp_stats["total_distance"].mean() / years) if len(emp_stats) > 0 else 0
    avg_hours = (emp_stats["total_minutes"].mean() / 60.0 / years) if len(emp_stats) > 0 else 0

    return {
        "total_staff": total_staff,
        "avg_km_per_staff": avg_km,
        "avg_hours_per_staff": avg_hours
    }

# --- Aircraft Requirements ---
def aircraft_staff_requirements(usage_df: pl.DataFrame) -> pl.DataFrame:
    return (
        usage_df.lazy()
        .group_by("airplane_model")
        .agg(
            pl.col("required_crew").mean().alias("avg_required_crew"),
            pl.col("used_crew").mean().alias("avg_used_crew")
        )
        .with_columns(
            (pl.col("avg_used_crew") - pl.col("avg_required_crew")).alias("crew_difference")
        )
        .sort("avg_required_crew", descending=True)
        .collect()
    )

# --- Route Needs ---
def route_staff_needs(usage_df: pl.DataFrame) -> pl.DataFrame:
    group_cols = ["route_code"]
    has_orig_dest = "origin" in usage_df.columns and "destination" in usage_df.columns
    if has_orig_dest:
        group_cols.extend(["origin", "destination"])

    res = (
        usage_df.lazy()
        .group_by(group_cols)
        .agg(
            pl.len().alias("total_flights"),
            pl.col("required_crew").sum().alias("total_required_crew"),
            pl.col("used_crew").sum().alias("total_actual_crew")
        )
        .with_columns(
            (pl.col("total_required_crew") - pl.col("total_actual_crew")).alias("crew_gap")
        )
    )

    if has_orig_dest:
        res = res.with_columns((pl.col("origin") + " → " + pl.col("destination")).alias("route_label"))
    else:
        res = res.with_columns(pl.col("route_code").alias("route_label"))

    return res.sort("crew_gap", descending=True).collect()

# --- Department Analysis ---
def department_stats(counts_df: pl.DataFrame, employee_dim_df: pl.DataFrame, monthly_df: pl.DataFrame) -> pl.DataFrame:
    # Hours by department
    dept_hours = (
        monthly_df.lazy()
        .group_by("empno")
        .agg(pl.col("total_minutes").sum())
        .join(employee_dim_df.lazy().select(["empno", "department"]), on="empno", how="left")
        .group_by("department")
        .agg((pl.col("total_minutes").sum() / 60.0).alias("total_hours_required"))
        .collect()
    )

    return (
        counts_df.join(dept_hours, on="department", how="left")
        .sort("staff_count", descending=True)
    )

# --- Temporal Analysis ---
def flying_hours_over_time(monthly_df: pl.DataFrame) -> pl.DataFrame:
    return (
        monthly_df.lazy()
        .group_by("year", "month")
        .agg(
            (pl.col("total_minutes").sum() / 60.0).alias("total_hours"),
            pl.col("empno").n_unique().alias("unique_staff")
        )
        .with_columns(
            (pl.col("total_hours") / pl.col("unique_staff")).alias("avg_hours_per_staff"),
            (
                pl.col("year").cast(pl.Utf8) + "-" + pl.col("month").cast(pl.Utf8).str.zfill(2)
            ).alias("period")
        )
        .sort("year", "month")
        .collect()
    )

# --- Vacations / Overwork ---
def staff_utilisation(monthly_df: pl.DataFrame, employee_dim_df: pl.DataFrame) -> pl.DataFrame:
    base = (
        monthly_df.lazy()
        .group_by("empno")
        .agg(
            pl.col("total_flights").sum(),
            (pl.col("total_minutes").sum() / 60.0).alias("total_hours"),
        )
        .join(employee_dim_df.lazy(), on="empno", how="left")
        .select(["empno", "firstnme", "lastname", "department", "total_flights", "total_hours"])
        .sort("total_hours", descending=True)
        .collect()
    )

    if len(base) == 0:
        return base

    p90 = float(base["total_hours"].quantile(0.90))
    p10 = float(base["total_hours"].quantile(0.10))

    return base.with_columns(
        (pl.col("total_hours") >= p90).alias("is_overused"),
        (pl.col("total_hours") <= p10).alias("is_underused"),
        pl.lit(p90).alias("p90_threshold"),
        pl.lit(p10).alias("p10_threshold"),
    )

