import polars as pl
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

def load_staff_counts() -> pl.DataFrame:
    return pl.scan_parquet(DATA_DIR / "q1_staff_counts.parquet").collect()

def load_staff_assignments() -> pl.DataFrame:
    q2 = pl.scan_parquet(DATA_DIR / "q2_staff_assignments.parquet")
    
    return (
        q2.with_columns(
            pl.col("departure").cast(pl.Datetime)
        )
        .with_columns(
            pl.col("departure").dt.year().alias("year"),
            pl.col("departure").dt.month().alias("month")
        )
        .collect()
    )

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
def staff_global_kpis(counts_df: pl.DataFrame, assign_df: pl.DataFrame) -> dict:
    total_staff = counts_df["staff_count"].sum()
    
    # Distance and hours per employee
    emp_stats = (
        assign_df.lazy()
        .group_by("empno")
        .agg(
            pl.col("distance").sum().alias("total_distance"),
            pl.col("flight_minutes").sum().alias("total_minutes")
        )
        .collect()
    )
    
    avg_km = emp_stats["total_distance"].mean() if len(emp_stats) > 0 else 0
    avg_hours = (emp_stats["total_minutes"].mean() / 60.0) if len(emp_stats) > 0 else 0
    
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
def department_stats(counts_df: pl.DataFrame, assign_df: pl.DataFrame) -> pl.DataFrame:
    # Hours by department
    dept_hours = (
        assign_df.lazy()
        .group_by("department")
        .agg(
            (pl.col("flight_minutes").sum() / 60.0).alias("total_hours_required")
        )
        .collect()
    )
    
    return (
        counts_df.join(dept_hours, on="department", how="left")
        .sort("staff_count", descending=True)
    )

# --- Temporal Analysis ---
def flying_hours_over_time(assign_df: pl.DataFrame) -> pl.DataFrame:
    return (
        assign_df.lazy()
        .group_by("year", "month")
        .agg(
            (pl.col("flight_minutes").sum() / 60.0).alias("total_hours"),
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
def staff_utilisation(assign_df: pl.DataFrame) -> pl.DataFrame:
    base = (
        assign_df.lazy()
        .group_by("empno", "firstnme", "lastname", "department")
        .agg(
            pl.len().alias("total_flights"),
            (pl.col("flight_minutes").sum() / 60.0).alias("total_hours"),
            pl.col("route_code").n_unique().alias("unique_routes")
        )
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

