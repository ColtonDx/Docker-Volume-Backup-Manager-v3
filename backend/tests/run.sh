#!/usr/bin/env bash
# Convenience runner. Usage:
#   ./tests/run.sh            # everything
#   ./tests/run.sh unit       # fast, no Docker
#   ./tests/run.sh integration
#   ./tests/run.sh clean      # remove leftovers from an interrupted run
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-all}" in
  unit)        exec python -m pytest tests/unit -v ;;
  integration) exec python -m pytest tests/integration -v ;;
  fast)        exec python -m pytest tests -v -m "not slow" ;;
  clean)
    echo "Removing leftover test containers and volumes..."
    ids=$(docker ps -aq --filter name=dvbmtest- || true)
    [ -n "$ids" ] && docker rm -f $ids || echo "  no containers"
    vols=$(docker volume ls -q --filter name=dvbmtest- || true)
    [ -n "$vols" ] && docker volume rm $vols || echo "  no volumes"
    echo "Done."
    ;;
  all)         exec python -m pytest tests -v ;;
  *)           exec python -m pytest "$@" ;;
esac
