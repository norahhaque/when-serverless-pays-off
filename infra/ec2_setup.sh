#!/usr/bin/env bash
# Run ON the EC2 instance (Amazon Linux 2023) to start the inference container.
# The instance needs an IAM role with AmazonEC2ContainerRegistryReadOnly attached,
# and a security group allowing TCP 8080 from the load-generator / router.
#
#   REGION=us-east-1 ACCOUNT=123456789012 bash ec2_setup.sh
set -euo pipefail

REGION=${REGION:-$(aws configure get region || echo us-east-1)}
: "${ACCOUNT:?set ACCOUNT to your AWS account id}"
IMAGE=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/resnet-serving:latest

sudo dnf install -y docker
sudo systemctl enable --now docker
aws ecr get-login-password --region "$REGION" | sudo docker login --username AWS --password-stdin "${IMAGE%%/*}"
sudo docker pull "$IMAGE"
sudo docker rm -f resnet >/dev/null 2>&1 || true
# Tuned default: 2 processes x 1 PyTorch thread (capacity 15.3 vs 7.8 req/s for 1 x 2).
# For the untuned baseline: WORKERS=1 THREADS=0 (0 = PyTorch picks, i.e. one per vCPU).
WORKERS=${WORKERS:-2}
THREADS=${THREADS:-1}
THREAD_ENV=()
[ "$THREADS" != 0 ] && THREAD_ENV=(-e "OMP_NUM_THREADS=$THREADS")
sudo docker run -d --name resnet --restart unless-stopped -p 8080:8080 "${THREAD_ENV[@]}" \
  --entrypoint python "$IMAGE" -m uvicorn server:app --host 0.0.0.0 --port 8080 --workers "$WORKERS"

until curl -sf localhost:8080/health; do sleep 2; done; echo
echo "Ready on :8080"
