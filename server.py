# mDNS advertising wrapper
# Goals:
# Start advertising Ollama instance via mDNS (i pulled llama2)
# Proxy requests to Ollama but in MY OWN SPECIFIC protocol format (refer to notes)
from fastapi import FastAPI
from pydantic import BaseModel
from zeroconf import ServiceInfo, Zeroconf, IPVersion
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceInfo
import socket
import httpx
import uvicorn #ASGI compliant so Uvicorn efficiently manages concurrent requests and support features like WebSockets
from contextlib import asynccontextmanager

#lifespan context, everything before yield runs at start, everythin after stops when done handling requests
@asynccontextmanager
async def lifespan(app: FastAPI):
    host = socket.gethostname() #the name of a device on the network
    localIP = socket.gethostbyname(host) #the ip address of that device

    #make sure we dont wait for network requests when completing jobs
    aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)

    info = AsyncServiceInfo(
        "_zeroconfai._tcp.local.", #Service type aka what everyone searches for
        "MyLaptop-ZeroConfAI._zeroconfai._tcp.local.", # Instance name (unique identifier for THIS specific service)
        addresses=[socket.inet_aton(localIP)],
        port=8000,
        properties={
            "version": "1.0",
            "capabilities": "completion",
            "models": "llama2", #  FIX: currently advertising statically, but what if the user pulls more models? Should dynamically query Ollama's /api/tags endpoint but I do not want to do that right now
        }
    )

    await aiozc.async_register_service(info)
    print(f"Zeroconf is advertising at {localIP}:{info.port}")
    print(f"Docs at http://localhost:{info.port}/docs")

    yield #the server has started running

    #once we are done
    await aiozc.async_unregister_service(info)
    await aiozc.async_close()
    print("Zeroconf is no longer advertising ")
    
app = FastAPI(title="ZeroConfAI", version="1.0", lifespan=lifespan)


# Request/Response models (auto-generates API docs)
class CompletionRequest(BaseModel):
    prompt: str
    model: str = "llama2"
    max_tokens: int = 100
    temperature: float = 0.7

class CompletionResponse(BaseModel):
    text: str
    model: str #should i include this?
    tokens_used: int

@app.post("/v1/complete", response_model=CompletionResponse)
async def complete(req: CompletionRequest):
    # Translate to Ollama format
    ollama_request = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": False,
        "options": {
            "temperature": req.temperature,
            "num_predict": req.max_tokens
        }
    }
    
    # Async HTTP call to Ollama
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json=ollama_request,
            timeout=60.0
        )
    
    result = response.json()
    
    # Return in the completion request protocol
    return CompletionResponse(
        text=result["response"],
        model=result["model"],
        tokens_used=result.get("eval_count", 0)
    )

@app.get("/health")
async def health():
    """Check if service is alive"""
    return {"status": "ok", "service": "ZeroConfAI"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) # FIX: anyone on my WiFi can now consume compute resources. Need to look into authentication or rate limiting but that comes further into the project process