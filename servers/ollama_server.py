import argparse
import socket
import time
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceListener
import uvicorn
import requests
from pydantic import BaseModel
from typing import Literal, List, Dict, Any
import threading

OLLAMA_BASE_URL = "http://localhost:11434"

def get_ollama_models() -> List[Dict]:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = []
            for model in data.get("models", []):
                models.append({
                    "id": model.get("name"),
                    "object": "model",
                    "owned_by": "ollama",
                })
            return models
    except Exception as e:
        print(f"Error fetching models from Ollama: {e}")
    return []

app = FastAPI(
    title="Saturn Ollama",
    description="Saturn allows you to connect to llm services through your local network. This is an example of an Ollama proxy server.",
    summary="Get LLMs anywhere you go!",
    version="1.0",
    contact={
        "name": "Joey Perrello",
        "url": "https://jperrello.netlify.app/",
        "email": "jperrell@ucsc.edu",
    })

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
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        if response.status_code == 200:
            return {"status": "ok", "provider": "Ollama"}
    except Exception:
        pass
    raise HTTPException(status_code=503, detail="Ollama server is not reachable")

@app.get("/v1/models", description="Get's the available models")
async def get_models() -> dict:
    models = get_ollama_models()
    if not models:
        raise HTTPException(status_code=503, detail="Could not fetch models from Ollama server.")
    return {"models": models}

@app.post("/v1/chat/completions", description="Get's a chat completion from the AI model")
async def chat_completions(request: UserAIRequest):
    print(f"Received request for model: {request.model}")
    print(f"Messages count: {len(request.messages)}, stream: {request.stream}")
    
    ollama_payload = {
        "model": request.model,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": request.stream,
    }
    
    if request.max_tokens:
        ollama_payload["options"] = {"num_predict": request.max_tokens}
    
    print(f"Sending to Ollama: stream={request.stream}")
    
    try:
        #make actual request to ollama server
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=ollama_payload,
            timeout=120,
            stream=request.stream
        )
        
        print(f"Ollama response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Ollama error response: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Ollama API error: {response.text}"
            )
        
        if request.stream:
            print(f"Returning streaming response")
            #basically yield each chunk as it comes in from ollama, converting to openai format and send the chunk
            def generate():
                chunk_id = f"chatcmpl-{int(time.time())}"
                first_chunk = True
                
                try:
                    for line in response.iter_lines():
                        if line:
                            try:
                                ollama_chunk = json.loads(line)
                            except json.JSONDecodeError:
                                print(f"Failed to parse Ollama chunk: {line}")
                                continue
                            
                            if ollama_chunk.get("done"):
                                #ollama chunks dont come in openAI format, so we have to convert them
                                #i must admit, some of this like delta and the first yield were written by copilot
                                openai_chunk = {
                                    "id": chunk_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": request.model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": "stop" 
                                    }]
                                }
                                yield f"data: {json.dumps(openai_chunk)}\n\n".encode('utf-8')
                                yield b"data: [DONE]\n\n" # Jan expects each chunk to be prefixed with 'data: ' and suffixed with two newlines. This was a major headache.
                                print("Stream completed")
                            else:
                                content = ollama_chunk.get("message", {}).get("content", "")
                                role = ollama_chunk.get("message", {}).get("role")
                                
                                delta = {}
                                if first_chunk and role:
                                    delta["role"] = role
                                    first_chunk = False
                                
                                if content:
                                    delta["content"] = content
                                
                                if delta:
                                    openai_chunk = {
                                        "id": chunk_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": request.model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": delta,
                                            "finish_reason": None
                                        }]
                                    }
                                    chunk_json = json.dumps(openai_chunk)
                                    print(f"Sending chunk: {chunk_json[:100]}")
                                    yield f"data: {chunk_json}\n\n".encode('utf-8')
                except Exception as e:
                    print(f"Error in stream generation: {type(e).__name__}: {str(e)}")
                    raise
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
                data = response.json()
                print(f"Ollama response parsed successfully")
            except requests.exceptions.JSONDecodeError:
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama returned non-JSON response: {response.text[:500]}"
                )
            
            message = data.get("message", {})
            content = message.get("content", "")
            role = message.get("role", "assistant")
            
            if not content:
                print(f"WARNING: Empty content in Ollama response")
                print(f"Full response: {json.dumps(data, indent=2)}")
            
            result = {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": role,
                            "content": content
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                }
            }
            
            print(f"Returning response with content length: {len(content)}")
            print(f"Response preview: {json.dumps(result, indent=2)[:300]}")
            return result
        
    except requests.Timeout:
        print(f"Ollama request timed out")
        raise HTTPException(status_code=504, detail="Ollama request timed out")
    except requests.RequestException as e:
        print(f"Ollama connection error: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ollama connection error: {str(e)}")

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

def register_saturn(port: int, priority: int, service_type: str) -> tuple[Zeroconf, ServiceInfo]:
    actual_priority = find_available_priority(priority, service_type)
    
    zeroconf = Zeroconf()

    host = socket.gethostname()
    host_ip = socket.gethostbyname(host)

    service_name = f"Ollama.{service_type}"

    info = ServiceInfo(
        type_=service_type,
        name=service_name,
        port=port,
        addresses=[socket.inet_aton(host_ip)],
        server=f"{host}.local.",
        properties={
            'version': '1.0', 
            'api': 'Ollama',
            'priority': str(actual_priority)
        },
        priority=actual_priority
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
    parser = argparse.ArgumentParser(description="Saturn Ollama Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--priority", type=int, default=50)
    args = parser.parse_args()

    port = args.port if args.port else find_port_number(args.host)
    print(f"Starting Ollama proxy on {args.host}:{port} with desired priority {args.priority}...")

    service_type = "_saturn._tcp.local."
    zeroconf, service_info = register_saturn(port, priority=args.priority, service_type=service_type)

    try:
        uvicorn.run(app, host=args.host, port=port)
    finally:
        print("Unregistering service...")
        zeroconf.unregister_service(service_info)
        zeroconf.close()

if __name__ == "__main__":
    main()