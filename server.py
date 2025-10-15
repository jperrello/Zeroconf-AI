"""
ZeroConfAI Gateway Server
Advertises via mDNS and proxies requests to OpenRouter
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import httpx
import socket
from contextlib import asynccontextmanager
from zeroconf.asyncio import AsyncZeroconf, AsyncServiceInfo
from zeroconf import IPVersion

from config import (
    DEFAULT_SERVICE_PORT,
    SERVICE_TYPE,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    HTTP_TIMEOUT_SECONDS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    MAX_REQUESTS_PER_HOUR,
    MAX_COST_PER_DAY_USD,
    get_service_properties
)
from models import ModelRouter
from usage_tracker import UsageTracker

# Validate configuration
if not OPENROUTER_API_KEY:
    raise ValueError(
        "OPENROUTER_API_KEY environment variable required. "
        "Get one at https://openrouter.ai/keys"
    )

# Initialize global services
usage_tracker = UsageTracker()
model_router = ModelRouter()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Get network info
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    # Start mDNS advertising
    aiozc = AsyncZeroconf(ip_version=IPVersion.V4Only)
    
    service_name = f"{hostname}-ZeroConfAI.{SERVICE_TYPE}"
    info = AsyncServiceInfo(
        SERVICE_TYPE,
        service_name,
        addresses=[socket.inet_aton(local_ip)],
        port=DEFAULT_SERVICE_PORT,
        properties=get_service_properties()
    )
    
    await aiozc.async_register_service(info)
    print(f"ZeroConfAI Gateway started")
    print(f"Advertising at {local_ip}:{DEFAULT_SERVICE_PORT}")
    print(f"API docs at http://localhost:{DEFAULT_SERVICE_PORT}/docs")
    
    # Cleanup old usage records on startup
    usage_tracker.cleanup_old_records()
    
    yield  # Server runs
    
    # Shutdown
    await aiozc.async_unregister_service(info)
    await aiozc.async_close()
    print("👋 ZeroConfAI Gateway stopped")

# Initialize FastAPI
app = FastAPI(
    title="ZeroConfAI Gateway",
    version="1.0",
    lifespan=lifespan
)

# ============================================================================
# API MODELS
# ============================================================================

class CompletionRequest(BaseModel):
    """Request model for completions"""
    prompt: str
    model: Optional[str] = None  # None = auto-select
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    app_id: str = "unknown"  # For usage tracking

class CompletionResponse(BaseModel):
    """Response model for completions"""
    text: str
    model: str
    tokens_used: int
    cost_estimate: float

class UsageStats(BaseModel):
    """Current usage statistics"""
    hourly_requests: int
    daily_tokens: int
    daily_cost_usd: float
    app_breakdown: dict

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.post("/v1/complete", response_model=CompletionResponse)
async def complete(
    request: CompletionRequest,
    background_tasks: BackgroundTasks
) -> CompletionResponse:
    """
    Main completion endpoint
    Routes to appropriate model and tracks usage
    """
    # Check rate limits
    hourly_requests = usage_tracker.get_hourly_request_count()
    if hourly_requests >= MAX_REQUESTS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {MAX_REQUESTS_PER_HOUR} requests/hour"
        )
    
    daily_stats = usage_tracker.get_daily_stats()
    if daily_stats["cost_usd"] >= MAX_COST_PER_DAY_USD:
        raise HTTPException(
            status_code=402,
            detail=f"Daily cost limit exceeded: ${MAX_COST_PER_DAY_USD}"
        )
    
    # Select model based on prompt complexity - this uses the models.py approximation which is a heuristic I currently have issue with
    model_config = model_router.select_model(request.prompt, request.model)
    
    # Build OpenRouter request
    openrouter_request = {
        "model": model_config.name,
        "messages": [
            {"role": "user", "content": request.prompt}
        ],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "route": "fallback"  # Auto-fallback if primary provider unavailable
    }
    
    # Make API call
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENROUTER_BASE_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": f"http://localhost:{DEFAULT_SERVICE_PORT}",
                    "X-Title": f"ZeroConfAI-{request.app_id}"
                },
                json=openrouter_request,
                timeout=HTTP_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402:
            raise HTTPException(
                status_code=402,
                detail="OpenRouter credits exhausted - please add credits"
            )
        elif e.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="OpenRouter rate limit - please retry later"
            )
        else:
            raise HTTPException(
                status_code=502,
                detail=f"OpenRouter error: {e.response.text}"
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"Request timed out after {HTTP_TIMEOUT_SECONDS}s"
        )
    
    # Parse response
    result = response.json()
    text = result["choices"][0]["message"]["content"]
    input_tokens, output_tokens = model_router.parse_usage(result)
    cost = model_config.calculate_cost(input_tokens, output_tokens)
    
    # Record usage in background
    background_tasks.add_task(
        usage_tracker.record_usage,
        app_id=request.app_id,
        model=model_config.name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        prompt_preview=request.prompt[:100]
    )
    
    return CompletionResponse(
        text=text,
        model=model_config.name,
        tokens_used=input_tokens + output_tokens,
        cost_estimate=cost
    )

@app.get("/usage", response_model=UsageStats)
async def get_usage() -> UsageStats:
    """Get current usage statistics"""
    daily_stats = usage_tracker.get_daily_stats()
    
    return UsageStats(
        hourly_requests=usage_tracker.get_hourly_request_count(),
        daily_tokens=int(daily_stats["tokens"]),
        daily_cost_usd=daily_stats["cost_usd"],
        app_breakdown=usage_tracker.get_app_breakdown(24)
    )

@app.get("/health")
async def health() -> dict:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "backend": "openrouter",
        "models_available": len(model_router.MODELS)
    }

# Run with: uvicorn server:app --host 0.0.0.0 --port 8000