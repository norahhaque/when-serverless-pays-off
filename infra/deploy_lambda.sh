#!/usr/bin/env bash
# Build the image for x86_64, push it to ECR, and create one Lambda function (with a
# public Function URL) per memory size. Safe to re-run: existing resources get updated.
#
#   ./infra/deploy_lambda.sh
#
# Needs: aws CLI configured (aws configure), Docker running.
set -euo pipefail

REGION=${REGION:-us-east-1}
REPO=${REPO:-resnet-serving}
ROLE=${ROLE:-resnet-lambda-role}
MEMS=${MEMS:-"1024 2048 3008"}

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
IMAGE=$REGISTRY/$REPO:latest

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# --provenance=false: Lambda rejects the OCI index manifests buildx emits by default.
# linux/amd64 is emulated on Apple Silicon, so the first build is slow (~10+ min).
docker buildx build --platform linux/amd64 --provenance=false -t "$IMAGE" --push .

if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "Waiting for the new IAM role to propagate..."; sleep 15
fi
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)

for MEM in $MEMS; do
  FN=resnet18-$MEM
  if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$FN" --image-uri "$IMAGE" --region "$REGION" >/dev/null
  else
    aws lambda create-function --function-name "$FN" --package-type Image --code ImageUri="$IMAGE" \
      --role "$ROLE_ARN" --memory-size "$MEM" --timeout 60 --architectures x86_64 --region "$REGION" >/dev/null
    aws lambda wait function-active-v2 --function-name "$FN" --region "$REGION"
    aws lambda create-function-url-config --function-name "$FN" --auth-type NONE --region "$REGION" >/dev/null
    aws lambda add-permission --function-name "$FN" --statement-id public-url \
      --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE --region "$REGION" >/dev/null
    # If the URL returns 403 Forbidden, your account may also need lambda:InvokeFunction
    # granted for URL calls; see the "Function URL" permissions page in the Lambda docs.
  fi
  echo "$FN -> $(aws lambda get-function-url-config --function-name "$FN" --region "$REGION" --query FunctionUrl --output text)"
done

echo
echo "Account concurrency limit (new accounts are often 10; request an increase if so):"
aws lambda get-account-settings --region "$REGION" --query AccountLimit.ConcurrentExecutions
