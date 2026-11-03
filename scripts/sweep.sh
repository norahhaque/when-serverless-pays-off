#!/usr/bin/env bash
# Runs ON the load generator: one steady Locust run per rate, results in /opt/results.
#
#   bash scripts/sweep.sh NAME HOST TARGET_PATH DURATION_S RATE [RATE ...]
#   bash scripts/sweep.sh ec2cap http://172.31.39.50:8080 /predict 90 2 4 6 8 10
#
# From the laptop, wrap it with scripts/remote.sh and pull results with scripts/fetch_results.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
NAME=$1 HOST=$2 TPATH=$3 DUR=$4
shift 4
mkdir -p /opt/results
for R in "$@"; do
  MODE=steady RATE=$R DURATION=$DUR TARGET_PATH=$TPATH python3.11 -m locust -f loadgen/locustfile.py \
    --headless --host "$HOST" --csv "/opt/results/${NAME}_r${R}" --only-summary >/dev/null 2>&1
  awk -F, -v r="$R" '$2 ~ /Aggregated/{printf "rate %s: achieved %.1f req/s  p50 %s  p99 %s  fails %s/%s\n", r, $10, $12, $19, $4, $3}' \
    "/opt/results/${NAME}_r${R}_stats.csv"
done
