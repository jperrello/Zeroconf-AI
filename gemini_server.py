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
from typing import Literal, Dict, Any
from dotenv import load_dotenv
import threading

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
if not OPENROUTER_API_KEY or not OPENROUTER_BASE_URL:
    raise ValueError(
        "Missing environment variables. "
        "Please set OPENROUTER_API_KEY and OPENROUTER_BASE_URL in your .env file"
    )

app = FastAPI(
    title="ZeroconfAI Gemini",
    description="Zeroconf AI allows you to connect to llm services through your local network. This is an example of a Gemini proxy server.",
    summary="Get LLMs anywhere you go!",
    version="1.0",
    contact={
        "name": "Joey Perrello",
        "url": "https://jperrello.netlify.app/",
        "email": "jperrell@ucsc.edu",
    })

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
    return {"status": "ok", "provider": "Google Gemini"}

@app.get("/v1/models", description="Get's the available models")
async def get_models() -> dict:
    models = [{"id": name, "object": "model", "owned_by": "google"} 
              for name in Gemini_Models.keys()]
    return {"models": models}

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

    service_name = f"Gemini.{service_type}"

    info = ServiceInfo(
        type_=service_type, 
        name=service_name, 
        port=port, 
        addresses=[socket.inet_aton(host_ip)], 
        server=f"{host}.local.", 
        properties={
            'version': '1.0', 
            'api': 'OpenRouter',
            'priority': str(actual_priority) # Store priority as a string property
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
    parser = argparse.ArgumentParser(description="ZeroconfAI Gemini Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--priority", type=int, default=50)
    args = parser.parse_args()
    
    port = args.port if args.port else find_port_number(args.host)
    print(f"Starting Gemini proxy on {args.host}:{port} with desired priority {args.priority}...")
    
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