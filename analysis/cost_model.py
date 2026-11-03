"""Analytical cost model: Lambda vs. always-on EC2 vs. hybrid, in $ per 1,000 requests.

  python analysis/cost_model.py                 # uses analysis/params.json
  python analysis/cost_model.py --params my.json

Writes three figures to results/figures/ and prints the crossover table.
Swap the assumed_* inputs for measured values as calibration results come in.
"""
import argparse
import json
import math
import os

import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(__file__)
FIG_DIR = os.path.join(HERE, "..", "results", "figures")

# Default categorical palette (slots 1-4) and recessive ink, light mode.
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


# ---------- cost functions ----------

def lambda_cost_per_req(p, mem_mb):
    billed_s = p["assumed_lambda_billed_ms"][str(mem_mb)] / 1000
    return p["lambda_price_per_request"] + (mem_mb / 1024) * billed_s * p["lambda_price_per_gb_s"]


def lambda_init_cost(p, mem_mb):
    """Container-image Lambdas are billed for the INIT phase of each cold start."""
    return (mem_mb / 1024) * p["assumed_lambda_init_s"] * p["lambda_price_per_gb_s"]


def ec2_cost_per_1k_steady(p, rps):
    n = math.ceil(rps / p["assumed_ec2_capacity_rps"])
    return n * p["ec2_price_per_hour"] / (rps * 3600) * 1000


def burst_profile(b, base=None):
    base = b["base_rps"] if base is None else base
    peak = base * b["mult"]
    quiet_s = b["period_s"] - b["burst_s"]
    reqs = base * quiet_s + peak * b["burst_s"]
    return base, peak, quiet_s, reqs


def hybrid_cost_per_1k(p, mem_mb, n, base=None):
    """N always-on containers; whatever exceeds N x capacity goes to Lambda."""
    b = p["burst"]
    base, peak, quiet_s, reqs = burst_profile(b, base)
    cap = n * p["assumed_ec2_capacity_rps"]
    over_quiet = max(0.0, base - cap) * quiet_s
    over_peak = max(0.0, peak - cap) * b["burst_s"]
    # Extra Lambda environments needed at the burst start (Little's law), assumed cold each cycle.
    lat_s = p["assumed_lambda_billed_ms"][str(mem_mb)] / 1000
    new_envs = math.ceil(max(0.0, peak - max(cap, base)) * lat_s)
    cycle = (n * p["ec2_price_per_hour"] * b["period_s"] / 3600
             + (over_quiet + over_peak) * lambda_cost_per_req(p, mem_mb)
             + new_envs * lambda_init_cost(p, mem_mb))
    return cycle / reqs * 1000


def steady_crossover(p, mem_mb, rates):
    lam = lambda_cost_per_req(p, mem_mb) * 1000
    for r in rates:
        if ec2_cost_per_1k_steady(p, r) < lam:
            return r
    return None


# ---------- figures ----------

def style(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=10)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)


def fig_steady(p, mems):
    rates = np.linspace(0.5, 50, 400)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, m in enumerate(mems):
        y = lambda_cost_per_req(p, m) * 1000
        ax.plot(rates, [y] * len(rates), color=C[i], lw=2, label=f"Lambda {m} MB")
    ec2 = [ec2_cost_per_1k_steady(p, r) for r in rates]
    ax.plot(rates, ec2, color=C[3], lw=2, label=f"EC2 {p['ec2_instance']} (always-on)")
    ax.set_yscale("log")
    ax.set_xlim(0, 50)
    style(ax, "Steady traffic: cost per 1,000 requests",
          "Request rate (req/s)", "$ per 1,000 requests (log)")
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "steady_crossover.png"), dpi=200)


def breakeven_utilization(p, mem_mb):
    """EC2 beats Lambda only if avg load / provisioned capacity exceeds this fraction."""
    ec2_full = p["ec2_price_per_hour"] / (p["assumed_ec2_capacity_rps"] * 3600)
    return ec2_full / lambda_cost_per_req(p, mem_mb)


def fig_burst_shift(p, mem_mb):
    """Crossover *average* rate when the always-on pool must be sized for the peak."""
    mults = [1, 1.5, 2, 2.5, 3, 4, 5]
    b = dict(p["burst"])
    lam = lambda_cost_per_req(p, mem_mb) * 1000
    xs = []
    for m in mults:
        b["mult"] = m
        found = None
        for base in np.linspace(0.1, 60, 1200):
            _, peak, _, reqs = burst_profile(b, base)
            avg = reqs / b["period_s"]
            n = math.ceil(peak / p["assumed_ec2_capacity_rps"])
            if n * p["ec2_price_per_hour"] / (avg * 3600) * 1000 < lam:
                found = avg
                break
        xs.append(None if found is None else float(found))
    fig, ax = plt.subplots(figsize=(7, 4))
    found = [(m, x) for m, x in zip(mults, xs) if x is not None]
    ax.set_ylim(0, max(x for _, x in found) * 1.4)
    ax.plot([m for m, _ in found], [x for _, x in found], color=C[0], lw=2,
            marker="o", ms=8, mec="white", mew=2)
    for m, x in found:
        ax.annotate(f"{x:.1f}", (m, x), xytext=(0, 9), textcoords="offset points",
                    ha="center", color=INK2, fontsize=9)
    missing = [m for m, x in zip(mults, xs) if x is None]
    if missing:
        ax.axvspan(min(missing) - 0.25, max(mults) + 0.25, color=GRID, alpha=0.6, lw=0)
        ax.text(min(missing) - 0.22, ax.get_ylim()[1] * 0.5,
                f"No crossover:\nEC2 never wins\n(break-even util.\n= {breakeven_utilization(p, mem_mb):.0%})",
                color=INK2, fontsize=9, va="center")
    ax.set_xlim(0.75, max(mults) + 0.25)
    style(ax, f"Bursts: peak-sized EC2 vs. Lambda {mem_mb} MB",
          "Burst multiplier (peak / base)", "Crossover average rate (req/s)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "burst_shift.png"), dpi=200)
    return dict(zip(mults, xs))


def fig_hybrid(p, mem_mb):
    b = p["burst"]
    base, peak, _, reqs = burst_profile(b)
    n_peak = math.ceil(peak / p["assumed_ec2_capacity_rps"])
    ns = list(range(0, n_peak + 1))
    costs = [hybrid_cost_per_1k(p, mem_mb, n) for n in ns]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(ns, costs, color=C[0], width=0.6)
    ax.set_xticks(ns)
    ax.set_xticklabels(["0\n(Lambda only)"] + [str(n) for n in ns[1:-1]] + [f"{n_peak}\n(peak-sized)"])
    best = int(np.argmin(costs))
    ax.annotate(f"cheapest: N={ns[best]}, ${costs[best]:.4f}", (ns[best], costs[best]),
                xytext=(0, 8), textcoords="offset points", ha="center", color=INK, fontsize=9)
    style(ax, f"Hybrid cost vs. number of always-on containers N\n"
              f"(base {base:g} req/s, {b['mult']:g}x burst for {b['burst_s']}s every {b['period_s']}s)",
          "Always-on containers N", "$ per 1,000 requests")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "hybrid_vs_n.png"), dpi=200)
    return dict(zip(ns, costs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=os.path.join(HERE, "params.json"))
    ap.add_argument("--mem", type=int, default=2048, help="Lambda memory for burst/hybrid figures")
    args = ap.parse_args()
    p = json.load(open(args.params))
    os.makedirs(FIG_DIR, exist_ok=True)
    mems = [int(m) for m in p["assumed_lambda_billed_ms"]]

    print("Lambda $/1k requests and steady-traffic crossover vs. EC2:")
    rates = np.round(np.arange(0.1, 200, 0.1), 1)
    for m in mems:
        print(f"  {m:>5} MB: ${lambda_cost_per_req(p, m) * 1000:.5f}/1k   "
              f"crossover ~ {steady_crossover(p, m, rates)} req/s")
    fig_steady(p, mems)
    print(f"Break-even EC2 utilization vs. Lambda {args.mem} MB: {breakeven_utilization(p, args.mem):.0%}")
    print("Burst multiplier -> crossover avg rate (None = never):",
          {k: (round(v, 1) if v else None) for k, v in fig_burst_shift(p, args.mem).items()})
    print("Hybrid N -> $/1k:", {k: round(float(v), 5) for k, v in fig_hybrid(p, args.mem).items()})
    print(f"Figures written to {os.path.abspath(FIG_DIR)}")


if __name__ == "__main__":
    main()
