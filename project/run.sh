#!/bin/bash

# ==============================================================================
# AWS SESSION CREDENTIALS CONFIGURATION
# (Update these 3 keys whenever you start a new Cloud Resource session)
# ==============================================================================
ACCESS_KEY="<YOUR_AWS_ACCESS_KEY_ID>"
SECRET_KEY="<YOUR_AWS_SECRET_ACCESS_KEY>"
SESSION_TOKEN="<YOUR_AWS_SESSION_TOKEN>"
REGION="us-east-1"

# 1. Set credentials in AWS CLI config (~/.aws/credentials) so Python/boto3 also sees them
aws configure set aws_access_key_id "$ACCESS_KEY"
aws configure set aws_secret_access_key "$SECRET_KEY"
aws configure set aws_session_token "$SESSION_TOKEN"
aws configure set region "$REGION"

# 2. Export environment variables for the current shell session
export AWS_ACCESS_KEY_ID="$ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
export AWS_SESSION_TOKEN="$SESSION_TOKEN"
export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"

echo "=== 1. AWS Identity Verified ==="
aws sts get-caller-identity --query "Arn" --output text

echo "=== 2. Deploying Foundation CloudFormation Stack (udacity-agentcore) ==="
echo "This takes about 2-3 minutes to provision DynamoDB, S3, S3 Vectors, IAM, and CloudWatch..."
aws cloudformation deploy \
  --template-file infrastructure/starter_stack.yaml \
  --stack-name udacity-agentcore \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

echo "=== 3. Seeding Sample Data to DynamoDB and S3 ==="
python infrastructure/seed_data.py

echo "=== 4. Setting up .env file ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env created from .env.example"
else
  echo ".env already exists"
fi

echo "=== 5. Verifying Setup with config.py ==="
python config.py
