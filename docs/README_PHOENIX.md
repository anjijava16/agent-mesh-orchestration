# Phoenix Observability for Notebooks - Quick Guide

## Problem
Notebook shows: **"Exporter already shutdown, ignoring batch"** and traces don't appear in Phoenix UI.

## Quick Fix (3 Steps)

### 1. Start Phoenix
```bash
# Make sure Phoenix is running
docker compose -f docker-compose-infra.yml up -d phoenix

# Or use the convenience script
./start-local.sh
```

### 2. Restart Jupyter Kernel
- **In Jupyter Notebook:** Kernel → Restart
- **In VSCode:** Click "Restart" in notebook toolbar
- **In JupyterLab:** Kernel → Restart Kernel

### 3. Run Setup Cell ONCE
Run the Phoenix setup cell at the start of your notebook. **Do NOT run it multiple times.**

---

## Files in This Directory

### 📄 `FIX_PHOENIX_EXPORT.md`
**Complete troubleshooting guide** with:
- Root cause analysis
- 5 different solutions
- Verification steps
- Common issues & fixes
- Best practices

**Read this if:** You're experiencing persistent Phoenix issues

---

### 🐍 `phoenix_setup_improved.py`
**Enhanced Phoenix setup code** with:
- Health checks before registration
- Graceful degradation if Phoenix unavailable
- Better error messages
- Dummy tracer for offline development

**Use this:** Copy into your notebook to replace existing Phoenix setup cell

---

### 🔧 `diagnose_phoenix.py`
**Diagnostic script** that checks:
- Docker container status
- Port accessibility
- HTTP endpoints
- Environment variables
- OTLP connectivity

**Run this:** When you need to diagnose connection issues

```bash
# From terminal
python notebook/diagnose_phoenix.py

# Or in notebook
%run notebook/diagnose_phoenix.py
```

---

## Usage Examples

### Example 1: First Time Setup

```bash
# 1. Start infrastructure
docker compose -f docker-compose-infra.yml up -d

# 2. Wait for services
sleep 15

# 3. Open Phoenix UI
open http://localhost:6006

# 4. Start Jupyter
jupyter notebook

# 5. In notebook: Run setup cell ONCE
# 6. Run rest of notebook
```

### Example 2: Troubleshooting

```bash
# Run diagnostic
python notebook/diagnose_phoenix.py

# Check Phoenix logs
docker compose -f docker-compose-infra.yml logs phoenix

# Restart Phoenix if needed
docker compose -f docker-compose-infra.yml restart phoenix
```

### Example 3: Clean Start

```bash
# Stop everything
docker compose -f docker-compose-infra.yml down

# Start fresh
docker compose -f docker-compose-infra.yml up -d

# Restart kernel in notebook
# Run setup cell once
```

---

## Common Errors & Quick Fixes

### ❌ "Exporter already shutdown, ignoring batch"

**Cause:** Setup cell ran multiple times in same kernel

**Fix:**
```
1. Kernel → Restart
2. Run setup cell ONCE
```

---

### ❌ "Connection refused to localhost:4317"

**Cause:** Phoenix not running or port not accessible

**Fix:**
```bash
docker compose -f docker-compose-infra.yml up -d phoenix
```

---

### ❌ Traces not appearing in UI

**Possible causes:**
1. Wrong project name
2. Spans not flushed
3. Phoenix started after traces sent

**Fix:**
```python
# In notebook, after running queries:
tracer_provider.force_flush()
print("View at: http://localhost:6006")
```

---

### ❌ "ModuleNotFoundError: No module named 'phoenix'"

**Cause:** Phoenix packages not installed

**Fix:**
```bash
pip install arize-phoenix-otel openinference-instrumentation-langchain
```

---

## Phoenix Ports Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 6006 | HTTP | Phoenix UI & Health checks |
| 4317 | gRPC | OTLP Collector (recommended) |
| 4318 | HTTP | OTLP Collector (alternative) |

---

## Environment Variables

```python
# Required for notebooks (running on HOST, not in Docker)
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]       = "http://localhost:4317"
os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4317"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"]         = "http://localhost:6006"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"]        = "grpc"
```

**⚠️ Do NOT use:** `http://phoenix:4317` in notebooks (that's for Docker-to-Docker)

---

## Best Practices

### ✅ DO

- Start Phoenix before starting notebook
- Restart kernel between sessions
- Run setup cell only once per kernel
- Call `force_flush()` before checking UI
- Use descriptive project names
- Check Phoenix health before registering

### ❌ DON'T

- Run setup cell multiple times
- Use `phoenix` hostname in notebooks (use `localhost`)
- Forget to flush spans
- Skip health checks
- Mix protocols (stick to gRPC)

---

## Quick Diagnostic Checklist

Run through this checklist when traces aren't appearing:

- [ ] Phoenix container running: `docker ps | grep phoenix`
- [ ] Port 6006 accessible: `curl http://localhost:6006/healthz`
- [ ] Port 4317 open: `nc -zv localhost 4317`
- [ ] Kernel restarted recently
- [ ] Setup cell ran only once
- [ ] No errors in setup cell output
- [ ] `tracer_provider.force_flush()` called
- [ ] Correct project name in UI dropdown
- [ ] Phoenix logs show no errors

---

## Advanced: Using HTTP Protocol Instead of gRPC

If gRPC has issues, switch to HTTP:

```python
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]  = "http://localhost:4318"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"]   = "http/protobuf"

tracer_provider = register(
    project_name="your-project",
    endpoint="http://localhost:4318",
    protocol="http/protobuf",
    auto_instrument=False,
)
```

---

## Getting Help

1. **Read:** `FIX_PHOENIX_EXPORT.md` for detailed troubleshooting
2. **Run:** `python notebook/diagnose_phoenix.py` for automated diagnostics
3. **Check:** Phoenix Docker logs: `docker compose -f docker-compose-infra.yml logs phoenix`
4. **Test:** Use improved setup from `phoenix_setup_improved.py`

---

## Phoenix UI URLs

- **Main UI:** http://localhost:6006
- **Health Check:** http://localhost:6006/healthz
- **Projects:** http://localhost:6006/projects
- **Your Project:** http://localhost:6006/projects/industry-rs

---

## Summary

**The Golden Rule:**

```
1. Start Phoenix first
2. Start notebook kernel
3. Run setup cell ONCE
4. Never re-run setup cell
5. Restart kernel if config changes needed
```

This ensures a clean `TracerProvider` lifecycle and proper trace export.

---

**Last Updated:** 2026-09-07  
**Related Docs:** `LOCAL_INSTALL.md`, `QUICK_START.md`, `docker-compose-infra.yml`
