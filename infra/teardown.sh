#!/usr/bin/env bash
# Terminate every EC2 instance tagged project=csci5144 and delete the Lambda functions.
#   ./infra/teardown.sh            # everything
#   ./infra/teardown.sh ec2        # instances only (keep Lambda deployed)
set -euo pipefail
REGION=${REGION:-$(aws configure get region || echo us-east-1)}
export AWS_DEFAULT_REGION=$REGION

IDS=$(aws ec2 describe-instances --filters Name=tag:project,Values=csci5144 \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query "Reservations[].Instances[].InstanceId" --output text)
if [ -n "$IDS" ]; then
  aws ec2 terminate-instances --instance-ids $IDS >/dev/null && echo "terminating: $IDS"
else
  echo "no csci5144 instances running"
fi
rm -f "$(dirname "$0")/.ec2.env"

[ "${1:-}" = ec2 ] && exit 0
for MEM in ${MEMS:-1024 2048 3008}; do
  aws lambda delete-function --function-name "resnet18-$MEM" 2>/dev/null && echo "deleted resnet18-$MEM" || true
done
