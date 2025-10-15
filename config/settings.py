"""
ZeroConfAI Configuration Module
All magic numbers, defaults, and configuration in one place
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import os
import socket
from dotenv import load_dotenv

load_dotenv()
# ============================================================================
# NETWORK CONFIGURATION
# ============================================================================
DEFAULT_SERVICE_PORT: int = 8000  # Standard port for local dev servers
SERVICE_TYPE: str = "_zeroconfai._tcp.local."  # mDNS service type identifier
DISCOVERY_TIMEOUT_SECONDS: float = 5.0  # Time to wait for mDNS discovery

# ============================================================================
# API CONFIGURATION  
# ============================================================================
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"

# HTTP timeout for API calls - 60s accommodates slow models on complex prompts
HTTP_TIMEOUT_SECONDS: float = 60.0

# ============================================================================
# DEFAULT GENERATION PARAMETERS
# ============================================================================
# Max tokens: 200 provides ~150 words, enough for most single responses
DEFAULT_MAX_TOKENS: int = 200

# Temperature: 0.7 balances creativity vs consistency (0=deterministic, 2=chaotic)
DEFAULT_TEMPERATURE: float = 0.7

# ============================================================================
# RATE LIMITING
# ============================================================================
# Hourly request limit prevents runaway loops/bugs from burning credits
MAX_REQUESTS_PER_HOUR: int = 100

# Daily token limit: ~100k tokens ≈ $0.10-$3.00 depending on model
MAX_TOKENS_PER_DAY: int = 100000

# Daily cost limit: Hard stop to prevent bill shock
MAX_COST_PER_DAY_USD: float = 10.0

# ============================================================================
# MODEL CONFIGURATIONS
# Prices from OpenRouter as of Jan 2025
# Source: https://openrouter.ai/models
# ============================================================================

@dataclass
class ModelConfig:
    """Configuration for a specific AI model"""
    name: str  # OpenRouter model identifier
    input_price_per_million: float  # USD per million input tokens
    output_price_per_million: float  # USD per million output tokens
    context_window: int  # Maximum context length in tokens
    capabilities: List[str] = field(default_factory=list)
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for given token counts"""
        input_cost = (input_tokens / 1_000_000) * self.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_million
        return input_cost + output_cost

# Model tier definitions - updated Jan 2025
MODELS: Dict[str, ModelConfig] = {
    "cheap": ModelConfig(
        name="meta-llama/llama-3.2-3b-instruct",
        input_price_per_million=0.06,
        output_price_per_million=0.06,
        context_window=131072,
        capabilities=["completion", "chat"]
    ),
    "balanced": ModelConfig(
        name="anthropic/claude-3-haiku-20240307", 
        input_price_per_million=0.25,
        output_price_per_million=1.25,
        context_window=200000,
        capabilities=["completion", "chat", "vision"]
    ),
    "premium": ModelConfig(
        name="openai/gpt-4o",
        input_price_per_million=2.50,
        output_price_per_million=10.00,
        context_window=128000,
        capabilities=["completion", "chat", "vision", "function_calling"]
    )
}

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
USAGE_DB_PATH: str = os.getenv("ZEROCONF_AI_DB", "zeroconf_ai_usage.db")

# ============================================================================
# SERVICE METADATA
# ============================================================================
def get_service_properties() -> Dict[str, str]:
    """Generate mDNS service properties"""
    return {
        "version": "1.0",
        "api_format": "zeroconfai-v1",
        "backend": "cloud",
        "provider": "openrouter",
        "capabilities": "completion,chat",
        "models": ",".join([m.name for m in MODELS.values()]),
        "auth_mode": "shared",
        "billing": "per-token"
    }