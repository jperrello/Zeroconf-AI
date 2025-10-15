"""
ZeroConfAI Client Library
Simplified client for discovering and using AI gateways
"""
import asyncio
import httpx
from typing import Optional, Dict, Any
from dataclasses import dataclass
from zeroconf import ServiceBrowser, Zeroconf
import socket
import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    SERVICE_TYPE,
    DISCOVERY_TIMEOUT_SECONDS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    HTTP_TIMEOUT_SECONDS
)

logger = logging.getLogger(__name__)

@dataclass
class AIGateway:
    name: str
    host: str
    port: int
    properties: Dict[str, str]
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class GatewayDiscovery:
    """Handles mDNS discovery of AI gateways"""
    
    def __init__(self):
        self.gateway: Optional[AIGateway] = None
        self._discovery_event = asyncio.Event()
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service is discovered"""
        info = zc.get_service_info(type_, name)
        if info and not self.gateway:  # Use first discovered
            properties = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in info.properties.items()
            }
            
            self.gateway = AIGateway(
                name=name,
                host=socket.inet_ntoa(info.addresses[0]),
                port=info.port,
                properties=properties
            )
            
            logger.info(f"Discovered AI gateway at {self.gateway.base_url}")
            self._discovery_event.set()
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service disappears"""
        if self.gateway and self.gateway.name == name:
            logger.info(f"Lost connection to {name}")
            self.gateway = None
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass  # We don't need to handle updates for now
    
    async def wait_for_gateway(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(
                self._discovery_event.wait(),
                timeout
            )
            return True
        except asyncio.TimeoutError:
            return False

class ZeroConfAIClient:
    """Main client for using ZeroConfAI gateways"""
    
    def __init__(self):
        self.discovery = GatewayDiscovery()
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
    
    async def connect(self, timeout: float = DISCOVERY_TIMEOUT_SECONDS) -> bool:
        """
        Discover and connect to an AI gateway
        Returns True if successful
        """
        self.zeroconf = Zeroconf()
        self.browser = ServiceBrowser(
            self.zeroconf,
            SERVICE_TYPE,
            self.discovery
        )
        
        found = await self.discovery.wait_for_gateway(timeout)
        if not found:
            logger.warning("No AI gateway found on network")
            self.disconnect()
        
        return found
    
    def disconnect(self) -> None:
        """Clean up mDNS resources"""
        if self.zeroconf:
            self.zeroconf.close()
            self.zeroconf = None
            self.browser = None
    
    async def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        app_id: str = "python-client"
    ) -> Dict[str, Any]:
        """
        Send a completion request to the gateway
        
        Args:
            prompt: The input text
            model: Optional specific model to use
            max_tokens: Maximum response length
            temperature: Creativity parameter (0-2)
            app_id: Application identifier for tracking
            
        Returns:
            Response dict with 'text', 'model', 'tokens_used', 'cost_estimate'
        """
        if not self.discovery.gateway:
            raise ConnectionError("No AI gateway connected")
        
        gateway = self.discovery.gateway
        
        request_data = {
            "prompt": prompt,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "app_id": app_id
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{gateway.base_url}/v1/complete",
                json=request_data,
                timeout=HTTP_TIMEOUT_SECONDS
            )
            
            if response.status_code == 429:
                raise Exception("Rate limit exceeded - try again later")
            elif response.status_code == 402:
                raise Exception("Payment required - gateway credits exhausted")
            
            response.raise_for_status()
            return response.json()
    
    async def get_usage(self) -> Dict[str, Any]:
        """Get usage statistics from the gateway"""
        if not self.discovery.gateway:
            raise ConnectionError("No AI gateway connected")
        
        gateway = self.discovery.gateway
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{gateway.base_url}/usage",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def query_ai(
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    app_id: str = "quick-query"
) -> Optional[str]:
    """
    Simple one-shot query to any available AI gateway
    
    Example:
        response = await query_ai("What is the capital of France?")
    """
    client = ZeroConfAIClient()
    
    try:
        connected = await client.connect()
        if not connected:
            return None
        
        result = await client.complete(
            prompt=prompt,
            max_tokens=max_tokens,
            app_id=app_id
        )
        
        return result.get("text")
        
    finally:
        client.disconnect()