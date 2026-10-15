#!/usr/bin/env bash
set -euo pipefail
mkdir -p infra
cat >infra/template.yaml <<'YAML'
Resources:
  Orders:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - {AttributeName: PK, AttributeType: S}
        - {AttributeName: SK, AttributeType: S}
      KeySchema:
        - {AttributeName: PK, KeyType: HASH}
        - {AttributeName: SK, KeyType: RANGE}
YAML
git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
