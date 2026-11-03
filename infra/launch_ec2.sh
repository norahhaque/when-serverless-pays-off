#!/usr/bin/env bash
# Launch inference server(s) and one load generator in the default VPC.
# Both are managed through SSM (no SSH keys). Instance ids/IPs go to infra/.ec2.env.
#
#   ./infra/launch_ec2.sh            # 1 server + 1 load generator
#   SERVERS=3 ./infra/launch_ec2.sh  # 3 servers + 1 load generator
#
# Run ./infra/teardown.sh to terminate everything tagged project=csci5144.
set -euo pipefail
cd "$(dirname "$0")/.."

REGION=${REGION:-$(aws configure get region || echo us-east-1)}
SERVERS=${SERVERS:-1}
TYPE=${TYPE:-c7i-flex.large}
LOADGEN_TYPE=${LOADGEN_TYPE:-c7i-flex.large}
REPO_URL=${REPO_URL:-https://github.com/norahhaque/when-serverless-pays-off}
ROLE=resnet-ec2-role
SG_NAME=resnet-sg
export AWS_DEFAULT_REGION=$REGION

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)

# IAM role: pull from ECR + be reachable through SSM.
if ! aws iam get-instance-profile --instance-profile-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
  aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  echo "Waiting for the instance profile to propagate..."; sleep 15
fi

# Security group: port 8080 open only to members of the same group (load generator, router).
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text)
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=$SG_NAME Name=vpc-id,Values=$VPC \
  --query "SecurityGroups[0].GroupId" --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name $SG_NAME --description "csci5144 inference" --vpc-id "$VPC" \
    --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 8080 --source-group "$SG" >/dev/null
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 8000 --source-group "$SG" >/dev/null
fi

TAGS="ResourceType=instance,Tags=[{Key=project,Value=csci5144},{Key=Name,Value=%s}]"

SERVER_DATA=$(mktemp); LOADGEN_DATA=$(mktemp)
{ echo '#!/bin/bash'; echo "export REGION=$REGION ACCOUNT=$ACCOUNT"; cat infra/ec2_setup.sh; } > "$SERVER_DATA"
cat > "$LOADGEN_DATA" <<EOF
#!/bin/bash
dnf install -y git python3.11 python3.11-pip
git clone $REPO_URL /opt/repo
python3.11 -m pip install locust requests  # AL2023's python3.9 has no gevent wheel
touch /opt/loadgen-ready
EOF

launch() {  # name count user-data-file type
  aws ec2 run-instances --image-id "$AMI" --instance-type "$4" --count "$2" \
    --security-group-ids "$SG" --iam-instance-profile Name=$ROLE \
    --user-data "file://$3" --tag-specifications "$(printf "$TAGS" "$1")" \
    --metadata-options HttpTokens=required \
    --query "Instances[].InstanceId" --output text
}

SERVER_IDS=$(launch resnet-server "$SERVERS" "$SERVER_DATA" "$TYPE")
LOADGEN_ID=$(launch resnet-loadgen 1 "$LOADGEN_DATA" "$LOADGEN_TYPE")
rm -f "$SERVER_DATA" "$LOADGEN_DATA"

echo "Waiting for instances to run..."
aws ec2 wait instance-running --instance-ids $SERVER_IDS $LOADGEN_ID
SERVER_IPS=$(aws ec2 describe-instances --instance-ids $SERVER_IDS \
  --query "Reservations[].Instances[].PrivateIpAddress" --output text)

cat > infra/.ec2.env <<EOF
REGION=$REGION
SERVER_IDS="$SERVER_IDS"
SERVER_IPS="$SERVER_IPS"
LOADGEN_ID=$LOADGEN_ID
EOF
cat infra/.ec2.env
echo "Servers need ~3-5 min to pull the image. Check with:"
echo "  ./scripts/remote.sh 'curl -s http://${SERVER_IPS%% *}:8080/health'"
