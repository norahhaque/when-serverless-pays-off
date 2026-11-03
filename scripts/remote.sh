#!/usr/bin/env bash
# Run a shell command on the load generator through SSM and print its output.
#
#   ./scripts/remote.sh 'cd /opt/repo && git pull'
#   ./scripts/remote.sh 'cd /opt/repo && MODE=steady RATE=5 DURATION=120 locust -f loadgen/locustfile.py \
#       --headless --host http://10.0.0.5:8080 --csv /tmp/r5 --only-summary && cat /tmp/r5_stats.csv'
set -euo pipefail
cd "$(dirname "$0")/.."
source infra/.ec2.env
export AWS_DEFAULT_REGION=$REGION
TARGET=${TARGET:-$LOADGEN_ID}

PARAMS=$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.argv[1]], "executionTimeout": ["7200"]}))' "$1")
CMD_ID=$(aws ssm send-command --instance-ids "$TARGET" --document-name AWS-RunShellScript \
  --parameters "$PARAMS" --query Command.CommandId --output text)

while true; do
  STATUS=$(aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$TARGET" \
    --query Status --output text 2>/dev/null || echo Pending)
  case $STATUS in Pending|InProgress|Delayed) sleep 3 ;; *) break ;; esac
done
aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$TARGET" \
  --query "[StandardOutputContent, StandardErrorContent]" --output text
[ "$STATUS" = Success ]
