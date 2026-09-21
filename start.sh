#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f client/dist/index.html ]; then
  (cd client && npm ci --no-audit --no-fund && npm run build)
fi
exec python run_poc.py
