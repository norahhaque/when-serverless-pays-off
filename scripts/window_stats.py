"""Windowed latency stats from a per-request log (REQUEST_LOG in the locustfile). Stdlib only,
so it runs on the load generator and prints a small CSV.

  python3 scripts/window_stats.py /opt/results/burst-ec2_requests.csv 10
"""
import csv
import sys
from collections import defaultdict

path, width = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
rows = list(csv.DictReader(open(path)))
t0 = min(float(r["t"]) for r in rows)
buckets = defaultdict(list)
fails = defaultdict(int)
for r in rows:
    w = int((float(r["t"]) - t0) // width)
    buckets[w].append(float(r["ms"]))
    fails[w] += r["ok"] == "0"

print("t_s,n,p50,p99,fails")
for w in sorted(buckets):
    v = sorted(buckets[w])
    pick = lambda q: v[min(len(v) - 1, int(q * len(v)))]
    print(f"{w * width:.0f},{len(v)},{pick(0.5):.0f},{pick(0.99):.0f},{fails[w]}")
