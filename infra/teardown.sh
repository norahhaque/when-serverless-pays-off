#!/usr/bin/env bash
# Delete the Lambda functions (public URLs cost money if someone finds them).
# EC2 instances: stop/terminate them from the console or with
#   aws ec2 terminate-instances --instance-ids i-...
set -euo pipefail
REGION=${REGION:-us-east-1}
for MEM in ${MEMS:-"1024 2048 3008"}; do
  aws lambda delete-function --function-name "resnet18-$MEM" --region "$REGION" && echo "deleted resnet18-$MEM"
done
