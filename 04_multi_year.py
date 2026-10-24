"""Step 4: repeat the NDVI download for every season, then compute season metrics.

Why: one season gives one point. To compare satellite greenness with yield you need
many seasons, so each season (2024L, 2024S and so on) becomes one point on a scatter plot.
L = long rains (Mar to Aug), S = short rains (Oct to the following Feb); see config.py.

Run:  python 04_multi_year.py      (about 3 to 10 minutes per season; safe to stop and restart,
                                    finished seasons are skipped)
Output: data/ndvi_<season>.csv for each season, and data/season_metrics.csv

If you change BBOX in config.py, delete the data/ndvi_*.csv files first, otherwise
old results from the previous box would be reused.
"""
import importlib
import os
import time
import pandas as pd
from pystac_client import Client
import config
import metrics

ndvi_mod = importlib.import_module("02_ndvi")  # reuse scene_ndvi() from step 2


MAX_FAILED_OK = 2  # a season is saved if at most this many scenes failed to download


def run_season(catalog, season_id: str):
    """Return (DataFrame of observations, number of scenes that failed to download)."""
    start, end = config.season_window(season_id)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=config.BBOX,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": config.MAX_CLOUD}},
    )
    items = sorted(search.items(), key=lambda i: i.datetime)
    print(f"{season_id}: found {len(items)} scenes under {config.MAX_CLOUD}% cloud")
    rows, failed = [], 0
    for n, item in enumerate(items, 1):
        result, ok = None, False
        for attempt in range(3):  # try each scene up to 3 times (network can be flaky)
            try:
                result, ok = ndvi_mod.scene_ndvi(item), True
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [{n}/{len(items)}] {item.datetime.date()} failed after 3 tries: {e}")
                else:
                    time.sleep(3 * (attempt + 1))
        if not ok:
            failed += 1
            continue
        if result is not None:
            ndvi, npix = result
            rows.append({"date": item.datetime.date(), "ndvi": round(ndvi, 4), "clean_pixels": npix})
        if n % 10 == 0:
            print(f"  [{n}/{len(items)}] done")
    return pd.DataFrame(rows), failed


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    try:
        catalog = Client.open(ndvi_mod.STAC_URL)
    except Exception as e:
        print("Could not reach the Planetary Computer. Check your internet connection and try again.")
        print(f"Details: {e}")
        return
    for season_id in config.SEASON_IDS:
        path = f"{config.DATA_DIR}/ndvi_{season_id}.csv"
        if os.path.exists(path):
            print(f"{season_id}: already done, skipping")
            continue
        try:
            df, failed = run_season(catalog, season_id)
        except Exception as e:
            print(f"{season_id}: search failed ({e}). Run the script again to retry.")
            continue
        if failed > MAX_FAILED_OK:
            print(f"{season_id}: {failed} scenes failed to download, so it was NOT saved. Run the script again to retry.")
            continue
        df.to_csv(path, index=False)
        note = f" ({failed} scenes failed and were skipped)" if failed else ""
        print(f"{season_id}: saved {len(df)} observations{note}")

    table = metrics.build_metrics()
    print("\nSeason metrics:")
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
