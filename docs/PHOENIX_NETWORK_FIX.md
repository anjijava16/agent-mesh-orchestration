# Phoenix Network Issue - RESOLVED ✅

## Problem

Phoenix was showing connection errors and UI GraphQL errors:

```
socket.gaierror: [Errno -2] Name or service not known
Error fetching GraphQL query 'authenticatedRootLoaderQuery'
```

## Root Cause

**Network Mismatch:**
- Phoenix container: `agentmesh_network` (from docker-compose-infra.yml)
- Postgres container: `agentmesh_default` (from docker-compose.yml)

Phoenix couldn't resolve the hostname "postgres" because they were on different Docker networks.

## Solution Applied

### Immediate Fix
```bash
# Connected Phoenix to the Postgres network
docker network connect agentmesh_default agentmesh-phoenix
docker restart agentmesh-phoenix
```

Phoenix is now on BOTH networks and can communicate with Postgres.

### Permanent Fix
Updated `docker-compose-infra.yml` to use the same network name as `docker-compose.yml`:

```yaml
# Changed from:
networks:
  default:
    name: agentmesh_network  # ❌ Different from docker-compose.yml

# Changed to:
networks:
  default:
    name: agentmesh_default  # ✅ Same as docker-compose.yml
```

## Verification

```bash
# Check Phoenix health
curl http://localhost:6006/healthz
# Returns: OK ✅

# Check Phoenix UI
open http://localhost:6006
# UI loads successfully ✅

# Check networks
docker inspect agentmesh-phoenix --format '{{json .NetworkSettings.Networks}}'
# Shows both agentmesh_default and agentmesh_network ✅

# Check logs
docker logs agentmesh-phoenix --tail 10
# Shows: "Phoenix is up and running" ✅
```

## Current Status

✅ Phoenix is HEALTHY and RUNNING
✅ Phoenix UI is accessible at http://localhost:6006
✅ Phoenix can connect to PostgreSQL
✅ No more connection errors
✅ GraphQL queries working

## Network Configuration

**Phoenix is now on:**
- `agentmesh_default` - Can reach Postgres, LiteLLM
- `agentmesh_network` - Can reach Redis, OpenSearch, MinIO, etc.

**Why Phoenix needs both networks:**
- Running `docker-compose.yml` creates `agentmesh_default`
- Running `docker-compose-infra.yml` creates `agentmesh_network`
- Phoenix from infra needs to talk to Postgres from main compose

## Prevention

To avoid this in the future:

1. **Option A:** Use only ONE compose file at a time
   ```bash
   # Either full stack:
   docker compose up -d
   
   # OR infrastructure only:
   docker compose -f docker-compose-infra.yml up -d
   ```

2. **Option B:** Ensure both compose files use the same network name (DONE ✅)

3. **Option C:** Explicitly define external networks in both files

## Related Services

Other services that were also affected:
- **LiteLLM**: Was on `agentmesh_default`, now accessible
- **Postgres**: Always on `agentmesh_default`
- **Redis, OpenSearch, MinIO**: On `agentmesh_network`

## Timeline

- **Before:** Phoenix healthy but couldn't connect to Postgres
- **Issue:** `socket.gaierror: [Errno -2] Name or service not known`
- **Fix:** Connected Phoenix to `agentmesh_default` network
- **After:** Phoenix fully functional, UI working, all GraphQL queries working

## Commands for Future Reference

```bash
# Check container networks
docker inspect <container> --format '{{json .NetworkSettings.Networks}}'

# List Docker networks
docker network ls

# Inspect network contents
docker network inspect agentmesh_default

# Connect container to network
docker network connect <network> <container>

# Restart container
docker restart <container>
```

## Files Modified

1. `docker-compose-infra.yml` - Changed network name to `agentmesh_default`

## Verification Checklist

- [x] Phoenix healthcheck passes
- [x] Phoenix UI loads at http://localhost:6006
- [x] No connection errors in Phoenix logs
- [x] GraphQL queries work
- [x] Phoenix connected to both networks
- [x] Can connect to PostgreSQL database
- [x] Network configuration updated for permanence

---

**Status:** ✅ RESOLVED - September 8, 2026
**Phoenix Version:** arizephoenix/phoenix:latest
**Networks:** agentmesh_default + agentmesh_network
