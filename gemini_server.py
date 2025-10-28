import argparse
import socket
from fastapi import FastAPI, HTTPException
import os
from zeroconf import ServiceInfo, Zeroconf
import uvicorn
import requests
from pydantic import BaseModel
from typing import Literal, List, Dict, Any
from dotenv import load_dotenv

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
    messages: list[CurrentChatContent] # This is kind of a slippery slope, appending all the old messages into the context each time is a little spooky (memory leaks, context accumulation)
    max_tokens: int | None = None # Might be a better idea to set a default max later. Just dont know how much context is going to be dumped into this.

@app.get("/v1/health", description="Get's the health of server")
async def health() -> dict:
    return {"status": "ok", "provider": "Google Gemini"}

@app.get("/v1/models", description="Get's the available models")
async def get_models() -> dict:
    models = [{"id": name, "object": "model", "owned_by": "google"} 
              for name in Gemini_Models.keys()]
    return {"models": models}

@app.post("/v1/chat/completions", description="Get's a chat completion from the AI model")
async def chat_completions(request: UserAIRequest) -> Dict[str, Any]:
    model_name = Gemini_Models.get(request.model, request.model)
    openrouter_request = request.model_dump()
    openrouter_request["model"] = model_name
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=openrouter_request)

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )
    return response.json()

#========================================================
# Setting up the service

def register_zeroconfai(port: int) -> tuple[Zeroconf, ServiceInfo]:
    zeroconf = Zeroconf()

    host = socket.gethostname()
    host_ip = socket.gethostbyname(host)

    service_type = "_zeroconfai._tcp.local."
    service_name = f"Gemini.{service_type}" #person who sets up the service should be able to change this to whatever they want

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
    parser = argparse.ArgumentParser(description="ZeroconfAI Gemini Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    
    port = args.port if args.port else find_port_number()
    print(f"Starting Gemini proxy on {args.host}:{port}")
    
    zeroconf, service_info = register_zeroconfai(port)
    
    try:
        uvicorn.run(app, host=args.host, port=port)
    finally:
        print("Unregistering service...")
        zeroconf.unregister_service(service_info)
        zeroconf.close()

if __name__ == "__main__":
    main()