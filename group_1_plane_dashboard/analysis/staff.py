import polars as pl
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_staff_flights() -> pl.DataFrame:
    """Load raw staff-flight assignment fact table and derive flight_hours."""
    return (
        pl.scan_parquet(DATA_DIR / "staff_flights.parquet")        
        .with_columns(
            pl.col("empno").cast(pl.Int64),
            pl.col("distance").cast(pl.Float64),
            pl.col("flight_minutes").cast(pl.Float64),
            pl.col("departure").cast(pl.Datetime),
        )
        .with_columns(
            (pl.col("flight_minutes") / 60.0).alias("flight_hours"),
        )
        .collect()
    )


def load_crew_gaps() -> pl.DataFrame:
    """Load route-month crew gap table."""
    return (
        pl.scan_parquet(DATA_DIR / "crew_gaps.parquet")
        .with_columns(
            pl.col("total_flights").cast(pl.Int64),
            pl.col("total_required_crew").cast(pl.Int64),
            pl.col("total_actual_crew").cast(pl.Int64),
            pl.col("total_crew_gap").cast(pl.Int64),
            pl.col("year").cast(pl.Int32),
            pl.col("month").cast(pl.Int32),
        )
        .collect()
    )


def staff_utilisation(df: pl.DataFrame) -> pl.DataFrame:
    """
    Per-employee summary: total flights, total hours, unique routes.
    Flags employees above the 90th percentile (overused) or below the 10th (underused).
    """
    base = (
        df.lazy()
        .group_by("empno", "firstnme", "lastname", "division", "department")
        .agg(
            pl.len().alias("total_flights"),
            pl.col("flight_hours").sum().alias("total_hours"),
            pl.col("route_code").n_unique().alias("unique_routes"),
        )
        .sort("total_hours", descending=True)
        .collect()
    )

    p90 = float(base["total_hours"].quantile(0.90))
    p10 = float(base["total_hours"].quantile(0.10))

    return base.with_columns(
        (pl.col("total_hours") >= p90).alias("is_overused"),
        (pl.col("total_hours") <= p10).alias("is_underused"),
        pl.lit(p90).alias("p90_threshold"),
        pl.lit(p10).alias("p10_threshold"),
    )


def occupation_by_route(df: pl.DataFrame) -> pl.DataFrame:
    """
    Route-level staff occupation: how many unique staff, total assignments,
    crew-hours, and averages per staff member.
    """
    return (
        df.lazy()
        .group_by("origin", "destination")
        .agg(
            pl.col("empno").n_unique().alias("unique_staff"),
            pl.len().alias("total_assignments"),
            pl.col("flight_hours").sum().alias("total_crew_hours"),
            pl.col("departure").n_unique().alias("total_flights"),
        )
        .with_columns(
            (pl.col("total_assignments") / pl.col("unique_staff")).alias("avg_flights_per_staff"),
            (pl.col("total_crew_hours") / pl.col("unique_staff")).alias("avg_hours_per_staff"),
            (pl.col("origin") + " → " + pl.col("destination")).alias("route_label"),
        )
        .sort("avg_hours_per_staff", descending=True)
        .collect()
    )


def understaffing_by_route(gaps_df: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate crew gaps by route (across all months).
    gap_rate = proportion of flights that were understaffed.
    A flight is understaffed when total_crew_gap > 0 for that route-month.
    """
    return (
        gaps_df.lazy()
        .with_columns(
            (pl.col("total_crew_gap") > 0).cast(pl.Int64).alias("months_understaffed"),
        )
        .group_by("route_code", "origin", "destination")
        .agg(
            pl.col("total_flights").sum().alias("total_flights"),
            pl.col("total_required_crew").sum().alias("total_required_crew"),
            pl.col("total_actual_crew").sum().alias("total_actual_crew"),
            pl.col("total_crew_gap").sum().alias("total_crew_gap"),
            pl.col("months_understaffed").sum().alias("months_understaffed"),
        )
        .with_columns(
            (pl.col("origin") + " → " + pl.col("destination")).alias("route_label"),
            (
                pl.col("total_crew_gap") / pl.col("total_required_crew") * 100
            ).alias("gap_rate_pct"),
        )
        .filter(pl.col("total_crew_gap") > 0)
        .sort("total_crew_gap", descending=True)
        .collect()
    )


def temporal_understaffing(gaps_df: pl.DataFrame) -> pl.DataFrame:
    """Monthly trend of crew gaps across all routes — useful for spotting peak periods."""
    return (
        gaps_df.lazy()
        .group_by("year", "month")
        .agg(
            pl.col("total_crew_gap").sum().alias("total_crew_gap"),
            pl.col("total_flights").sum().alias("total_flights"),
            pl.col("total_actual_crew").sum().alias("total_actual_crew"),
            pl.col("total_required_crew").sum().alias("total_required_crew"),
        )
        .with_columns(
            (
                pl.col("year").cast(pl.Utf8) + "-"
                + pl.col("month").cast(pl.Utf8).str.zfill(2)
            ).alias("period"),
        )
        .sort("year", "month")
        .collect()
    )
