"""Step 5: compare satellite season metrics with reported yield (ground-data validation).

You provide data/yields.csv with two columns:
    season,yield
    2022L,8.0
    2024S,4.5
    ...   (L = long rains, S = short rains, see config.py)
Use ONE consistent unit (for example 90 kg sacks per acre) and write
the unit and the source in README.md. The yield figures must be for the same area as
your BBOX (same county, or better, a smaller area). See README for where to find them.

Run:  python 05_validate.py
Output: outputs/ndvi_vs_yield.png, outputs/validation_summary.txt
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config

METRICS = ["peak_ndvi", "integrated_ndvi"]


def evaluate(x: np.ndarray, y: np.ndarray) -> dict:
    """Linear fit of yield on one metric, with leave-one-out error."""
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    loo_err = []
    for i in range(len(x)):
        mask = np.arange(len(x)) != i
        s, b = np.polyfit(x[mask], y[mask], 1)
        loo_err.append(y[i] - (s * x[i] + b))
    return {
        "r": float(np.corrcoef(x, y)[0, 1]),
        "spearman": float(pd.Series(x).rank().corr(pd.Series(y).rank())),  # Spearman = Pearson on ranks (no scipy needed)
        "slope": float(slope), "intercept": float(intercept), "r2": r2,
        "loo_rmse": float(np.sqrt(np.mean(np.square(loo_err)))),
    }


def main():
    os.makedirs(config.OUT_DIR, exist_ok=True)
    m = pd.read_csv(f"{config.DATA_DIR}/season_metrics.csv")
    y = pd.read_csv(f"{config.DATA_DIR}/yields.csv")
    df = m.merge(y, on="season").dropna(subset=["yield"] + METRICS)
    lines = [f"Seasons used: {len(df)} ({', '.join(df['season'])})"]
    bad = m[~m["season"].isin(df["season"])]
    if len(bad):
        lines.append("Seasons left out (no yield or poor NDVI): " + ", ".join(bad["season"]))
    if len(df) < 4:
        lines.append("Fewer than 4 seasons: not enough to say anything. Add more years.")
        open(f"{config.OUT_DIR}/validation_summary.txt", "w").write("\n".join(lines))
        print("\n".join(lines))
        return
    if len(df) < 8:
        lines.append("Note: fewer than 8 seasons, so treat the numbers below as indicative only.")

    counts = df["type"].value_counts().to_dict()
    lines.append(f"Long rains: {counts.get('L', 0)} seasons, short rains: {counts.get('S', 0)} seasons (pooled in one fit; analyse separately once there is enough data).")
    results = {}
    for name in METRICS:
        res = evaluate(df[name].to_numpy(float), df["yield"].to_numpy(float))
        results[name] = res
        lines.append(
            f"{name}: r = {res['r']:.2f}, Spearman = {res['spearman']:.2f}, "
            f"R2 = {res['r2']:.2f}, leave-one-out RMSE = {res['loo_rmse']:.2f} (yield units)"
        )

    best = max(results, key=lambda k: results[k]["r2"] if not np.isnan(results[k]["r2"]) else -1)
    res = results[best]
    lines.append(f"Best single metric in this sample: {best}. With so few points this can change as years are added.")

    fig, ax = plt.subplots(figsize=(6.5, 5))
    for kind, colour, label in [("L", "#2a7f3f", "Long rains"), ("S", "#c9822b", "Short rains")]:
        sub = df[df["type"] == kind]
        if len(sub):
            ax.scatter(sub[best], sub["yield"], color=colour, s=45, zorder=3, label=label)
    for _, r in df.iterrows():
        ax.annotate(r["season"], (r[best], r["yield"]), textcoords="offset points", xytext=(5, 5), fontsize=8)
    xs = np.linspace(df[best].min(), df[best].max(), 50)
    ax.plot(xs, res["slope"] * xs + res["intercept"], color="#444", lw=1.2, label=f"fit, all seasons (R2 = {res['r2']:.2f})")
    ax.set_xlabel(best.replace("_", " "))
    ax.set_ylabel("Reported yield")
    ax.set_title("Satellite greenness vs own-farm yield, one point per season")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(f"{config.OUT_DIR}/ndvi_vs_yield.png", dpi=150)

    open(f"{config.OUT_DIR}/validation_summary.txt", "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
