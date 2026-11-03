"""Calibration figures.

  python analysis/plot_calibration.py cold results/raw/cold_start.csv
  python analysis/plot_calibration.py capacity results/raw/ec2cap-rep*_r*_stats.csv --slo 500
  python analysis/plot_calibration.py compare --slo 500
  python analysis/plot_calibration.py burst --slo 500

cold:     Lambda cold vs. warm client latency per memory size (median, with p90 whisker)
capacity: one EC2 instance, p50/p99 vs. achieved request rate, from Locust *_stats.csv files
compare:  p99 vs. rate for EC2 default, EC2 tuned, and Lambda, on one chart
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cost_model import C, FIG_DIR, GRID, INK, INK2, style


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


def load_sweep(pattern):
    import glob
    rows = []
    for p in glob.glob(pattern):
        s = pd.read_csv(p)
        agg = s[s["Name"] == "Aggregated"].iloc[0]
        target = int(os.path.basename(p).split("_r")[1].split("_")[0])
        rows.append({"target": target, "rps": agg["Requests/s"], "p99": agg["99%"]})
    return pd.DataFrame(rows).groupby("target").mean().reset_index()


def compare(slo):
    """p99 vs. achieved rate for every backend, on one axis."""
    series = [
        ("EC2, default server", "results/raw/ec2cap-rep*_r*_stats.csv", C[3], 2),
        ("EC2, tuned (2 workers x 1 thread)", "results/raw/ec2tuned-rep*_r*_stats.csv", C[1], 2),
        ("Lambda 3008 MB", "results/raw/lambda3008-rep*_r*_stats.csv", C[0], 5),
        ("Lambda 1024 MB", "results/raw/lambda1024-rep*_r*_stats.csv", C[2], 5),
    ]
    root = os.path.join(os.path.dirname(__file__), "..")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for label, pattern, color, min_target in series:
        df = load_sweep(os.path.join(root, pattern))
        df = df[df["target"] >= min_target]
        ax.plot(df["rps"], df["p99"], color=color, lw=2, marker="o", ms=8, mec="white", mew=2, label=label)
    ax.axhline(slo, color=INK2, lw=1, ls="--")
    ax.annotate(f"SLO {slo:g} ms", (2, slo), xytext=(0, 4), textcoords="offset points", color=INK2, fontsize=9)
    style(ax, "p99 latency vs. load, one EC2 instance vs. Lambda",
          "Achieved request rate (req/s)", "p99 latency (ms)")
    ax.set_ylim(0, 1400)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.text(0.99, 0.02, "Lambda 2 req/s run omitted: started cold (p99 4.2-4.6 s)",
            transform=ax.transAxes, ha="right", va="bottom", color=INK2, fontsize=8)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "p99_comparison.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)


def burst(slo, period=600, burst_len=120):
    """p99 per 10 s window during the burst test (from scripts/window_stats.py output), bursts shaded."""
    root = os.path.join(os.path.dirname(__file__), "..", "results", "raw")
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for label, name, color in [("EC2 tuned, 1 instance", "burst2-ec2tuned", C[1]),
                               ("Lambda 3008 MB", "burst2-lambda3008", C[0])]:
        h = pd.read_csv(os.path.join(root, f"{name}_windows.csv"))
        ax.plot(h["t_s"] / 60, h["p99"], color=color, lw=2, label=label)
    end = ax.get_xlim()[1]
    t = period - burst_len
    while t / 60 < end:
        ax.axvspan(t / 60, (t + burst_len) / 60, color=GRID, alpha=0.7, lw=0)
        ax.text((t + burst_len / 2) / 60, 0.97, "5x burst", transform=ax.get_xaxis_transform(),
                ha="center", va="top", color=INK2, fontsize=9)
        t += period
    ax.axhline(slo, color=INK2, lw=1, ls="--")
    ax.annotate(f"SLO {slo:g} ms", (0, slo), xytext=(2, 4), textcoords="offset points", color=INK2, fontsize=9)
    style(ax, "Bursty load (5 -> 25 req/s): p99 over time", "Time (min)", "p99 per 10 s window (ms)")
    ax.set_xlim(0, end)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.02, 0.9), fontsize=9)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "burst_timeline.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["cold", "capacity", "compare", "burst"])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--slo", type=float, default=500)
    args = ap.parse_args()
    os.makedirs(FIG_DIR, exist_ok=True)
    if args.kind == "burst":
        burst(args.slo)
    elif args.kind == "compare":
        compare(args.slo)
    elif args.kind == "cold":
        cold(args.paths[0])
    else:
        capacity(args.paths, args.slo)


if __name__ == "__main__":
    main()
