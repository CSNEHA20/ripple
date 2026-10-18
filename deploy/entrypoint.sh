#!/bin/sh
set -e

echo "[Ripple] Starting FalkorDB in background..."
redis-server --loadmodule /var/lib/falkordb/bin/falkordb.so --daemonize yes --port 6379

echo "[Ripple] Waiting for FalkorDB to be ready..."
until redis-cli -p 6379 ping >/dev/null 2>&1; do
  sleep 0.1
done

echo "[Ripple] FalkorDB is live. Starting Ripple backend on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
