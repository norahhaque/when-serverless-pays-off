"""Calibration figures.

  python analysis/plot_calibration.py cold results/raw/cold_start.csv
  python analysis/plot_calibration.py capacity results/raw/ec2_cap_r*_stats.csv --slo 500

cold:     Lambda cold vs. warm client latency per memory size (median, with p90 whisker)
capacity: one EC2 instance, p50/p99 vs. achieved request rate, from Locust *_stats.csv files
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cost_model import C, FIG_DIR, INK, INK2, style


def cold(path):
    df = pd.read_csv(path)
    df["kind"] = np.where(df["seq"] == 0, "cold", "warm")
    mems = sorted(df["memory_mb"].unique())
    g = df.groupby(["memory_mb", "kind"])["client_ms"]
    med, p90 = g.median(), g.quantile(0.9)

    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(mems))
    w = 0.36
    for i, kind in enumerate(["warm", "cold"]):
        ys = [med[(m, kind)] for m in mems]
        err = [p90[(m, kind)] - med[(m, kind)] for m in mems]
        xs = x + (i - 0.5) * (w + 0.02)
        ax.bar(xs, ys, w, color=C[i], label=kind, yerr=[np.zeros(len(ys)), err],
               error_kw={"ecolor": INK2, "elinewidth": 1, "capsize": 3})
        for xi, y in zip(xs, ys):
            ax.annotate(f"{y:,.0f}", (xi, y), xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_yscale("log")
    ticks = [100, 200, 500, 1000, 2000, 5000, 10000]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:,}" for t in ticks])
    ax.minorticks_off()
    ax.set_xticks(x)
    ax.set_xticklabels([f"{m} MB" for m in mems])
    style(ax, "Lambda latency: cold vs. warm (median, whisker = p90)",
          "Lambda memory size", "Client latency (ms, log)")
    ax.legend(frameon=False)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "lambda_cold_warm.png")
    fig.savefig(out, dpi=200)

    summary = pd.DataFrame({"median_ms": med, "p90_ms": p90}).round(0)
    load = df[df["seq"] == 0].groupby("memory_mb")["model_load_ms"].median().round(0)
    print(summary.to_string())
    print("median in-function model load on cold start (ms):", load.to_dict())
    print("wrote", out)


def capacity(paths, slo):
    """Files named <prefix>_r<target>_stats.csv; several prefixes (reps) are averaged."""
    rows = []
    for p in paths:
        s = pd.read_csv(p)
        agg = s[s["Name"] == "Aggregated"].iloc[0]
        base = os.path.basename(p)
        rows.append({"rep": base.split("_r")[0], "target": int(base.split("_r")[1].split("_")[0]),
                     "rps": agg["Requests/s"], "p50": agg["50%"], "p99": agg["99%"],
                     "fail_pct": 100 * agg["Failure Count"] / max(1, agg["Request Count"])})
    raw = pd.DataFrame(rows)
    df = raw.groupby("target").agg(rps=("rps", "mean"), p50=("p50", "mean"), p99=("p99", "mean"),
                                   p99_min=("p99", "min"), p99_max=("p99", "max"),
                                   fail_pct=("fail_pct", "max"), reps=("rep", "count")).reset_index()

    fig, ax = plt.subplots(figsize=(7, 4))
    if df["reps"].max() > 1:
        ax.fill_between(df["rps"], df["p99_min"], df["p99_max"], color=C[1], alpha=0.15, lw=0,
                        label="p99 range across runs")
    for i, col in enumerate(["p50", "p99"]):
        ax.plot(df["rps"], df[col], color=C[i], lw=2, marker="o", ms=8, mec="white", mew=2,
                label=f"{col} (mean of {df['reps'].max()} runs)")
    ax.axhline(slo, color=INK2, lw=1, ls="--")
    ax.annotate(f"SLO {slo:g} ms", (df["rps"].min(), slo), xytext=(0, 4), textcoords="offset points",
                color=INK2, fontsize=9)
    # Capacity = highest rate before the mean p99 first crosses the SLO.
    over = df.index[df["p99"] > slo]
    ok = df.loc[: over[0] - 1] if len(over) else df
    if len(ok):
        cap = ok["rps"].max()
        ax.axvline(cap, color=INK2, lw=1, ls=":")
        ax.annotate(f"capacity ~ {cap:.1f} req/s", (cap, slo * 1.6), xytext=(4, 0),
                    textcoords="offset points", color=INK, fontsize=9)
    style(ax, "One EC2 instance (c7i-flex.large): latency vs. load",
          "Achieved request rate (req/s)", "Latency (ms)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "ec2_capacity.png")
    fig.savefig(out, dpi=200)
    print(df.round(1).to_string(index=False))
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["cold", "capacity"])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--slo", type=float, default=500)
    args = ap.parse_args()
    os.makedirs(FIG_DIR, exist_ok=True)
    if args.kind == "cold":
        cold(args.paths[0])
    else:
        capacity(args.paths, args.slo)


if __name__ == "__main__":
    main()
