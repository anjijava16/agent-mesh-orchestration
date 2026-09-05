#!/usr/bin/env bash
# Uploads a sample document and waits for it to finish indexing, so you have
# something to retrieve against on a fresh install.
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
USER="${USER_ID:-demo-user}"
TMP="$(mktemp -d)"
DOC="$TMP/agentmesh-sample.md"

cat > "$DOC" <<'DOCEOF'
# Northwind Quarterly Operations Review — Q3

## Revenue
Q3 revenue was 4,180,000 USD, up from 3,640,000 USD in Q2. The increase came
almost entirely from the enterprise segment, which grew 22% quarter over quarter
while self-serve was flat.

## Costs
Infrastructure spend was 512,000 USD, of which 61% was model inference. The
finance team has asked engineering to bring inference below 50% of infrastructure
spend by the end of Q4.

## Incidents
There were two Sev-1 incidents. INC-4471 (payment gateway timeout, 47 minutes)
and INC-4498 (search cluster red status, 2 hours 14 minutes). Both were traced to
missing circuit breakers on outbound dependencies.

## Retention Policy
Customer documents are retained for 90 days. Deletion requests must be honoured
within 30 days and are logged to the audit trail.
DOCEOF

echo "Uploading sample document..."
RESPONSE=$(curl -sS -X POST "$API/files" -H "X-User-ID: $USER" -F "file=@$DOC;type=text/markdown")
DOC_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  document_id: $DOC_ID"

echo "Waiting for ingestion..."
for _ in $(seq 1 60); do
  STATUS=$(curl -sS "$API/files/$DOC_ID" -H "X-User-ID: $USER" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  status: $STATUS"
  [ "$STATUS" = "indexed" ] && break
  [ "$STATUS" = "failed" ] && { echo "Ingestion failed. Check: docker compose logs celery-worker"; exit 1; }
  sleep 3
done

echo ""
echo "Try it:"
echo "  curl -sS -X POST $API/search -H 'X-User-ID: $USER' -H 'Content-Type: application/json' \\"
echo "    -d '{\"query\":\"what caused the Sev-1 incidents\"}' | python3 -m json.tool"
rm -rf "$TMP"
