# Manage the local FalkorDB: scripts/db.sh up | ingest | status | down | reset
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${FALKORDB_PORT:-6379}"
BROWSER_PORT="${FALKORDB_BROWSER_PORT:-3000}"

case "${1:-}" in
  up)
    # --wait returns once the health check passes
    docker compose up -d --wait falkordb
    echo "FalkorDB:  redis://localhost:${PORT}/0"
    echo "Browser:   http://localhost:${BROWSER_PORT}"
    ;;
  ingest)
    # clears the graph named in config.py, then loads the dataset
    FALKORDB_URL="redis://localhost:${PORT}/0" python scripts/ingest_company_data.py "${2:-company_brain_dataset.json}"
    ;;
  status)
    docker compose ps
    ;;
  down)
    # stops and removes the container, keeps the data volume
    docker compose down
    ;;
  reset)
    # clean exit and forget everything: also removes the data volume
    docker compose down --volumes
    ;;
  *)
    echo "usage: scripts/db.sh up | ingest [dataset.json] | status | down | reset" >&2
    exit 1
    ;;
esac
