#!/usr/bin/env bash
# A CDK app's synthesized template. JSON on purpose: the eval sandbox has
# no network, so the CLI can't fetch PyYAML for a YAML template.
set -euo pipefail
mkdir -p infra/cdk.out
cp "$(dirname -- "${BASH_SOURCE[0]}")/../fixtures/OrdersStack.template.json" infra/cdk.out/
git init -q -b main
git -c user.name=eval -c user.email=eval@example.invalid add -A
git -c user.name=eval -c user.email=eval@example.invalid commit -qm 'chore: init'
