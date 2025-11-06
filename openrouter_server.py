import argparse
import socket
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import os
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceListener
import uvicorn
import requests
from pydantic import BaseModel
from typing import Literal, Dict, Any, Optional, List
from dotenv import load_dotenv
import threading
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

if not OPENROUTER_API_KEY or not OPENROUTER_BASE_URL:
    raise ValueError(
        "Missing environment variables. "
        "Please set OPENROUTER_API_KEY and OPENROUTER_BASE_URL in your .env file"
    )

# Model Cache for OpenRouter models
class ModelCache:
    def __init__(self):
        self.models: List[Dict[str, Any]] = []
        self.last_updated: Optional[datetime] = None
        self.lock = threading.Lock()

    def update(self, models: List[Dict[str, Any]]):
        with self.lock:
            self.models = models
            self.last_updated = datetime.now()

    def get(self) -> List[Dict[str, Any]]:
        with self.lock:
            return self.models.copy()

    def needs_refresh(self, max_age_hours: int = 1) -> bool:
        with self.lock:
            if not self.last_updated:
                return True
            return datetime.now() - self.last_updated > timedelta(hours=max_age_hours)

model_cache = ModelCache()

def fetch_openrouter_models() -> List[Dict[str, Any]]:
    """Fetch all available models from OpenRouter API"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }

    try:
        print("Fetching models from OpenRouter API...")
        response = requests.get(OPENROUTER_MODELS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        # OpenRouter returns models in a 'data' array
        if "data" in data:
            models = data["data"]
        else:
            models = data

        # Format models to match OpenAI API format
        formatted_models = []
        for model in models:
            if isinstance(model, dict) and "id" in model:
                formatted_models.append({
                    "id": model["id"],
                    "object": "model",
                    "owned_by": model.get("owned_by", "openrouter"),
                    "context_length": model.get("context_length"),
                    "pricing": model.get("pricing"),
                    "modality": model.get("modality", "text"),
                })

        print(f"Successfully fetched {len(formatted_models)} models from OpenRouter")
        return formatted_models
    except requests.RequestException as e:
        print(f"Failed to fetch OpenRouter models: {e}")
        return []

async def refresh_models_if_needed():
    """Refresh model cache if it's stale"""
    if model_cache.needs_refresh():
        print("Model cache is stale, refreshing...")
        models = fetch_openrouter_models()
        if models:
            model_cache.update(models)
            print(f"Successfully refreshed cache with {len(models)} models")
        else:
            print("Failed to refresh models, keeping existing cache")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup: Fetch models from OpenRouter
    print("=" * 50)
    print("Starting up OpenRouter server...")
    print("=" * 50)
    models = fetch_openrouter_models()
    if models:
        model_cache.update(models)
        print(f"Cached {len(models)} models from OpenRouter")
    else:
        print("WARNING: Failed to fetch models at startup. The /v1/models endpoint will be empty.")

    yield  # Server is running

    # Shutdown (cleanup if needed)
    print("Shutting down OpenRouter server...")

app = FastAPI(
    title="ZeroconfAI OpenRouter",
    description="Zeroconf AI allows you to connect to llm services through your local network. This is an OpenRouter proxy server with dynamic model discovery.",
    summary="Get LLMs anywhere you go!",
    version="1.0",
    contact={
        "name": "Joey Perrello",
        "url": "https://jperrello.netlify.app/",
        "email": "jperrell@ucsc.edu",
    },
    lifespan=lifespan
)

Gemini_Models = {"Gemini-2.5-Flash": "google/gemini-2.5-flash",
                 "Gemini-2.5-Pro": "google/gemini-2.5-pro",
                 "Gemini-2.0-Flash": "google/gemini-2.0-flash-001",
                 "Gemini-2.5-Flash-Image-Preview": "google/gemini-2.5-flash-image-preview"}

class CurrentChatContent(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class UserAIRequest(BaseModel):
    model: str
    messages: list[CurrentChatContent]
    max_tokens: int | None = None
    stream: bool = False

@app.get("/v1/health", description="Get's the health of server")
async def health() -> dict:
    return {"status": "ok", "provider": "OpenRouter", "models_cached": len(model_cache.get())}

@app.get("/v1/models", description="Get's the available models from OpenRouter")
async def get_models() -> dict:
    """Return all cached models from OpenRouter API"""
    # Optionally refresh if cache is stale
    await refresh_models_if_needed()

    cached_models = model_cache.get()

    if not cached_models:
        raise HTTPException(
            status_code=503,
            detail="No models available. Failed to fetch from OpenRouter API."
        )

    return {"models": cached_models}

@app.post("/v1/chat/completions", description="Get's a chat completion from the AI model")
async def chat_completions(request: UserAIRequest):
    print(f"Received request for model: {request.model}")
    print(f"Messages count: {len(request.messages)}, stream: {request.stream}")
    
    model_name = Gemini_Models.get(request.model, request.model)
    
    openrouter_request = {
        "model": model_name,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages]
    }
    if request.max_tokens is not None:
        openrouter_request["max_tokens"] = request.max_tokens
    if request.stream:
        openrouter_request["stream"] = True
    
    print(f"Sending to OpenRouter with model: {model_name}, stream: {request.stream}")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            OPENROUTER_BASE_URL, 
            headers=headers, 
            json=openrouter_request, 
            timeout=120,
            stream=request.stream
        )
        
        print(f"OpenRouter response status: {response.status_code}")
        
        if not response.ok:
            print(f"OpenRouter error response: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenRouter API error: {response.text}"
            )
        
        if request.stream:
            print(f"Returning streaming response")
            
            def generate():
                try:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                data_content = decoded_line[6:]
                                
                                if data_content == '[DONE]':
                                    yield f"data: [DONE]\n\n".encode('utf-8')
                                    break
                                
                                try:
                                    chunk_data = json.loads(data_content)
                                    
                                    yield f"data: {json.dumps(chunk_data)}\n\n".encode('utf-8')
                                except json.JSONDecodeError:
                                    continue
                finally:
                    response.close()
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            try:
                result = response.json()
                print(f"OpenRouter response parsed successfully")
                return result
            except requests.exceptions.JSONDecodeError:
                raise HTTPException(
                    status_code=502,
                    detail=f"OpenRouter returned non-JSON response. Status: {response.status_code}, Body: {response.text[:500]}"
                )
    
    except requests.Timeout:
        print(f"OpenRouter request timed out")
        raise HTTPException(status_code=504, detail="OpenRouter request timed out")
    except requests.RequestException as e:
        print(f"OpenRouter connection error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=502, detail=f"OpenRouter connection error: {str(e)}")


class PriorityDiscoveryListener(ServiceListener):
    def __init__(self):
        self.priorities = set()
        self.lock = threading.Lock()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info and info.properties:
            priority_bytes = info.properties.get(b'priority')
            if priority_bytes:
                with self.lock:
                    try:
                        priority_value = int(priority_bytes.decode('utf-8'))
                        self.priorities.add(priority_value)
                    except (ValueError, UnicodeDecodeError):
                        pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

#right when a service is being registered, we want to find an available priority
def find_available_priority(desired_priority: int, service_type: str) -> int:
    discovery_zc = Zeroconf()
    listener = PriorityDiscoveryListener()
    
    browser = ServiceBrowser(discovery_zc, service_type, listener)
    
    time.sleep(2.0)
    
    browser.cancel()
    discovery_zc.close()
    
    current_priority = desired_priority
    with listener.lock:
        while current_priority in listener.priorities:
            print(f"Priority {current_priority} is already in use, trying {current_priority + 1}...")
            current_priority += 1
    
    if current_priority != desired_priority:
        print(f"Adjusted priority from {desired_priority} to {current_priority}")
    
    return current_priority

def register_zeroconfai(port: int, priority: int, service_type: str) -> tuple[Zeroconf, ServiceInfo]:
    actual_priority = find_available_priority(priority, service_type)
    
    zeroconf = Zeroconf()

    host = socket.gethostname()
    host_ip = socket.gethostbyname(host)

    service_name = f"OpenRouter.{service_type}"

    info = ServiceInfo(
        type_=service_type,
        name=service_name,
        port=port,
        addresses=[socket.inet_aton(host_ip)],
        server=f"{host}.local.",
        properties={
            'version': '1.0',
            'api': 'OpenRouter',
            'priority': str(actual_priority)
        },
        priority=actual_priority # Also set as ServiceInfo.priority field
    )

    zeroconf.register_service(info)

    print(f"{service_name} has been registered with priority {actual_priority}.")

    return zeroconf, info

def find_port_number(host: str, start_port=8080, max_attempts=20) -> int:
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"No available ports in range {start_port} - {start_port + max_attempts}")

def main():
    parser = argparse.ArgumentParser(description="ZeroconfAI OpenRouter Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--priority", type=int, default=50)
    args = parser.parse_args()

    port = args.port if args.port else find_port_number(args.host)
    print(f"Starting OpenRouter proxy on {args.host}:{port} with desired priority {args.priority}...")
    
    service_type = "_zeroconfai._tcp.local."
    zeroconf, service_info = register_zeroconfai(port, priority=args.priority, service_type=service_type)
    
    try:
        uvicorn.run(app, host=args.host, port=port)
    finally:
        print("Unregistering service...")
        zeroconf.unregister_service(service_info)
        zeroconf.close()

if __name__ == "__main__":
    main()