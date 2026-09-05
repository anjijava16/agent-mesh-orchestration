#!/usr/bin/env bash
# End-to-end check against a running stack. Exits non-zero on the first failure.
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
USER="${USER_ID:-demo-user}"
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1"; exit 1; }

echo "Health"
curl -fsS "$API/health/live" >/dev/null && pass "liveness" || fail "liveness"
READY=$(curl -sS "$API/health/ready" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$READY" = "ready" ] && pass "readiness" || fail "readiness ($READY)"

echo "Dependencies"
curl -sS "$API/health" | python3 - <<'PY'
import json, sys
health = json.load(sys.stdin)
for name, dep in health["dependencies"].items():
    print(f"  {'ok  ' if dep['status'] == 'up' else 'DOWN'} {name}")
    if dep["status"] != "up":
        sys.exit(1)
open_breakers = [n for n, b in health["breakers"].items() if b["state"] != "closed"]
print(f"  ok   breakers ({len(open_breakers)} open)" if not open_breakers
      else f"  WARN open breakers: {open_breakers}")
PY

echo "Frameworks"
curl -sS "$API/frameworks" | python3 - <<'PY'
import json, sys
for fw in json.load(sys.stdin)["frameworks"]:
    print(f"  {'ok  ' if fw['installed'] else 'MISS'} {fw['id']:<18} {fw.get('note','')}")
PY

echo "Settings"
curl -fsS "$API/settings/options" >/dev/null && pass "options" || fail "options"

echo "Chat (non-streaming)"
ANSWER=$(curl -sS -X POST "$API/chat" -H "X-User-ID: $USER" -H 'Content-Type: application/json' \
  -d '{"message":"Reply with the single word: pong"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('answer','')[:60])")
[ -n "$ANSWER" ] && pass "chat -> $ANSWER" || fail "chat returned nothing (is a provider key set?)"

echo ""
echo "Smoke test passed."
