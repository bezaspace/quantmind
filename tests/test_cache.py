import polars as pl


def test_cache_roundtrip(tmp_cache):
    df = pl.DataFrame(
        {
            "Datetime": ["2024-08-01", "2024-08-02"],
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [104.0, 105.0],
            "Volume": [1000, 2000],
        }
    ).with_columns(pl.col("Datetime").str.to_datetime().cast(pl.Datetime("ns")))

    tmp_cache.set("TEST", "RELIANCE", "day", None, None, df)
    cached = tmp_cache.get("TEST", "RELIANCE", "day", None, None)

    assert cached is not None
    assert len(cached) == 2
    assert list(cached.columns) == ["Datetime", "Open", "High", "Low", "Close", "Volume"]


def test_cache_has(tmp_cache):
    df = pl.DataFrame({
        "Datetime": ["2024-08-01"],
        "Open": [100.0],
        "High": [105.0],
        "Low": [99.0],
        "Close": [104.0],
        "Volume": [1000],
    }).with_columns(pl.col("Datetime").str.to_datetime().cast(pl.Datetime("ns")))

    tmp_cache.set("TEST", "ABC", "day", None, None, df)
    assert tmp_cache.has("TEST", "ABC", "day", None, None)
    assert not tmp_cache.has("TEST", "ABC", "day", None, "2024-08-02")
