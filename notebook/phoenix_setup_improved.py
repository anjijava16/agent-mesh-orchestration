"""
Improved Phoenix/OpenTelemetry Setup for Jupyter Notebooks
===========================================================

Copy this cell into your notebook to replace the existing Phoenix setup.
This version includes:
- Phoenix health checks before registration
- Graceful degradation if Phoenix is unavailable
- Better error handling
- Dummy tracer for offline development

Usage:
1. Restart kernel
2. Run this cell ONCE
3. Run rest of notebook
"""

import os
import sys

# ---------------------------------------------------------------------------
# Phoenix / OpenTelemetry — ROBUST ONE-TIME SETUP
# ---------------------------------------------------------------------------

# Force localhost endpoints (notebook runs on HOST, not in Docker)
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]       = "http://localhost:4317"
os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4317"
os.environ["PHOENIX_COLLECTOR_ENDPOINT"]         = "http://localhost:6006"
os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"]        = "grpc"

# Remove conflicting env vars
for key in ["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"]:
    os.environ.pop(key, None)

PHOENIX_UI   = "http://localhost:6006"
PROJECT_NAME = "industry-rs"

# ---------------------------------------------------------------------------
# Helper: Check Phoenix Health
# ---------------------------------------------------------------------------
def check_phoenix_health() -> bool:
    """Verify Phoenix is running and reachable."""
    import urllib.request
    import socket
    
    try:
        # First check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 6006))
        sock.close()
        
        if result != 0:
            print(f"⚠️  Port 6006 is not open")
            return False
        
        # Then check HTTP health endpoint
        with urllib.request.urlopen(f"{PHOENIX_UI}/healthz", timeout=5) as response:
            if response.status == 200:
                print(f"✅ Phoenix is healthy at {PHOENIX_UI}")
                return True
            else:
                print(f"⚠️  Phoenix returned status {response.status}")
                return False
                
    except Exception as e:
        print(f"⚠️  Phoenix not reachable: {e}")
        print(f"   Start Phoenix: docker compose -f docker-compose-infra.yml up -d phoenix")
        print(f"   Or: ./start-local.sh")
        return False


# ---------------------------------------------------------------------------
# Dummy Tracer for Offline Development
# ---------------------------------------------------------------------------
class DummySpan:
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def set_status(self, *args, **kwargs):
        pass
    
    def set_attribute(self, *args, **kwargs):
        pass


class DummyTracer:
    def start_as_current_span(self, name, **kwargs):
        return DummySpan()
    
    def get_tracer(self, name):
        return self


class DummyProvider:
    def force_flush(self, *args, **kwargs):
        pass
    
    def get_tracer(self, name):
        return DummyTracer()
    
    def shutdown(self):
        pass


# ---------------------------------------------------------------------------
# Main Setup Logic
# ---------------------------------------------------------------------------
if not globals().get("_phoenix_ready"):
    # Check if Phoenix is running
    phoenix_available = check_phoenix_health()
    
    if not phoenix_available:
        print("❌ Cannot connect to Phoenix. Tracing will be disabled.")
        print(f"   Expected Phoenix at: {PHOENIX_UI}")
        print("   Notebook will continue without observability.")
        
        # Set dummy tracer to avoid errors in rest of notebook
        tracer_provider = DummyProvider()
        tracer = DummyTracer()
        _phoenix_ready = False
        
    else:
        # Phoenix is available, register for real
        try:
            from phoenix.otel import register
            from openinference.instrumentation.langchain import LangChainInstrumentor
            
            print("📡 Registering OpenTelemetry tracer with Phoenix...")
            
            tracer_provider = register(
                project_name=PROJECT_NAME,
                endpoint="http://localhost:4317",
                protocol="grpc",
                auto_instrument=False,  # Manual instrumentation for better control
            )
            
            # Instrument LangChain/LangGraph
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            
            tracer = tracer_provider.get_tracer(__name__)
            _phoenix_ready = True
            
            print(f"🔭 Phoenix tracing registered → project '{PROJECT_NAME}'")
            print(f"   UI: {PHOENIX_UI}")
            
            # Send test span to verify connectivity
            with tracer.start_as_current_span("phoenix-connectivity-check") as span:
                span.set_attribute("test", "initial-connection")
                span.set_attribute("notebook", "agentic-rag")
            
            tracer_provider.force_flush(timeout_millis=5000)
            print("✅ Test span sent successfully")
            print(f"   View at: {PHOENIX_UI}/projects")
            
        except Exception as e:
            print(f"❌ Failed to register Phoenix: {e}")
            print("   Continuing without tracing...")
            
            # Fallback to dummy tracer
            tracer_provider = DummyProvider()
            tracer = DummyTracer()
            _phoenix_ready = False

else:
    print(f"ℹ️  Phoenix already registered → project '{PROJECT_NAME}' @ {PHOENIX_UI}")
    print("   ⚠️  If seeing 'Exporter shutdown' errors:")
    print("      1. Kernel → Restart Kernel")
    print("      2. Re-run this cell")

# ---------------------------------------------------------------------------
# Export for use in rest of notebook
# ---------------------------------------------------------------------------
print("\n" + "="*70)
if _phoenix_ready:
    print("✅ Phoenix observability ENABLED")
    print(f"   All LangChain/LangGraph operations will be traced")
    print(f"   View traces at: {PHOENIX_UI}")
else:
    print("⚠️  Phoenix observability DISABLED")
    print("   Notebook will run normally without tracing")
    print("   To enable: start Phoenix and restart kernel")
print("="*70 + "\n")
