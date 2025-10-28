import argparse
import socket
from fastapi import FastAPI, HTTPException
import os
from zeroconf import ServiceInfo, Zeroconf
import uvicorn
import requests
from pydantic import BaseModel
from typing import Literal, List, Dict, Any

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
    title="ZeroconfAI Ollama",
    description="Zeroconf AI allows you to connect to llm services through your local network. This is an example of an Ollama proxy server.",
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
    messages: list[CurrentChatContent] # This is kind of a slippery slope, appending all the old messages into the context each time is a little spooky (memory leaks, context accumulation)
    max_tokens: int | None = None # Might be a better idea to set a default max later. Just dont know how much context is going to be dumped into this.

#========================================================
@app.get("/v1/health", description="Get's the health of server")
async def health() -> dict:
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
    if response.status_code == 200:
        return {"status": "ok", "provider": "Ollama"}
    else:
        raise HTTPException(status_code=503, detail="Ollama server is not reachable")

@app.get("/v1/models", description="Get's the available models")
async def get_models() -> dict:
    models = get_ollama_models()
    if not models:
        raise HTTPException(status_code=503, detail="Could not fetch models from Ollama server.")
    return {"models": models}

@app.post("/v1/chat/completions", description="Get's a chat completion from the AI model")
async def chat_completions(request: UserAIRequest) -> Dict[str, Any]:
    
    ollama_payload = {
        "model": request.model,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": False,
    }
    
    if request.max_tokens:
        ollama_payload["options"] = {"num_predict": request.max_tokens}
    
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=ollama_payload,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        
        content = data.get("message", {}).get("content", "")
        
        return {
            "id": "chatcmpl-ollama",
            "object": "chat.completion",
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", -1),
                "completion_tokens": data.get("eval_count", -1),
                "total_tokens": -1
            }
        }
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Ollama request timed out")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Ollama API error: {str(e)}")

#========================================================
#Setting up the service
def register_zeroconfai(port: int) -> tuple[Zeroconf, ServiceInfo]:
    zeroconf = Zeroconf()

    host = socket.gethostname()
    host_ip = socket.gethostbyname(host)

    service_type = "_zeroconfai._tcp.local."
    service_name = f"Ollama.{service_type}" #person who sets up the service should be able to change this to whatever they want

    info = ServiceInfo(type_=service_type, name=service_name, port=port, addresses=[socket.inet_aton(host_ip)], server=f"{host}.local.", properties={'version': '1.0', 'api': 'OpenRouter'})

    zeroconf.register_service(info)

    print(f"{service_name} has been registered.")

    return zeroconf, info


#=============================================
def find_port_number(start_port=8080, max_attempts=20) -> int:
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"There are no available ports in range {start_port} - {start_port + max_attempts}, please try again by specifying port number with --port.")
#=============================================

def main():
    parser = argparse.ArgumentParser(description="ZeroconfAI Ollama Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    
    port = args.port if args.port else find_port_number()
    print(f"Starting Ollama proxy on {args.host}:{port}")
    
    zeroconf, service_info = register_zeroconfai(port)
    
    try:
        uvicorn.run(app, host=args.host, port=port)
    finally:
        print("Unregistering service...")
        zeroconf.unregister_service(service_info)
        zeroconf.close()

if __name__ == "__main__":
    main()