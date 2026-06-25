from datetime import date, datetime
from pathlib import Path

import polars as pl


DATA_DIR = Path(__file__).parent / "data"
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


def _filter_by_date_range(
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
        pl.col("year").cast(pl.Int64).alias("year"),
        month_expr.alias("year_month"),
        pl.col("continent").cast(pl.Utf8).alias("continent"),
        pl.col("country").cast(pl.Utf8).alias("country"),
        pl.col("city").cast(pl.Utf8).alias("city"),
        pl.col("route").cast(pl.Utf8).alias("route"),
        pl.col("origin").cast(pl.Utf8).alias("origin"),
        pl.col("destination").cast(pl.Utf8).alias("destination"),
        pl.col("destination_continent").cast(pl.Utf8).alias("destination_continent"),
        pl.col("destination_conutry").cast(pl.Utf8).alias("destination_country"),
        pl.col("destination_city").cast(pl.Utf8).alias("destination_city"),
        pl.col("class").cast(pl.Utf8).alias("class"),
        pl.col("revenue").cast(pl.Float64).alias("revenue"),
    )


def load_revenue_data() -> pl.DataFrame:
    revenue = pl.read_parquet(DATA_DIR / "revenue.parquet")
    return _normalize_columns(revenue)


def total_revenue_per_range(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> float:
    return (
        _filter_by_date_range(df, start, end)
        .select(pl.col("revenue").sum().fill_null(0).alias("total_revenue"))
        .item()
    )


def most_profitable_outgoing_route(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    return (
        _filter_by_date_range(df, start, end)
        .group_by("route","city","country","destination_city","destination_country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
        .limit(1)
    )


def most_revenue_perceived(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    return (
        _filter_by_date_range(df, start, end)
        .group_by("continent", "country", "city")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
        .limit(1)
    )


def revenue_trend_analysis(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    return (
        _filter_by_date_range(df, start, end)
        .group_by("year_month")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("year_month")
    )


def revenue_class_analysis(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    return (
        _filter_by_date_range(df, start, end)
        .group_by("class")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
    )


def revenue_per_country(
    df: pl.DataFrame,
    start: str | date | datetime = DEFAULT_START,
    end: str | date | datetime = DEFAULT_END,
) -> pl.DataFrame:
    return (
        _filter_by_date_range(df, start, end)
        .group_by("country")
        .agg(pl.col("revenue").sum().alias("total_revenue"))
        .sort("total_revenue", descending=True)
    )



