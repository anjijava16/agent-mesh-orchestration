#!/usr/bin/env python3
"""
Phoenix Connection Diagnostic Tool
===================================

Run this script to diagnose Phoenix connectivity issues:
    python notebook/diagnose_phoenix.py

Or in notebook:
    %run notebook/diagnose_phoenix.py
"""

import os
import sys
import socket
import urllib.request
from typing import Tuple, Optional


def check_port(host: str, port: int, timeout: float = 2.0) -> Tuple[bool, str]:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return True, f"✅ Port {port} is OPEN"
        else:
            return False, f"❌ Port {port} is CLOSED or not reachable"
    except Exception as e:
        return False, f"❌ Port {port} check failed: {e}"


def check_http_endpoint(url: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """Check if an HTTP endpoint is reachable."""
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            if status == 200:
                return True, f"✅ {url} returned 200 OK"
            else:
                return False, f"⚠️  {url} returned status {status}"
    except urllib.error.HTTPError as e:
        return False, f"❌ HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"❌ URL Error: {e.reason}"
    except Exception as e:
        return False, f"❌ Request failed: {e}"


def check_env_vars() -> dict:
    """Check relevant environment variables."""
    relevant_vars = [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "PHOENIX_COLLECTOR_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
    ]
    
    result = {}
    for var in relevant_vars:
        value = os.environ.get(var)
        result[var] = value if value else "(not set)"
    
    return result


def check_docker_phoenix() -> Tuple[bool, str]:
    """Check if Phoenix container is running via Docker."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=phoenix", "--format", "{{.Names}} - {{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                return True, f"✅ Phoenix container running: {output}"
            else:
                return False, "❌ No Phoenix container found"
        else:
            return False, f"❌ Docker command failed: {result.stderr}"
            
    except FileNotFoundError:
        return False, "⚠️  Docker command not found (is Docker installed?)"
    except Exception as e:
        return False, f"❌ Docker check failed: {e}"


def main():
    print("="*70)
    print(" Phoenix Connection Diagnostic")
    print("="*70)
    print()
    
    # 1. Check Docker container
    print("1️⃣  Checking Docker container...")
    success, msg = check_docker_phoenix()
    print(f"   {msg}")
    if not success:
        print("   💡 Start Phoenix: docker compose -f docker-compose-infra.yml up -d phoenix")
    print()
    
    # 2. Check ports
    print("2️⃣  Checking ports...")
    ports = {
        6006: "Phoenix UI",
        4317: "OTLP gRPC Collector",
        4318: "OTLP HTTP Collector",
    }
    
    any_port_open = False
    for port, desc in ports.items():
        success, msg = check_port("localhost", port)
        print(f"   {msg} ({desc})")
        if success:
            any_port_open = True
    
    if not any_port_open:
        print("   ⚠️  No Phoenix ports are open!")
        print("   💡 Start Phoenix: docker compose -f docker-compose-infra.yml up -d phoenix")
    print()
    
    # 3. Check HTTP endpoints
    print("3️⃣  Checking HTTP endpoints...")
    endpoints = {
        "http://localhost:6006/healthz": "Health check",
        "http://localhost:6006": "UI homepage",
    }
    
    for url, desc in endpoints.items():
        success, msg = check_http_endpoint(url)
        print(f"   {msg} ({desc})")
    print()
    
    # 4. Check environment variables
    print("4️⃣  Checking environment variables...")
    env_vars = check_env_vars()
    for var, value in env_vars.items():
        symbol = "✅" if value != "(not set)" else "⚠️ "
        print(f"   {symbol} {var}={value}")
    print()
    
    # 5. Test OTLP connectivity
    print("5️⃣  Testing OTLP gRPC connectivity...")
    try:
        from phoenix.otel import register
        from opentelemetry.trace import Status, StatusCode
        
        print("   📡 Attempting to register tracer...")
        
        # Set environment for test
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4317"
        os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = "grpc"
        
        tracer_provider = register(
            project_name="diagnostic-test",
            endpoint="http://localhost:4317",
            protocol="grpc",
            auto_instrument=False,
        )
        
        tracer = tracer_provider.get_tracer("diagnostic")
        
        print("   📤 Sending test span...")
        with tracer.start_as_current_span("diagnostic-test-span") as span:
            span.set_attribute("diagnostic", "connection-test")
            span.set_status(Status(StatusCode.OK))
        
        tracer_provider.force_flush(timeout_millis=5000)
        
        print("   ✅ Test span sent successfully!")
        print("   💡 Check Phoenix UI: http://localhost:6006/projects")
        
        # Clean up
        tracer_provider.shutdown()
        
    except ImportError:
        print("   ⚠️  arize-phoenix-otel not installed")
        print("   💡 Install: pip install arize-phoenix-otel")
    except Exception as e:
        print(f"   ❌ OTLP test failed: {e}")
        print("   💡 Make sure Phoenix is running and ports are accessible")
    
    print()
    
    # Summary
    print("="*70)
    print(" Summary")
    print("="*70)
    
    if any_port_open:
        print("✅ Phoenix appears to be running")
        print("   If traces still don't appear:")
        print("   1. Restart Jupyter kernel")
        print("   2. Run Phoenix setup cell ONCE")
        print("   3. Check Phoenix logs: docker compose -f docker-compose-infra.yml logs phoenix")
    else:
        print("❌ Phoenix is NOT running")
        print("   To fix:")
        print("   1. docker compose -f docker-compose-infra.yml up -d phoenix")
        print("   2. Wait 10-15 seconds for startup")
        print("   3. Re-run this diagnostic")
    
    print()
    print("📚 Documentation: notebook/FIX_PHOENIX_EXPORT.md")
    print("="*70)


if __name__ == "__main__":
    main()
