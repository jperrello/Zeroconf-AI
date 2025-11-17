import socket
import threading
import time
import argparse
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import requests
from zeroconf import ServiceListener, ServiceBrowser, Zeroconf
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class AIService:
    name: str
    address: str
    port: int
    priority: int
    last_seen: datetime = field(default_factory=datetime.now)
    is_healthy: bool = False
    available_models: List[str] = field(default_factory=list)
    first_check_complete: bool = False
    
    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "priority": self.priority,
            "is_healthy": self.is_healthy,
            "models": self.available_models,
            "last_seen": self.last_seen.isoformat()
        }

class ServiceDiscovery:
    def __init__(self):
        self.services: Dict[str, AIService] = {}
        self.lock = threading.Lock()
        self.zc = Zeroconf()
        self.listener = self._create_listener()
        # this is where we actively listen for _saturn._tcp.local. broadcasts on the network
        self.browser = ServiceBrowser(self.zc, "_saturn._tcp.local.", self.listener)
    
    def _create_listener(self) -> ServiceListener:
        discovery = self
        
        class Listener(ServiceListener):
            # whenever a new zeroconf service appears, we capture its details here
            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if info and info.port:
                    address = socket.inet_ntoa(info.addresses[0])
                    port = info.port
                    priority = info.priority if info.priority else 50
                    
                    with discovery.lock:
                        discovery.services[name] = AIService(
                            name=name,
                            address=address,
                            port=port,
                            priority=priority
                        )
                    logger.info(f"Discovered: {name} at {address}:{port}")
            
            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.add_service(zc, type_, name)
            
            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                with discovery.lock:
                    if name in discovery.services:
                        del discovery.services[name]
                        logger.info(f"Removed: {name}")
        
        return Listener()
    
    def get_all_services(self) -> List[AIService]:
        with self.lock:
            return list(self.services.values())
    
    def get_service(self, name: str) -> Optional[AIService]:
        with self.lock:
            return self.services.get(name)
    
    def get_service_by_partial_name(self, partial_name: str) -> Optional[AIService]:
        with self.lock:
            partial_lower = partial_name.lower()
            for name, service in self.services.items():
                if partial_lower in name.lower():
                    return service
            return None
    
    def stop(self):
        self.browser.cancel()
        self.zc.close()

class HealthMonitor:
    def __init__(self, discovery: ServiceDiscovery, check_interval: int = 10):
        self.discovery = discovery
        self.check_interval = check_interval
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    # continuously checking if discovered services are actually alive
    def _monitor_loop(self):
        while self.running:
            services = self.discovery.get_all_services()
            
            for service in services:
                was_healthy = service.is_healthy
                service.is_healthy = self._check_health(service.url)
                service.last_seen = datetime.now()
                
                if service.is_healthy:
                    service.available_models = self._fetch_models(service.url)
                
                if service.first_check_complete and service.is_healthy != was_healthy:
                    status = "healthy" if service.is_healthy else "unhealthy"
                    logger.info(f"{service.name} is now {status}")
                
                service.first_check_complete = True
            
            time.sleep(self.check_interval)
    
    def _check_health(self, url: str) -> bool:
        try:
            response = requests.get(f"{url}/v1/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def _fetch_models(self, url: str) -> List[str]:
        try:
            response = requests.get(f"{url}/v1/models", timeout=3)
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to fetch models from {url}: {e}")
        return []
    
    def stop(self):
        self.running = False

class BridgeManager:
    def __init__(self):
        self.discovery = ServiceDiscovery()
        self.health_monitor = HealthMonitor(self.discovery)
    
    def get_healthy_services(self) -> List[AIService]:
        services = self.discovery.get_all_services()
        return [s for s in services if s.is_healthy]
    
    # priority-based routing - lowest priority number wins (like dns records)
    def get_best_service(self) -> Optional[AIService]:
        services = self.get_healthy_services()
        if not services:
            return None
        return min(services, key=lambda s: s.priority)
    
    def get_service_by_name(self, name: str) -> Optional[AIService]:
        service = self.discovery.get_service(name)
        if service and service.is_healthy:
            return service
        
        service = self.discovery.get_service_by_partial_name(name)
        if service and service.is_healthy:
            return service
        
        return None
    
    def stop(self):
        self.health_monitor.stop()
        self.discovery.stop()

bridge_manager: Optional[BridgeManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge_manager
    bridge_manager = BridgeManager()
    logger.info("Discovery bridge started")
    time.sleep(2)
    
    yield
    
    if bridge_manager:
        bridge_manager.stop()
        logger.info("Discovery bridge stopped")

app = FastAPI(
    title="VLC AI Discovery Bridge",
    description="Bridge between VLC Lua extension and Saturn services",
    version="1.0",
    lifespan=lifespan
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    stream: bool = False
    service: Optional[str] = None

@app.get("/")
async def root():
    return {
        "service": "VLC AI Discovery Bridge",
        "status": "running",
        "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/health", "/services"]
    }

@app.get("/services")
async def get_services():
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")
    
    services = bridge_manager.get_healthy_services()
    return {
        "count": len(services),
        "services": [s.to_dict() for s in services],
        "best": bridge_manager.get_best_service().to_dict() if bridge_manager.get_best_service() else None
    }

@app.get("/v1/health")
async def health():
    if not bridge_manager:
        return {"status": "starting"}
    
    services = bridge_manager.get_healthy_services()
    return {
        "status": "ready" if services else "no_services",
        "healthy_services": len(services),
        "total_services": len(bridge_manager.discovery.services)
    }

@app.get("/v1/models")
async def get_models():
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")

    services = bridge_manager.get_healthy_services()
    if not services:
        raise HTTPException(status_code=503, detail="No AI services available")

    all_models = []
    for service in services:
        for model_id in service.available_models:
            all_models.append({
                "id": model_id,
                "object": "model",
                "owned_by": service.name
            })

    return {"models": all_models}

@app.post("/shutdown")
async def shutdown():
    """Shutdown endpoint for clean bridge termination from Lua"""
    logger.info("Shutdown requested")

    # Schedule shutdown after returning response
    def stop_server():
        time.sleep(0.5)  # Give time for response to be sent
        os._exit(0)

    threading.Thread(target=stop_server, daemon=True).start()

    return {"status": "shutting_down"}

# vlc's lua can't do post easily, so we support both get and post for chat completions
@app.get("/v1/chat/completions")
async def chat_completions_get(payload: str, service: Optional[str] = None, raw_request: Request = None):
    import urllib.parse
    try:
        decoded_payload = urllib.parse.unquote_plus(payload)
        request_data = json.loads(decoded_payload)
        
        if service:
            request_data["service"] = service
        
        chat_request = ChatRequest(**request_data)
        return await chat_completions_core(chat_request, raw_request)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in payload parameter: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse request: {str(e)}")

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, raw_request: Request):
    return await chat_completions_core(request, raw_request)

# this is where the bridge decides which discovered service to route the request to
async def chat_completions_core(request: ChatRequest, raw_request: Request):
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")
    
    service = None
    
    # user can explicitly request a specific service, otherwise we pick the best one by priority
    if request.service:
        service = bridge_manager.get_service_by_name(request.service)
        if not service:
            raise HTTPException(
                status_code=404, 
                detail=f"Requested service '{request.service}' not found or unhealthy"
            )
    else:
        service = bridge_manager.get_best_service()
        if not service:
            raise HTTPException(status_code=503, detail="No AI services available")
    
    model = request.model
    if not model and service.available_models:
        model = service.available_models[0]
    
    if not model:
        raise HTTPException(status_code=503, detail="No models available on selected service")
    
    payload = {
        "model": model,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "stream": request.stream
    }
    
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    
    logger.info(f"Routing chat to {service.name} using model {model}")
    
    try:
        # forwarding the actual request to the selected zeroconf service
        response = requests.post(
            f"{service.url}/v1/chat/completions",
            json=payload,
            timeout=60,
            stream=request.stream
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"AI service error: {response.text}")
        
        if request.stream:
            async def generate():
                try:
                    for chunk in response.iter_content(chunk_size=None):
                        if await raw_request.is_disconnected():
                            break
                        if chunk:
                            yield chunk
                finally:
                    response.close()
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            return response.json()
    
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to AI service: {str(e)}")

def find_port_number(host: str, start_port: int = 9876, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"No available ports in range {start_port} - {start_port + max_attempts}"
    )

def wait_for_server_ready(host: str, port: int, timeout: int = 15) -> bool:
    """Poll the server until it's ready to accept connections"""
    url = f"http://{host}:{port}/v1/health"
    start_time = time.time()
    attempt = 0

    logger.info(f"Waiting for server to be ready at {url}...")

    while time.time() - start_time < timeout:
        attempt += 1
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Server is ready! (attempt {attempt}, status: {data.get('status', 'unknown')})")
                # Extra verification - make sure we can actually handle requests
                time.sleep(0.2)  # Small safety margin
                return True
            else:
                logger.debug(f"Server responded but not ready (status {response.status_code})")
        except requests.exceptions.ConnectionError:
            # Server not ready yet, continue waiting
            logger.debug(f"Connection attempt {attempt} failed (server not ready)")
        except requests.exceptions.Timeout:
            logger.debug(f"Connection attempt {attempt} timed out")
        except Exception as e:
            logger.debug(f"Connection attempt {attempt} error: {e}")

        time.sleep(0.3)  # Wait 300ms between attempts

    logger.error(f"Server failed to become ready after {timeout}s ({attempt} attempts)")
    return False

def main():
    parser = argparse.ArgumentParser(description="VLC AI Discovery Bridge")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=None, help="Port to bind to (auto-detect if not specified)")
    parser.add_argument("--port-file", type=str, default=None, help="File to write host:port to for Lua discovery")
    args = parser.parse_args()

    try:
        port = args.port if args.port else find_port_number(args.host)
    except RuntimeError as e:
        logger.error(f"Failed to find available port: {e}")
        sys.exit(1)

    print("=" * 50)
    print("  VLC AI Discovery Bridge")
    print("=" * 50)
    print(f"Starting on {args.host}:{port}")
    print(f"Discovering Saturn services...")
    if args.port_file:
        print(f"Port file: {args.port_file}")
    print()

    # Start uvicorn in a background thread
    logger.info(f"Starting FastAPI server on {args.host}:{port}...")
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app,
            host=args.host,
            port=port,
            log_level="info",
            access_log=False  # Reduce log noise
        ),
        daemon=True
    )
    server_thread.start()

    # CRITICAL: Wait for the server to be ready before writing the port file
    # This ensures that when Lua reads the port file, the server is guaranteed to be accepting connections
    logger.info("Waiting for server to be ready...")
    if not wait_for_server_ready(args.host, port, timeout=15):
        logger.error("Server failed to start within timeout period")
        logger.error("Check for port conflicts or firewall issues")
        sys.exit(1)

    # NOW write port information to file (server is confirmed ready)
    # Lua will wait for this file to appear, then wait an additional safety margin
    if args.port_file:
        try:
            # Ensure directory exists
            port_file_dir = os.path.dirname(args.port_file)
            if port_file_dir and not os.path.exists(port_file_dir):
                os.makedirs(port_file_dir, exist_ok=True)

            with open(args.port_file, 'w') as f:
                f.write(f"{args.host}:{port}")
            logger.info(f"Port information written to {args.port_file}")
            logger.info("Bridge is ready for VLC connections!")
        except Exception as e:
            logger.error(f"Failed to write port file: {e}")
            sys.exit(1)
    else:
        logger.info("Bridge is ready!")

    # Keep the main thread alive while server runs
    logger.info("Bridge running. Press Ctrl+C to stop.")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Clean up port file on exit if it was created
        if args.port_file and os.path.exists(args.port_file):
            try:
                os.remove(args.port_file)
                logger.info(f"Cleaned up port file {args.port_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up port file: {e}")

if __name__ == "__main__":
    main()