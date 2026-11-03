"""Measure Lambda cold vs. warm latency for each memory size.

Forces a cold start by changing an environment variable (Lambda then discards all
warm execution environments), sends one request (cold), then several more (warm).

  python scripts/cold_start.py --functions resnet18-1024 resnet18-2048 resnet18-3008 \
      --trials 10 --out results/raw/cold_start.csv

The Init Duration that Lambda bills is in CloudWatch REPORT lines; pull them with
  aws logs filter-log-events --log-group-name /aws/lambda/resnet18-2048 --filter-pattern "Init Duration"
"""
import argparse
import base64
import csv
import os
import time
import uuid

import boto3
import requests


def force_cold(lam, fn):
    lam.update_function_configuration(FunctionName=fn, Environment={"Variables": {"NONCE": uuid.uuid4().hex}})
    lam.get_waiter("function_updated_v2").wait(FunctionName=fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--functions", nargs="+", required=True)
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--warm", type=int, default=5, help="warm requests after each cold one")
    ap.add_argument("--region", default=os.environ.get("AWS_REGION"), help="defaults to your aws configure region")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    lam = boto3.client("lambda", region_name=args.region)
    img = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "..", "data", "sample.jpg"), "rb").read()).decode()
    write_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["function", "memory_mb", "trial", "seq", "cold", "client_ms", "inference_ms", "model_load_ms"])
        for fn in args.functions:
            mem = lam.get_function_configuration(FunctionName=fn)["MemorySize"]
            url = lam.get_function_url_config(FunctionName=fn)["FunctionUrl"]
            for trial in range(args.trials):
                force_cold(lam, fn)
                s = requests.Session()  # fresh connection each trial
                for seq in range(1 + args.warm):
                    t = time.perf_counter()
                    body = s.post(url, json={"image": img}, timeout=120).json()
                    ms = (time.perf_counter() - t) * 1000
                    w.writerow([fn, mem, trial, seq, body["cold"], round(ms, 1),
                                round(body["inference_ms"], 1), round(body["model_load_ms"], 1)])
                    f.flush()
                print(f"{fn} trial {trial}: done")


if __name__ == "__main__":
    main()
