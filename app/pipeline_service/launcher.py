#!/usr/bin/env python3
"""
Launcher Script - Starts all services for the Intelligent Archiving Platform
This script launches all Python services and waits for them to be ready
before starting the unified Pipeline Service.
"""
import subprocess
import sys
import time
import os
import signal
from pathlib import Path
import requests
import threading

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
OCR_SERVICE = PROJECT_ROOT / "ocr_service"
CHUNK_SERVICE = PROJECT_ROOT / "chunk_service"
EMBEDDING_SERVICE = PROJECT_ROOT / "embendding_service"
STORAGE_SERVICE = PROJECT_ROOT / "storage_service"
PIPELINE_SERVICE = PROJECT_ROOT / "app" / "pipeline_service"

# Service configurations
SERVICES = [
    {
        "name": "Storage Service",
        "port": 8003,
        "cwd": str(STORAGE_SERVICE),
        "command": [sys.executable, "api_server.py"],
        "health_endpoint": "/health"
    },
    {
        "name": "OCR Service",
        "port": 8000,
        "cwd": str(OCR_SERVICE),
        "command": [sys.executable, "api_server.py"],
        "health_endpoint": "/health"
    },
    {
        "name": "Chunk Service",
        "port": 8001,
        "cwd": str(CHUNK_SERVICE),
        "command": [sys.executable, "api_server.py"],
        "health_endpoint": "/health"
    },
    {
        "name": "Embedding Service",
        "port": 8002,
        "cwd": str(EMBEDDING_SERVICE),
        "command": [sys.executable, "api_server.py"],
        "health_endpoint": "/health"
    }
]

# Store running processes
running_processes = []

def print_banner():
    """Print startup banner"""
    print("\n" + "="*70)
    print("  Intelligent Archiving Platform - Service Launcher")
    print("="*70)
    print(f"\nProject Root: {PROJECT_ROOT}")
    print(f"Python: {sys.executable}")
    print(f"Python Version: {sys.version}")
    print("\n")

def check_service_ready(port, timeout=60):
    """Check if a service is ready by polling its health endpoint"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

def start_service(service_config):
    """Start a single service"""
    name = service_config["name"]
    port = service_config["port"]
    cwd = service_config["cwd"]
    command = service_config["command"]
    
    print(f"Starting {name} on port {port}...")
    print(f"  Working directory: {cwd}")
    print(f"  Command: {' '.join(command)}")
    
    try:
        # Start the service
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        
        running_processes.append(process)
        
        # Wait for service to be ready
        print(f"  Waiting for {name} to be ready...")
        if check_service_ready(port):
            print(f"  ✓ {name} is ready!\n")
            return process
        else:
            print(f"  ✗ {name} failed to start within timeout period\n")
            return None
            
    except Exception as e:
        print(f"  ✗ Failed to start {name}: {e}\n")
        return None

def cleanup(signum=None, frame=None):
    """Cleanup all running services"""
    print("\n" + "="*70)
    print("  Shutting down all services...")
    print("="*70 + "\n")
    
    for i, process in enumerate(running_processes):
        service_name = SERVICES[i]["name"] if i < len(SERVICES) else f"Process {i}"
        print(f"Stopping {service_name} (PID: {process.pid})...")
        try:
            if os.name == 'nt':
                process.terminate()
            else:
                process.terminate()
            process.wait(timeout=5)
            print(f"  ✓ {service_name} stopped")
        except Exception as e:
            print(f"  ✗ Error stopping {service_name}: {e}")
            try:
                process.kill()
            except:
                pass
    
    print("\nAll services stopped.")
    sys.exit(0)

def main():
    """Main launcher function"""
    print_banner()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Check if all service directories exist
    print("Checking service directories...")
    for service in SERVICES:
        cwd = Path(service["cwd"])
        if not cwd.exists():
            print(f"  ✗ {service['name']} directory not found: {cwd}")
            return
        print(f"  ✓ {service['name']}: {cwd}")
    print()
    
    # Start all services
    print("="*70)
    print("  Starting Services")
    print("="*70 + "\n")
    
    successful = 0
    for service in SERVICES:
        process = start_service(service)
        if process:
            successful += 1
        else:
            print(f"Failed to start {service['name']}")
    
    # Check if all services started successfully
    if successful != len(SERVICES):
        print(f"\n⚠ Warning: Only {successful}/{len(SERVICES)} services started successfully")
        print("Continuing anyway...\n")
    else:
        print(f"\n✓ All {len(SERVICES)} services started successfully!\n")
    
    # Print service status
    print("="*70)
    print("  Service Status")
    print("="*70)
    for service in SERVICES:
        port = service["port"]
        name = service["name"]
        print(f"  {name:25s} → http://localhost:{port}")
    print("="*70 + "\n")
    
    # Start the Pipeline Service
    print("="*70)
    print("  Starting Pipeline Service")
    print("="*70 + "\n")
    
    print(f"Starting Pipeline Service on port 8082...")
    pipeline_process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(PIPELINE_SERVICE),
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )
    
    running_processes.append(pipeline_process)
    
    print(f"  ✓ Pipeline Service started (PID: {pipeline_process.pid})")
    print(f"  → http://localhost:8082\n")
    
    # Final status
    print("="*70)
    print("  All Services Running")
    print("="*70)
    print(f"\n  Pipeline Service:     http://localhost:8082")
    print(f"  Storage Service:      http://localhost:8003")
    print(f"  OCR Service:          http://localhost:8000")
    print(f"  Chunk Service:        http://localhost:8001")
    print(f"  Embedding Service:    http://localhost:8002")
    print(f"\n  Health Check:         http://localhost:8082/health")
    print(f"\n  Press Ctrl+C to stop all services\n")
    print("="*70 + "\n")
    
    # Wait for all processes
    try:
        for process in running_processes:
            process.wait()
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"\n✗ Launcher failed: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
