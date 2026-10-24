"""Step 6: does rainfall explain your yields?

For every season we work out a few rainfall numbers from NASA POWER daily rainfall,
then compare each one with your yield (sacks per acre) from data/yields.csv.

Rainfall numbers per season (counted from the planting date: the date in data/planting_dates.csv if
you filled one in, otherwise 1 March / 1 October plus PLANTING_OFFSET_DAYS):
  rain_total             total rain from planting to the end of the season (mm)
  rain_first60           rain in the first 60 days after planting: germination and early growth (mm)
  rain_mid               rain in days 30 to 100 after planting: tasselling and grain filling (mm)
  longest_dry_spell_mid  longest run of days with under 1 mm in days 30 to 100 (days)
  wet_days               number of days with at least 1 mm of rain

Because we test several numbers against only 10 or 11 seasons, one of them can look good by
chance. So we also report a corrected p-value: how often a shuffled yield list gives a
best correlation as strong as the real one (see rain_summary.txt).

Run:  python 06_rain_vs_yield.py      (needs internet the first time, about 1 minute)
Output: data/season_rain.csv, outputs/rain_vs_yield.png, outputs/rain_summary.txt
Delete data/weather_daily_long.csv if you want to download the rainfall again.
"""
import importlib
import os
import time
import numpy as np
import pandas as pd
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config

weather = importlib.import_module("01_weather")      # reuse the NASA POWER parser
validate = importlib.import_module("05_validate")    # reuse evaluate()

PLANTING_OFFSET_DAYS = 0   # days after 1 March / 1 October that you usually plant (change if needed)
FIRST_DAYS = 60
MID_FROM, MID_TO = 30, 100
WET_MM = 1.0
CACHE = f"{config.DATA_DIR}/weather_daily_long.csv"
PLANTING_FILE = f"{config.DATA_DIR}/planting_dates.csv"   # optional: season,planting_date (YYYY-MM-DD)

METRICS = {
    "rain_total": "Total rain, planting to end of season (mm)",
    "rain_first60": "Rain in first 60 days (mm)",
    "rain_mid": "Rain in days 30 to 100 (mm)",
    "longest_dry_spell_mid": "Longest dry spell, days 30 to 100 (days)",
    "wet_days": "Wet days (at least 1 mm)",
}


def fetch_daily(start: str, end: str) -> pd.DataFrame:
    params = {
        "parameters": "PRECTOTCORR",
        "community": "AG",
        "longitude": round(config.LON, 4),
        "latitude": round(config.LAT, 4),
        "start": start.replace("-", ""),
        "end": end.replace("-", ""),
        "format": "JSON",
    }
    for attempt in range(3):
        try:
            r = requests.get(weather.API, params=params, timeout=120)
            r.raise_for_status()
            return weather.parse_power(r.json())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def get_daily() -> pd.DataFrame:
    """Daily rainfall for all seasons, downloaded once and then kept in data/."""
    if os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col="date", parse_dates=True)
    starts = [config.season_window(s)[0] for s in config.SEASON_IDS]
    ends = [config.season_window(s)[1] for s in config.SEASON_IDS]
    daily = fetch_daily(min(starts), max(ends))
    os.makedirs(config.DATA_DIR, exist_ok=True)
    daily.to_csv(CACHE)
    return daily


def longest_run(flags: np.ndarray) -> int:
    best = cur = 0
    for v in flags:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def load_planting_dates() -> dict:
    """Actual planting dates per season from data/planting_dates.csv (blank rows are ignored)."""
    if not os.path.exists(PLANTING_FILE):
        return {}
    p = pd.read_csv(PLANTING_FILE).dropna(subset=["planting_date"])
    p["planting_date"] = pd.to_datetime(p["planting_date"], errors="coerce")
    return {r.season: r.planting_date for r in p.itertuples() if pd.notna(r.planting_date)}


def season_rain(daily: pd.DataFrame, season_id: str, planting: dict = None) -> dict:
    start, end = config.season_window(season_id)
    planting = planting or {}
    t0 = planting.get(season_id)
    if t0 is None or not (pd.Timestamp(start) - pd.Timedelta(days=45) <= t0 <= pd.Timestamp(end)):
        t0 = pd.Timestamp(start) + pd.Timedelta(days=PLANTING_OFFSET_DAYS)   # default planting date
        used_actual = False
    else:
        used_actual = True
    s = daily.loc[t0:end, "rain_mm"]
    first = s[s.index < t0 + pd.Timedelta(days=FIRST_DAYS)]
    mid = s[(s.index >= t0 + pd.Timedelta(days=MID_FROM)) & (s.index < t0 + pd.Timedelta(days=MID_TO))]
    return {
        "season": season_id,
        "rain_total": round(float(s.sum()), 1),
        "rain_first60": round(float(first.sum()), 1),
        "rain_mid": round(float(mid.sum()), 1),
        "longest_dry_spell_mid": longest_run((mid.fillna(0) < WET_MM).to_numpy()),
        "wet_days": int((s >= WET_MM).sum()),
        "missing_days": int(s.isna().sum()),
        "actual_planting_date": used_actual,
    }


def corrected_p(df: pd.DataFrame, metrics: list, n_perm: int = 5000, seed: int = 0) -> float:
    """P-value for 'the best of these metrics correlates this strongly with yield'."""
    y = df["yield"].to_numpy(float)
    X = {m: df[m].to_numpy(float) for m in metrics}

    def best_abs_r(yy):
        return max(abs(np.corrcoef(X[m], yy)[0, 1]) for m in metrics)

    obs = best_abs_r(y)
    rng = np.random.default_rng(seed)
    perm = np.array([best_abs_r(rng.permutation(y)) for _ in range(n_perm)])
    return float((np.sum(perm >= obs) + 1) / (n_perm + 1))


def main():
    os.makedirs(config.OUT_DIR, exist_ok=True)
    try:
        daily = get_daily()
    except Exception as e:
        print("Could not download the rainfall from NASA POWER. Check your internet and run again.")
        print(f"Details: {e}")
        return

    planting = load_planting_dates()
    rain = pd.DataFrame([season_rain(daily, s, planting) for s in config.SEASON_IDS])
    rain["type"] = rain["season"].str[-1]
    rain.to_csv(f"{config.DATA_DIR}/season_rain.csv", index=False)

    yields = pd.read_csv(f"{config.DATA_DIR}/yields.csv")
    df = rain.merge(yields, on="season").dropna(subset=["yield"])
    lines = [f"Seasons used: {len(df)} ({', '.join(df['season'])})",
             f"Actual planting dates used for {int(df['actual_planting_date'].sum())} of {len(df)} seasons; "
             f"the rest assume planting {PLANTING_OFFSET_DAYS} days after 1 March / 1 October.",
             "Rainfall source: NASA POWER (gridded, about 50 km cells), so it shows the regional rain pattern, not rain at your plot."]
    if df["missing_days"].sum() > 0:
        lines.append(f"Missing rainfall days in these seasons: {int(df['missing_days'].sum())}")

    usable = [m for m in METRICS if df[m].std() > 0]
    results = {m: validate.evaluate(df[m].to_numpy(float), df["yield"].to_numpy(float)) for m in usable}
    lines.append("")
    lines.append(f"Yield spread (standard deviation): {df['yield'].std(ddof=0):.2f} sacks per acre")
    for m in usable:
        r = results[m]
        lines.append(f"{m}: r = {r['r']:+.2f}, Spearman = {r['spearman']:+.2f}, R2 = {r['r2']:.2f}, "
                     f"leave-one-out RMSE = {r['loo_rmse']:.2f}")
    best = max(usable, key=lambda m: abs(results[m]["r"]))
    p_adj = corrected_p(df, usable)
    lines.append("")
    lines.append(f"Strongest: {best} (r = {results[best]['r']:+.2f}).")
    lines.append(f"Corrected p-value for the best of {len(usable)} rainfall numbers: {p_adj:.2f}"
                 " (below 0.05 would be a real signal; with about 10 seasons even that needs care).")
    lines.append("Leave-one-out RMSE close to the yield spread means the rainfall number does no better than guessing the average yield.")

    # Chart: one small scatter per rainfall number
    n = len(usable)
    cols = 3
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(11, 3.6 * rows), squeeze=False)
    for ax in axes.ravel():
        ax.set_visible(False)
    for ax, m in zip(axes.ravel(), usable):
        ax.set_visible(True)
        for kind, colour, label in [("L", "#2a7f3f", "Long rains"), ("S", "#c9822b", "Short rains")]:
            sub = df[df["type"] == kind]
            ax.scatter(sub[m], sub["yield"], color=colour, s=35, label=label, zorder=3)
        for _, row in df.iterrows():
            ax.annotate(row["season"], (row[m], row["yield"]), textcoords="offset points", xytext=(4, 4), fontsize=7)
        res = results[m]
        xs = np.linspace(df[m].min(), df[m].max(), 30)
        ax.plot(xs, res["slope"] * xs + res["intercept"], color="#444", lw=1)
        ax.set_title(f"{m}  (r = {res['r']:+.2f}, R2 = {res['r2']:.2f})", fontsize=9)
        ax.set_xlabel(METRICS[m], fontsize=8)
        ax.set_ylabel("Yield (sacks per acre)", fontsize=8)
    axes.ravel()[0].legend(fontsize=7)
    fig.suptitle("Rainfall vs own-farm maize yield, one point per season", fontsize=11)
    fig.tight_layout()
    fig.savefig(f"{config.OUT_DIR}/rain_vs_yield.png", dpi=150)

    open(f"{config.OUT_DIR}/rain_summary.txt", "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
