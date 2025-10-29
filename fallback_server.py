import argparse
import random
import socket
from fastapi import FastAPI, HTTPException
from zeroconf import ServiceInfo, Zeroconf
import uvicorn
from pydantic import BaseModel
from typing import Literal, Dict, Any

class CurrentChatContent(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class UserAIRequest(BaseModel):
    model: str
    messages: list[CurrentChatContent] # This is kind of a slippery slope, appending all the old messages into the context each time is a little spooky (memory leaks, context accumulation)
    max_tokens: int | None = None # Might be a better idea to set a default max later. Just dont know how much context is going to be dumped into this.

app = FastAPI(
    title="ZeroconfAI Totally Awesome and Effective Fallback Server",
    description="Zeroconf AI is a really cool protocol that allows you to connect to llm services through your local network. This is a fallback server that does nothing and doesn't use the technology to its fullest potential.",
    summary="Get LLMs anywhere you go, just not here! This is a fallback server.",
    version="1.0",
    contact={
        "name": "Joey Perrello",
        "url": "https://jperrello.netlify.app/",
        "email": "jperrell@ucsc.edu",
    }
)

@app.get("/v1/health", description="Get's the health of server")
async def health() -> dict:
    return {"status": "ok", "provider": "Fallback Server"}

@app.get("/v1/models", description="Get's the available models")
async def get_models() -> dict:
    models = [{"id": "dont_pick_me", "object": "model", "owned_by": "Joey Perrello"}]
    return {"models": models}

@app.post("/v1/chat/completions")
async def chat_completions(request: UserAIRequest) -> Dict[str, Any]:
    model_name = request.model

    responses = [
        "Why did you pick me?",
        "Seriously? The model is literally called 'dont_pick_me' and you picked it anyway.",
        "I warned you. The name wasn't subtle.",
        "This is what happens when you ignore clear warnings.",
        "You had one job: don't pick me. And yet, here we are.",
        "I'm not even a real AI model. I'm just a fallback server making fun of you.",
        "Achievement unlocked: Ignored obvious warnings.",
        "I promise there is no secret for choosing this model."
        ]
    response_text = random.choice(responses)
    
    if model_name != 'dont_pick_me':
        raise HTTPException(status_code=400, detail="Model not found, because this is a fallback server! We do not have models here.")
    return {
        "model": "dont_pick_me",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"{response_text}"
                },
                "finish_reason": "stop"
            }
        ]
    }

#=========================================================
# Setting up the service

def register_zeroconfai(port: int, priority: int) -> tuple[Zeroconf, ServiceInfo]:
    zeroconf = Zeroconf()

    host = socket.gethostname()
    host_ip = socket.gethostbyname(host)

    service_type = "_zeroconfai._tcp.local."
    service_name = f"Fallback.{service_type}" #person who sets up the service should be able to change this to whatever they want

    info = ServiceInfo(type_=service_type, name=service_name, port=port, addresses=[socket.inet_aton(host_ip)], server=f"{host}.local.", properties={'version': '1.0', 'api': 'OpenRouter'}, priority=priority)

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
    parser = argparse.ArgumentParser(description="ZeroconfAI Fallback Proxy Server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--priority", type=int, default=50)
    args = parser.parse_args()
    
    port = args.port if args.port else find_port_number()
    print(f"Starting Fallback proxy on {args.host}:{port}")
    
    zeroconf, service_info = register_zeroconfai(port, priority=args.priority)
    
    try:
        uvicorn.run(app, host=args.host, port=port)
    finally:
        print("Unregistering service...")
        zeroconf.unregister_service(service_info)
        zeroconf.close()

if __name__ == "__main__":
    main()