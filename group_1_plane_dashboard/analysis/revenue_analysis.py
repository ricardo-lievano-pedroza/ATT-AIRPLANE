from datetime import date, datetime
from pathlib import Path

import polars as pl


DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_START = date(2020, 1, 1)
DEFAULT_END = date(2025, 12, 31)


def _parse_date(value: str | date | datetime, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def _date_range(start: str | date | datetime, end: str | date | datetime) -> tuple[date, date]:
    start_date = _parse_date(start, DEFAULT_START)
    end_date = _parse_date(end, DEFAULT_END)

    if start_date > end_date:
        return end_date, start_date

    return start_date, end_date


def filter_by_date_range(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    start_date, end_date = _date_range(start, end)

    return df.filter(
        pl.col("year_month").is_between(start_date, end_date, closed="both")
    )


def _normalize_columns(df: pl.DataFrame) -> pl.DataFrame:
    renamed = {column: column.lower().strip() for column in df.columns}
    df = df.rename(renamed)

    if "route_code" in df.columns and "route" not in df.columns:
        df = df.rename({"route_code": "route"})

    month_dtype = df.schema.get("month")
    if month_dtype == pl.Date:
        month_expr = pl.col("month")
    elif month_dtype in (pl.Datetime, pl.Datetime("ms"), pl.Datetime("us"), pl.Datetime("ns")):
        month_expr = pl.col("month").dt.date()
    else:
        month_expr = pl.col("month").cast(pl.Date, strict=False)

    return df.select(
        pl.col("year").cast(pl.Int32).alias("year"),
        month_expr.alias("year_month"),
        pl.col("continent").cast(pl.Categorical).alias("continent"),
        pl.col("country").cast(pl.Categorical).alias("country"),
        pl.col("city").cast(pl.Categorical).alias("city"),
        pl.col("route").cast(pl.Categorical).alias("route"),
        pl.col("origin").cast(pl.Categorical).alias("origin"),
        pl.col("destination").cast(pl.Categorical).alias("destination"),
        pl.col("destination_continent").cast(pl.Categorical).alias("destination_continent"),
        pl.col("destination_conutry").cast(pl.Categorical).alias("destination_country"),
        pl.col("destination_city").cast(pl.Categorical).alias("destination_city"),
        pl.col("class").cast(pl.Categorical).alias("class"),
        pl.col("revenue").cast(pl.Float64).alias("revenue"),
    )


def load_revenue_data() -> pl.DataFrame:
    revenue = pl.read_parquet(DATA_DIR / "revenue.parquet")
    return _normalize_columns(revenue)


def compute_revenue_dashboard_metrics(df: pl.DataFrame) -> dict:
    """Compute every aggregate the Revenue tab needs from a single shared lazy
    query, so Polars scans the (potentially near-full) filtered table once
    instead of once per metric."""
    lf = df.lazy()

    total_lazy = lf.select(pl.col("revenue").sum().fill_null(0).alias("total_revenue"))
    route_lazy = (
        lf.group_by("route", "city", "country", "destination_city", "destination_country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
        .limit(1)
    )
    city_lazy = (
        lf.group_by("continent", "country", "city")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
        .limit(1)
    )
    trend_lazy = (
        lf.group_by("year_month")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("year_month")
    )
    class_lazy = (
        lf.group_by("class")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
    )
    country_lazy = (
        lf.group_by("country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
    )

    total_df, route_df, city_df, trend_df, class_df, country_df = pl.collect_all(
        [total_lazy, route_lazy, city_lazy, trend_lazy, class_lazy, country_lazy]
    )

    return {
        "total_revenue": total_df.item(),
        "top_route": route_df.row(0, named=True) if route_df.height else {},
        "top_city": city_df.row(0, named=True) if city_df.height else {},
        "trend_df": trend_df,
        "class_df": class_df,
        "country_df": country_df,
    }



