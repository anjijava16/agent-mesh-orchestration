# Fix: "Exporter already shutdown, ignoring batch" - Phoenix/Arize Not Exporting Metrics

## Problem
Notebook shows error: `Exporter already shutdown, ignoring batch` and metrics are not appearing in Phoenix UI.

## Root Causes

### 1. **Multiple Registrations in Same Kernel**
- OpenTelemetry allows only ONE global TracerProvider per Python process
- Running the Phoenix setup cell multiple times shuts down the previous exporter
- Each re-registration invalidates the old exporter

### 2. **Phoenix Service Not Running**
- Phoenix Docker container must be running before notebook starts sending traces
- If Phoenix starts AFTER traces are sent, they're lost

### 3. **Network/Port Issues**
- Notebook runs on HOST, but Phoenix runs in Docker
- Must use `localhost` not `phoenix` hostname
- Ports 4317 (gRPC) and 6006 (UI) must be accessible

### 4. **Protocol Mismatch**
- Phoenix OTLP collector supports both gRPC (4317) and HTTP (4318)
- Notebook must use matching protocol

---

## Solutions

### ✅ Solution 1: Restart Kernel (Recommended)

If you see the "Exporter already shutdown" error:

```python
# In Jupyter/VSCode:
# 1. Kernel → Restart Kernel
# 2. Run setup cell ONCE
# 3. Run rest of notebook
```

**Why this works:** Fresh kernel = no previous TracerProvider = clean registration

---

### ✅ Solution 2: Verify Phoenix is Running

```bash
# Check if Phoenix container is running
docker ps | grep phoenix

# Check Phoenix health
curl http://localhost:6006/healthz

# Start Phoenix if not running
docker compose -f docker-compose-infra.yml up -d phoenix

# View Phoenix logs
docker compose -f docker-compose-infra.yml logs -f phoenix
```

**Phoenix should show:**
```
phoenix_1  | INFO:     Uvicorn running on http://0.0.0.0:6006
phoenix_1  | INFO:     OTLP gRPC collector listening on 0.0.0.0:4317
```

---

### ✅ Solution 3: Enhanced Notebook Setup Cell

Replace the Phoenix setup cell with this improved version:

```python
import os
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Phoenix / OpenTelemetry — ROBUST ONE-TIME SETUP
# ---------------------------------------------------------------------------

# Force localhost endpoints (notebook runs on HOST, not in Docker)
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]       = "http://localhost:4317"
os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4317"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"]         = "http://localhost:6006"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"]        = "grpc"

# Remove conflicting env vars
os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", None)

PHOENIX_UI   = "http://localhost:6006"
PROJECT_NAME = "industry-rs"

# ---------------------------------------------------------------------------
# Check if Phoenix is reachable before registering
# ---------------------------------------------------------------------------
def check_phoenix_health() -> bool:
    """Verify Phoenix is running and reachable."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{PHOENIX_UI}/healthz", timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"⚠️  Phoenix not reachable: {e}")
        print(f"   Start Phoenix: docker compose -f docker-compose-infra.yml up -d phoenix")
        return False


if not globals().get("_phoenix_ready"):
    # Verify Phoenix is running
    if not check_phoenix_health():
        print("❌ Cannot connect to Phoenix. Tracing will be disabled.")
        print(f"   Expected Phoenix at: {PHOENIX_UI}")
        # Set dummy tracer to avoid errors in rest of notebook
        class DummySpan:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def set_status(self, *args): pass
        
        class DummyTracer:
            def start_as_current_span(self, name, **kwargs):
                return DummySpan()
            def get_tracer(self, name):
                return self
        
        class DummyProvider:
            def force_flush(self, *args): pass
            def get_tracer(self, name):
                return DummyTracer()
        
        tracer_provider = DummyProvider()
        tracer = DummyTracer()
        _phoenix_ready = False
    else:
        print("✅ Phoenix is reachable")
        
        from phoenix.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor
        
        try:
            # Register with BatchSpanProcessor for production use
            tracer_provider = register(
                project_name=PROJECT_NAME,
                endpoint="http://localhost:4317",
                protocol="grpc",
                auto_instrument=False,
            )
            
            # Instrument LangChain
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            
            tracer = tracer_provider.get_tracer(__name__)
            _phoenix_ready = True
            
            print(f"🔭 Phoenix tracing registered -> project '{PROJECT_NAME}' @ {PHOENIX_UI}")
            
            # Send test span to verify connectivity
            with tracer.start_as_current_span("phoenix-connectivity-check") as span:
                span.set_attribute("test", "initial-connection")
            
            tracer_provider.force_flush()
            print("✅ Test span sent successfully")
            
        except Exception as e:
            print(f"❌ Failed to register Phoenix: {e}")
            print("   Continuing without tracing...")
            # Set dummy objects
            class DummySpan:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def set_status(self, *args): pass
                def set_attribute(self, *args): pass
            
            class DummyTracer:
                def start_as_current_span(self, name, **kwargs):
                    return DummySpan()
            
            class DummyProvider:
                def force_flush(self, *args): pass
                def get_tracer(self, name):
                    return DummyTracer()
            
            tracer_provider = DummyProvider()
            tracer = DummyTracer()
            _phoenix_ready = False
else:
    print(f"ℹ️  Phoenix already registered -> project '{PROJECT_NAME}' @ {PHOENIX_UI}")
    print("   (If seeing 'Exporter shutdown' errors, restart kernel)")
```

---

### ✅ Solution 4: Alternative - Use BatchSpanProcessor

For production notebooks, use batch processing instead of simple processor:

```python
from phoenix.otel import register

tracer_provider = register(
    project_name=PROJECT_NAME,
    endpoint="http://localhost:4317",
    protocol="grpc",
    auto_instrument=False,
)

# The warning message suggests using BatchSpanProcessor for production
# This is already the default in newer versions
```

---

### ✅ Solution 5: Manual Shutdown and Re-register (Last Resort)

If you must re-register without restarting kernel:

```python
# Shutdown existing tracer provider
if globals().get("_phoenix_ready") and globals().get("tracer_provider"):
    try:
        tracer_provider.shutdown()
        print("Shut down existing tracer provider")
    except:
        pass
    
    # Clear the flag
    _phoenix_ready = False

# Now re-run the setup cell
```

**⚠️ Warning:** This is NOT recommended. Prefer kernel restart.

---

## Verification Steps

### 1. Check Phoenix UI
```bash
# Open in browser
open http://localhost:6006

# You should see:
# - Projects list with "industry-rs"
# - Traces appearing in real-time as notebook runs
```

### 2. Verify Traces in Notebook

```python
# After running your RAG queries, check:
print(f"View traces at: {PHOENIX_UI}/projects/{PROJECT_NAME}")

# Force flush to ensure all spans are sent
tracer_provider.force_flush()
```

### 3. Check Docker Logs

```bash
# Phoenix should show incoming spans
docker compose -f docker-compose-infra.yml logs -f phoenix | grep "span"
```

---

## Common Issues & Fixes

### Issue: "Connection refused to localhost:4317"

**Fix:**
```bash
# Check if Phoenix is listening on 4317
docker compose -f docker-compose-infra.yml ps phoenix

# Restart Phoenix
docker compose -f docker-compose-infra.yml restart phoenix

# Check port mapping
docker compose -f docker-compose-infra.yml port phoenix 4317
```

### Issue: Traces not appearing in UI

**Possible causes:**
1. Wrong project name → Check project dropdown in UI
2. Spans not flushed → Call `tracer_provider.force_flush()`
3. Phoenix database issue → Check PostgreSQL is running

**Fix:**
```bash
# Check Phoenix database connection
docker compose -f docker-compose-infra.yml logs phoenix | grep -i postgres

# Restart Phoenix and PostgreSQL
docker compose -f docker-compose-infra.yml restart postgres phoenix
```

### Issue: "Protocol mismatch"

**Fix:**
```python
# Explicitly set protocol in environment
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "grpc"

# OR use HTTP protocol on port 4318
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
```

### Issue: Notebook in Docker, Phoenix in Docker

If your notebook also runs in Docker (not just infrastructure):

```python
# Use Docker service name instead of localhost
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://phoenix:4317"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"]   = "http://phoenix:6006"
```

---

## Best Practices

### 1. **Always Restart Kernel Between Sessions**
```python
# At start of each notebook session:
# Kernel → Restart Kernel & Run All
```

### 2. **Run Setup Cell Only Once**
```python
# The `_phoenix_ready` flag prevents double registration
# Don't manually set it to False unless you know what you're doing
```

### 3. **Use Descriptive Project Names**
```python
# Good: project_name = f"agentic-rag-{datetime.now().strftime('%Y%m%d')}"
# Bad:  project_name = "test"
```

### 4. **Always Flush Before Viewing Results**
```python
# After running experiments
tracer_provider.force_flush()
print(f"View results: {PHOENIX_UI}")
```

### 5. **Check Phoenix Health in Notebook**
```python
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:6006/healthz", timeout=5) as r:
        if r.status == 200:
            print("✅ Phoenix is healthy")
except Exception as e:
    print(f"❌ Phoenix health check failed: {e}")
```

---

## Quick Debug Checklist

- [ ] Phoenix Docker container is running
- [ ] Phoenix UI accessible at http://localhost:6006
- [ ] Port 4317 is open and not blocked by firewall
- [ ] Kernel was restarted before running setup cell
- [ ] Setup cell ran only ONCE in current kernel session
- [ ] No errors in Phoenix Docker logs
- [ ] Test span sent successfully (output shows "Test span sent")
- [ ] Called `tracer_provider.force_flush()` after sending spans

---

## Alternative: Use HTTP Protocol Instead of gRPC

If gRPC continues to have issues:

```python
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]       = "http://localhost:4318"
os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4318"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"]        = "http/protobuf"

tracer_provider = register(
    project_name=PROJECT_NAME,
    endpoint="http://localhost:4318",
    protocol="http/protobuf",  # Use HTTP instead of gRPC
    auto_instrument=False,
)
```

---

## Still Not Working?

1. **Check environment variables:**
```python
print("OTEL_EXPORTER_OTLP_ENDPOINT:", os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))
print("PHOENIX_COLLECTOR_ENDPOINT:", os.environ.get("PHOENIX_COLLECTOR_ENDPOINT"))
```

2. **Enable debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

3. **Test with simple span:**
```python
with tracer.start_as_current_span("debug-test") as span:
    span.set_attribute("debug", "testing-connection")
    print("Span created")

tracer_provider.force_flush(timeout_millis=5000)
print("Flushed - check Phoenix UI now")
```

4. **Check Phoenix logs for errors:**
```bash
docker compose -f docker-compose-infra.yml logs phoenix --tail=100
```

---

## Summary

**The golden rule:** 
1. Start Phoenix first
2. Start kernel
3. Run setup cell ONCE
4. Never re-run setup cell
5. Restart kernel if you need to change configuration

This ensures a clean TracerProvider lifecycle and proper trace export to Phoenix.
