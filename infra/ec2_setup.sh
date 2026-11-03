#!/usr/bin/env bash
# Run ON the EC2 instance (Amazon Linux 2023) to start the inference container.
# The instance needs an IAM role with AmazonEC2ContainerRegistryReadOnly attached,
# and a security group allowing TCP 8080 from the load-generator / router.
#
#   REGION=us-east-1 ACCOUNT=123456789012 bash ec2_setup.sh
set -euo pipefail

REGION=${REGION:-us-east-1}
: "${ACCOUNT:?set ACCOUNT to your AWS account id}"
IMAGE=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/resnet-serving:latest

sudo dnf install -y docker
sudo systemctl enable --now docker
aws ecr get-login-password --region "$REGION" | sudo docker login --username AWS --password-stdin "${IMAGE%%/*}"
sudo docker pull "$IMAGE"
sudo docker rm -f resnet >/dev/null 2>&1 || true
sudo docker run -d --name resnet --restart unless-stopped -p 8080:8080 \
  --entrypoint python "$IMAGE" -m uvicorn server:app --host 0.0.0.0 --port 8080

until curl -sf localhost:8080/health; do sleep 2; done; echo
echo "Ready on :8080"
