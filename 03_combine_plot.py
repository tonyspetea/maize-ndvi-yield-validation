"""Step 3: combine NDVI with rainfall, make the chart, test the relationship.

Reads:   data/ndvi_timeseries.csv, data/weather_weekly.csv
Writes:  outputs/ndvi_vs_rainfall.png, outputs/combined_weekly.csv,
         outputs/summary.txt
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config


def combine(ndvi: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """Weekly table with mean NDVI (interpolated across cloudy gaps) and rain."""
    ndvi = ndvi.copy()
    ndvi["date"] = pd.to_datetime(ndvi["date"])
    ndvi_w = ndvi.set_index("date")["ndvi"].resample("W-MON", label="left", closed="left").mean()
    ndvi_w.index.name = "week_start"
    out = weekly.join(ndvi_w, how="left")
    out["ndvi_interp"] = out["ndvi"].interpolate(limit=3)  # fill gaps of up to 3 weeks
    # rainfall in the previous 2 to 4 weeks is what crops respond to
    out["rain_prev4w"] = out["rain_mm"].rolling(4).sum().shift(1)
    return out


def main():
    os.makedirs(config.OUT_DIR, exist_ok=True)
    ndvi = pd.read_csv(f"{config.DATA_DIR}/ndvi_timeseries.csv")
    weekly = pd.read_csv(f"{config.DATA_DIR}/weather_weekly.csv", index_col="week_start", parse_dates=True)
    df = combine(ndvi, weekly)
    df.to_csv(f"{config.OUT_DIR}/combined_weekly.csv")

    # Chart: NDVI line over weekly rainfall bars
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.bar(df.index, df["rain_mm"], width=5, color="#8fb8de", label="Weekly rainfall (mm)")
    ax1.set_ylabel("Rainfall (mm per week)")
    ax2 = ax1.twinx()
    ax2.plot(df.index, df["ndvi_interp"], color="#2a7f3f", lw=2, label="NDVI (interpolated)")
    ax2.scatter(df.index, df["ndvi"], color="#1b5e2f", s=22, zorder=3, label="NDVI (satellite pass)")
    ax2.set_ylabel("NDVI")
    ax2.set_ylim(0, 1)
    ax1.set_title("Crop greenness (Sentinel-2 NDVI) vs rainfall, study area")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(f"{config.OUT_DIR}/ndvi_vs_rainfall.png", dpi=150)

    # Simple statistics: does greenness follow rainfall with a delay?
    lines = []
    valid = df.dropna(subset=["ndvi", "rain_prev4w"])
    lines.append(f"NDVI observations used: {len(valid)}")
    lines.append(f"Peak NDVI: {df['ndvi'].max():.2f} in week of {df['ndvi'].idxmax().date()}")
    if len(valid) >= 5:
        r = valid["ndvi"].corr(valid["rain_prev4w"])
        lines.append(f"Correlation between NDVI and rainfall of the previous 4 weeks: r = {r:.2f}")
    open(f"{config.OUT_DIR}/summary.txt", "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
