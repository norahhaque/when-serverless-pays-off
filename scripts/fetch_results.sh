#!/usr/bin/env bash
# Copy Locust *_stats.csv files matching a prefix from the load generator into results/raw/.
#
#   ./scripts/fetch_results.sh ec2cap
set -euo pipefail
cd "$(dirname "$0")/.."
PREFIX=$1
./scripts/remote.sh "cd /opt/results && for f in ${PREFIX}_*_stats.csv; do echo \"### \$f\"; cat \"\$f\"; done" |
  awk -v dir=results/raw '/^### /{out=dir "/" $2; printf "" > out; print "fetched " out; next} out && NF{print >> out}'
