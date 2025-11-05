import argparse
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Literal
import uvicorn
import requests
from zeroconf import ServiceListener, ServiceBrowser, Zeroconf
import logging
import json

#used for when i was debugging, there are so many logs now that I am just keeping them. they are going to be commented out for now.
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class Service:
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

class ServiceDiscovery:
    def __init__(self):
        self.services: Dict[str, Service] = {}
        self.lock = threading.Lock()
        self.zc = Zeroconf()
        self.listener = self._create_listener()
        self.browser = ServiceBrowser(self.zc, "_zeroconfai._tcp.local.", self.listener)

    def _create_listener(self) -> ServiceListener:
        discovery = self

        class Listener(ServiceListener):
            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if info and info.port:
                    address = socket.inet_ntoa(info.addresses[0])
                    port = info.port
                    priority = info.priority if info.priority else 50

                    with discovery.lock:
                        discovery.services[name] = Service(
                            name=name,
                            address=address,
                            port=port,
                            priority=priority
                        )
                    logger.info(f"Discovered service: {name} at {address}:{port} (priority: {priority})")

            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.add_service(zc, type_, name)

            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                with discovery.lock:
                    if name in discovery.services:
                        del discovery.services[name]
                        logger.info(f"Removed service: {name}")

        return Listener()

    def get_all_services(self) -> List[Service]:
        with self.lock:
            return list(self.services.values())

    def get_service(self, name: str) -> Optional[Service]:
        with self.lock:
            return self.services.get(name)

    def stop(self):
        self.browser.cancel()
        self.zc.close()

class HealthMonitor:
    def __init__(self, discovery: ServiceDiscovery, check_interval: int = 20):
        self.discovery = discovery
        self.check_interval = check_interval
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

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
            response = requests.get(f"{url}/v1/health", timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def _fetch_models(self, url: str) -> List[str]:
        try:
            response = requests.get(f"{url}/v1/models", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to fetch models from {url}: {e}")
        return []

    def stop(self):
        self.running = False

class ModelRouter:
    def __init__(self, discovery: ServiceDiscovery):
        self.discovery = discovery

    def get_all_models(self) -> Dict[str, List[Dict[str, str]]]:
        services = self.discovery.get_all_services()
        healthy_services = [s for s in services if s.is_healthy]
        
        all_models = []
        model_to_services: Dict[str, List[str]] = {}
        
        for service in healthy_services:
            for model_id in service.available_models:
                if model_id not in model_to_services:
                    model_to_services[model_id] = []
                    all_models.append({
                        "id": model_id,
                        "object": "model",
                        "owned_by": service.name
                    })
                model_to_services[model_id].append(service.name)
        
        return {"models": all_models}

    def get_service_for_model(self, model_id: str) -> Optional[Service]:
        services = self.discovery.get_all_services()
        healthy_services = [s for s in services if s.is_healthy]
        
        candidates = [s for s in healthy_services if model_id in s.available_models]
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda s: s.priority)
        return candidates[0]

    def route_request(self, model_id: str, request_data: dict, max_retries: int = 2):
        services = self.discovery.get_all_services()
        healthy_services = [s for s in services if s.is_healthy]
        
        candidates = [s for s in healthy_services if model_id in s.available_models]
        
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not found in any available service"
            )
        
        candidates.sort(key=lambda s: s.priority)
        
        is_streaming = request_data.get("stream", False)
        
        #logger.info(f"Request streaming mode: {is_streaming}")
        #logger.debug(f"Full request data: {json.dumps(request_data, indent=2)}")
        
        last_error = None
        for service in candidates[:max_retries]:
            try:
                logger.info(f"Routing '{model_id}' request to {service.name} at {service.url}")
                
                #this is where the proxy receives the request and forwards it to the selected service
                response = requests.post(
                    f"{service.url}/v1/chat/completions",
                    json=request_data,
                    timeout=120,
                    stream=is_streaming #crucial
                )
                
                logger.info(f"Response status: {response.status_code}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                
                response.raise_for_status()
                
                if is_streaming:
                    logger.info(f"Returning streaming response from {service.name}")
                    return response
                else:
                    try:
                        result = response.json()
                        logger.debug(f"Non-streaming response: {json.dumps(result, indent=2)[:500]}")
                        
                        if not result.get("choices"):
                            raise ValueError(f"Invalid response format: missing 'choices' field")
                        
                        logger.info(f"Successfully routed to {service.name}")
                        return result
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        logger.error(f"Response text: {response.text[:1000]}")
                        raise ValueError(f"Service returned invalid JSON: {str(e)}")
                
            except requests.Timeout:
                last_error = f"Service {service.name} timed out"
                logger.warning(last_error)
            except ValueError as e:
                last_error = f"Service {service.name} returned invalid format: {str(e)}"
                logger.warning(last_error)
            except Exception as e:
                last_error = f"Service {service.name} failed: {str(e)}"
                logger.error(f"Exception details: {type(e).__name__}: {str(e)}")
        
        raise HTTPException(
            status_code=502,
            detail=f"All services failed for model '{model_id}'. Last error: {last_error}"
        )

class ProxyManager:
    def __init__(self):
        self.discovery = ServiceDiscovery()
        self.health_monitor = HealthMonitor(self.discovery)
        self.router = ModelRouter(self.discovery)

    def stop(self):
        self.health_monitor.stop()
        self.discovery.stop()

app = FastAPI(
    title="ZeroconfAI Local Proxy",
    description="OpenAI-compatible reverse proxy that discovers and routes to ZeroconfAI services",
    version="1.0",
    contact={
        "name": "Joey Perrello",
        "url": "https://jperrello.netlify.app/",
        "email": "jperrell@ucsc.edu",
    }
)

_proxy_manager: Optional[ProxyManager] = None

def get_proxy_manager() -> ProxyManager:
    if _proxy_manager is None:
        raise HTTPException(status_code=503, detail="Proxy not initialized")
    return _proxy_manager

class CurrentChatContent(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class UserAIRequest(BaseModel):
    model: str
    messages: list[CurrentChatContent]
    max_tokens: int | None = None
    stream: bool = False

@app.get("/v1/health")
async def health(manager: ProxyManager = Depends(get_proxy_manager)) -> dict:
    services = manager.discovery.get_all_services()
    healthy_services = [s for s in services if s.is_healthy]
    
    return {
        "status": "ok" if healthy_services else "no_services",
        "provider": "ZeroconfAI local proxy",
        "services": len(healthy_services),
        "total_services": len(services)
    }

@app.get("/v1/models")
async def get_models(manager: ProxyManager = Depends(get_proxy_manager)) -> dict:
    models = manager.router.get_all_models()
    
    if not models["models"]:
        raise HTTPException(
            status_code=503,
            detail="No models available from any ZeroconfAI service"
        )
    
    return models

@app.post("/v1/chat/completions")
async def chat_completions(
    request: UserAIRequest,
    manager: ProxyManager = Depends(get_proxy_manager)
):
    logger.info(f"=== NEW REQUEST ===")
    logger.info(f"Model: {request.model}")
    logger.info(f"Messages: {len(request.messages)}")
    logger.info(f"Stream: {request.stream}")
    logger.info(f"Max tokens: {request.max_tokens}")
    
    #for i, msg in enumerate(request.messages):
        #logger.debug(f"Message {i}: {msg.role} - {msg.content[:100]}")
    
    request_dict = {
        "model": request.model,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "stream": request.stream
    }
    if request.max_tokens is not None:
        request_dict["max_tokens"] = request.max_tokens
    
    response = manager.router.route_request(request.model, request_dict)
    
    if request.stream:
        #logger.info(f"Setting up streaming response")
        
        def generate():
            chunk_count = 0
            try:
                for line in response.iter_lines():
                    if line:
                        chunk_count += 1
                        decoded_line = line.decode('utf-8')
                        
                        logger.debug(f"Chunk {chunk_count}: {decoded_line[:200]}")
                        
                        if decoded_line.startswith('data: '):
                            yield line + b'\n\n'
                        else:
                            yield f"data: {decoded_line}\n\n".encode('utf-8')
                
                #logger.info(f"Stream complete. Total chunks: {chunk_count}")
            except Exception as e:
                logger.error(f"Error in stream generator: {type(e).__name__}: {str(e)}")
                raise
            finally:
                response.close()
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache", #tells proxies not to cache, important for streaming
                "Connection": "keep-alive", #normally HTTP servers close connections after response, this keeps it open for each chunk
                "X-Accel-Buffering": "no" # I didnt know this existed until copilot told me, but it nginx waits to forward until a complete response is ready unless you set this header
            }
        )
    else:
        #logger.info(f"Returning non-streaming response")
        #logger.debug(f"Response type: {type(response)}")
        #logger.debug(f"Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")
        
        if isinstance(response, dict) and "choices" in response:
            #logger.info(f"Valid response with {len(response['choices'])} choices")
            if response['choices']:
                content = response['choices'][0].get('message', {}).get('content', '')
                logger.info(f"Content length: {len(content)}")
                #logger.debug(f"Content preview: {content[:200]}")
        
        return JSONResponse(
            content=response,
            media_type="application/json"
        )

def find_port_number(start_port=8080, max_attempts=20) -> int:
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports in range {start_port} - {start_port + max_attempts}")

def main():
    global _proxy_manager

    parser = argparse.ArgumentParser(description="ZeroconfAI Local Proxy Server")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port if args.port else find_port_number()

    print("=" * 50)
    print("  ZeroconfAI Local Proxy")
    print("=" * 50)
    print(f"Starting proxy on {args.host}:{port}")
    print(f"Configure Jan to connect to: http://{args.host}:{port}/v1")
    print(f"To configure:Open Jan Setting -> Model Providers -> Add Provider -> Any name -> Api Key = Any string -> Base URL = http://{args.host}:{port}/v1")
    print()

    _proxy_manager = ProxyManager()

    logger.info("Waiting for service discovery...")
    time.sleep(3)

    try:
        uvicorn.run(app, host=args.host, port=port, log_level="info")
    finally:
        logger.info("Shutting down proxy...")
        _proxy_manager.stop()

if __name__ == "__main__":
    main()