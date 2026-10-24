"""Step 1: download daily rainfall and temperature for the study area.

Source: NASA POWER (free, no account, no API key).
We use the API instead of scraping a website: it is stable, documented, and
gives clean numbers, so there is no HTML to break.

Run:  python 01_weather.py
Output: data/weather_daily.csv and data/weather_weekly.csv
"""
import os
import requests
import pandas as pd
import config

API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def parse_power(payload: dict) -> pd.DataFrame:
    """Turn a NASA POWER JSON response into a tidy daily DataFrame."""
    params = payload["properties"]["parameter"]
    df = pd.DataFrame(params)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.rename(columns={"PRECTOTCORR": "rain_mm", "T2M": "temp_c"})
    # NASA POWER uses -999 for missing values
    df = df.where(df > -900)
    return df


def to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Weekly rainfall total and mean temperature (weeks start on Monday)."""
    weekly = daily.resample("W-MON", label="left", closed="left").agg(
        {"rain_mm": "sum", "temp_c": "mean"}
    )
    weekly.index.name = "week_start"
    return weekly


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    params = {
        "parameters": "PRECTOTCORR,T2M",
        "community": "AG",
        "longitude": round(config.LON, 4),
        "latitude": round(config.LAT, 4),
        "start": config.START.replace("-", ""),
        "end": config.END.replace("-", ""),
        "format": "JSON",
    }
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    daily = parse_power(r.json())
    weekly = to_weekly(daily)
    daily.to_csv(f"{config.DATA_DIR}/weather_daily.csv")
    weekly.to_csv(f"{config.DATA_DIR}/weather_weekly.csv")
    print(f"Saved {len(daily)} daily rows and {len(weekly)} weekly rows.")
    print(f"Total rainfall in season: {daily['rain_mm'].sum():.0f} mm")


if __name__ == "__main__":
    main()
