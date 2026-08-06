#!/usr/bin/env bash
set -euo pipefail

# Deploy QuantMind backend to Fly.io (requires flyctl and app name)
APP_NAME=${FLY_APP_NAME:-quantmind}

echo "Deploying QuantMind backend to Fly.io: $APP_NAME"
fly deploy --app "$APP_NAME"
