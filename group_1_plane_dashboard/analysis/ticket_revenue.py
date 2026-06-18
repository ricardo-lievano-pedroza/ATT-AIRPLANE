import polars as pl
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def load_data() -> pl.DataFrame:
    tickets_agg = pl.read_parquet(DATA_DIR / "tickets_agg.parquet")
    airports = pl.read_parquet(DATA_DIR / "airports.parquet")

    return (
        tickets_agg.lazy()
        .join(
            airports.lazy().select(
                pl.col("iata_code").alias("origin"),
                pl.col("airport").alias("origin_airport"),
                pl.col("city").alias("origin_city"),
                pl.col("country").alias("origin_country"),
                pl.col("continent").alias("origin_continent"),
                pl.col("latitude").cast(pl.Float64).alias("lat"),
                pl.col("longitude").cast(pl.Float64).alias("lon"),
            ),
            on="origin",
            how="left",
        )
        .with_columns(
            pl.col("avg_airport_tax").cast(pl.Float64),
            pl.col("avg_local_tax").cast(pl.Float64),
            pl.col("avg_ticket_value").cast(pl.Float64),
            pl.col("total_revenue").cast(pl.Float64),
            pl.col("ticket_count").cast(pl.Int64),
        )
        .with_columns(
            (pl.col("avg_airport_tax") + pl.col("avg_local_tax")).alias("avg_total_tax"),
            (
                (pl.col("avg_airport_tax") + pl.col("avg_local_tax"))
                / pl.col("avg_ticket_value") * 100
            ).alias("avg_tax_pct"),
        )
        .sort("avg_tax_pct", descending=True)
        .collect()
    )


def filter_data(
    df: pl.DataFrame,
    continents: list[str],
    countries: list[str],
    tax_range: tuple[float, float],
) -> pl.DataFrame:
    return df.filter(
        pl.col("origin_continent").is_in(continents)
        & pl.col("origin_country").is_in(countries)
        & pl.col("avg_tax_pct").is_between(tax_range[0], tax_range[1])
    )
