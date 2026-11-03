"""Send N sequential requests and log client-side latency plus server fields to CSV.

Used for calibration: warm latency per Lambda memory size, single-request EC2 latency.

  python scripts/probe.py --url http://localhost:8080/predict -n 50 --out results/raw/local_probe.csv
"""
import argparse
import base64
import csv
import os
import statistics
import time

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--image", default=os.path.join(os.path.dirname(__file__), "..", "data", "sample.jpg"))
    ap.add_argument("--label", default="", help="tag stored in each row, e.g. lambda-2048")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    payload = {"image": base64.b64encode(open(args.image, "rb").read()).decode()}
    session = requests.Session()
    rows = []
    for i in range(args.n):
        t = time.perf_counter()
        r = session.post(args.url, json=payload, timeout=60)
        client_ms = (time.perf_counter() - t) * 1000
        body = r.json() if r.ok else {}
        rows.append({
            "config": args.label, "i": i, "status": r.status_code,
            "client_ms": round(client_ms, 2),
            "inference_ms": round(body.get("inference_ms", 0), 2),
            "cold": body.get("cold", ""), "model_load_ms": round(body.get("model_load_ms", 0), 2),
            "label": body.get("label", ""),
        })

    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        if write_header:
            w.writeheader()
        w.writerows(rows)

    warm = sorted(r["client_ms"] for r in rows[1:]) or [rows[0]["client_ms"]]
    print(f"first={rows[0]['client_ms']:.0f}ms cold={rows[0]['cold']}  "
          f"warm p50={statistics.median(warm):.0f}ms "
          f"p99~{warm[min(len(warm) - 1, int(0.99 * len(warm)))]:.0f}ms  label={rows[0]['label']}")


if __name__ == "__main__":
    main()
