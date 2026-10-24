"""Turn a season's NDVI observations into a few numbers per year.

These numbers are what we later compare with yield:
  peak_ndvi        highest (lightly smoothed) greenness in the season
  integrated_ndvi  total greenness over the season above bare-soil level
                   (area under the NDVI curve, a common yield proxy)
  greenup_day      days after the season start when greenness reaches half of its peak

Quality steps (written so they can be put in an SOP):
  1. Same-date scenes (overlapping tiles) are averaged.
  2. Spikes are removed: any point more than MAX_DROP away from the median of its
     neighbours (this catches missed cloud or haze, like the 0.04 reading in March 2025).
  3. Seasons with fewer than MIN_OBS clean observations are flagged and not used.
"""
import glob
import os
import re
import pandas as pd
import config

BASELINE = 0.2   # approximate NDVI of bare soil
MAX_DROP = 0.12  # spike threshold
MIN_OBS = 8      # minimum clean observations for a usable season
MAX_GAP_OK = 45  # days; longer gaps between observations get flagged


def despike(s: pd.Series, window: int = 5, max_diff: float = MAX_DROP) -> pd.Series:
    """Drop points that differ from the rolling median of their neighbours by too much."""
    med = s.rolling(window, center=True, min_periods=3).median()
    keep = ((s - med).abs() <= max_diff) | med.isna()
    return s[keep]


def season_metrics(df: pd.DataFrame, season_id: str, start: str):
    """Compute metrics for one season (for example 2024S). df needs columns: date, ndvi."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    s = df.groupby("date")["ndvi"].mean().sort_index()
    n_raw = len(s)
    s = despike(s)
    row = {"season": season_id, "year": int(season_id[:4]), "type": season_id[-1],
           "n_obs_raw": n_raw, "n_obs_used": len(s)}
    if len(s) < MIN_OBS:
        row.update(peak_ndvi=None, integrated_ndvi=None, greenup_day=None,
                   max_gap_days=None, quality="too few observations")
        return row

    smooth = s.rolling(3, center=True, min_periods=1).median()
    peak = float(smooth.max())
    daily = smooth.resample("D").mean().interpolate(limit_area="inside")
    integ = float((daily - BASELINE).clip(lower=0).sum())
    low = float(daily.min())
    half = low + 0.5 * (peak - low)
    up = daily[(daily >= half) & (daily.index <= daily.idxmax())]
    greenup = int((up.index[0] - pd.Timestamp(start)).days) if len(up) else None
    gap = int(s.index.to_series().diff().dt.days.max())

    row.update(peak_ndvi=round(peak, 3), integrated_ndvi=round(integ, 1),
               greenup_day=greenup, max_gap_days=gap,
               quality="ok" if gap <= MAX_GAP_OK else f"gap of {gap} days")
    return row


def build_metrics(data_dir: str = None) -> pd.DataFrame:
    """Read data/ndvi_<season>.csv (for example ndvi_2024S.csv) and write data/season_metrics.csv."""
    data_dir = data_dir or config.DATA_DIR
    rows = []
    for path in sorted(glob.glob(os.path.join(data_dir, "ndvi_[0-9][0-9][0-9][0-9][LS].csv"))):
        season_id = re.search(r"ndvi_(\d{4}[LS])\.csv", path).group(1)
        start, _ = config.season_window(season_id)
        rows.append(season_metrics(pd.read_csv(path), season_id, start))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(data_dir, "season_metrics.csv"), index=False)
    return out


if __name__ == "__main__":
    print(build_metrics().to_string(index=False))
