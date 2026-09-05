#!/usr/bin/env bash
# Destructive. Drops both OpenSearch indices and lets the API recreate them on
# next start. Use after changing OPENSEARCH_EMBEDDING_DIM or a mapping - a
# knn_vector dimension cannot be changed in place.
set -euo pipefail

OS="${OPENSEARCH_URL:-http://localhost:9200}"
DOCS="${OPENSEARCH_DOCUMENTS_INDEX:-agentmesh-documents}"
MEM="${OPENSEARCH_MEMORY_INDEX:-agentmesh-longterm-memory}"

read -rp "Delete indices '$DOCS' and '$MEM' at $OS? [y/N] " confirm
[ "$confirm" = "y" ] || { echo "Aborted."; exit 0; }

curl -sS -X DELETE "$OS/$DOCS" || true
curl -sS -X DELETE "$OS/$MEM" || true
echo ""
echo "Deleted. Restart the backend to recreate them:"
echo "  docker compose restart backend"
echo ""
echo "Then re-ingest every document:"
echo "  for id in \$(curl -sS $API/files -H 'X-User-ID: demo-user' | python3 -c \"import sys,json;[print(d['id']) for d in json.load(sys.stdin)['items']]\"); do"
echo "    curl -sS -X POST \$API/files/\$id/reingest -H 'X-User-ID: demo-user'; done"
