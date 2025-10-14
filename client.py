"""
ZeroConfAI Client Library
Simple discovery and usage of local AI services via mDNS
"""

import asyncio
import httpx
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from zeroconf import ServiceBrowser, Zeroconf
import socket
import time
import logging
from abc import ABC, abstractmethod
import random

logger = logging.getLogger(__name__)


@dataclass
class AIService:
    name: str
    host: str
    port: int
    properties: Dict[str, str]
    api_format: str
    models: List[str]
    capabilities: List[str]
    
    # Runtime metrics for load balancing
    response_times: List[float] = field(default_factory=list)
    error_count: int = 0
    last_used: Optional[float] = None
    is_healthy: bool = True
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        # Keep only last 10 measurements, this is really bad and shouldnt be magic
        recent = self.response_times[-10:]
        return sum(recent) / len(recent)
    
    def record_success(self, response_time: float) -> None:
        self.response_times.append(response_time)
        self.last_used = time.time()
        self.is_healthy = True
    
    def record_error(self) -> None: # i hate this function, but it got my program to work
        self.error_count += 1
        self.last_used = time.time()
        if self.error_count >= 3:
            self.is_healthy = False
    
    def __str__(self) -> str:
        return f"{self.name} at {self.base_url} (models: {', '.join(self.models)})"

"""
Below are my best attempts at load balancing for a lot of http requests. 
Doesnt work that well and actually takes a lot of time.
YAGNI principle - am i acually going to need this feature in the future
"""

class LoadBalancer(ABC):
    """Abstract base class for load balancing strategies"""
    
    @abstractmethod
    async def select_service(self, services: List[AIService]) -> Optional[AIService]:
        pass


class RoundRobinBalancer(LoadBalancer):
    """Inspired by round-robin load balancing"""
    
    def __init__(self):
        self._index = 0
    
    async def select_service(self, services: List[AIService]) -> Optional[AIService]:
        if not services:
            return None
        healthy_services = [s for s in services if s.is_healthy]
        if not healthy_services:
            return None
        
        selected = healthy_services[self._index % len(healthy_services)]
        self._index += 1
        return selected


class LatencyAwareBalancer(LoadBalancer):
    """should choose service with lowest average latency"""
    
    async def select_service(self, services: List[AIService]) -> Optional[AIService]:
        if not services:
            return None
        
        healthy_services = [s for s in services if s.is_healthy]
        if not healthy_services:
            return None
        
        # If no metrics yet, choose randomly
        if not any(s.response_times for s in healthy_services):
            return random.choice(healthy_services)
        
        # pick service with lowest average latency
        return min(healthy_services, key=lambda s: s.avg_response_time if s.response_times else float('inf'))


class MLLoadBalancer(LoadBalancer):
    """
    Placeholder for ML-based load balancing
    
    Future implementation could use:
    - LSTM for temporal sequence modeling of service performance
    - DRL for dynamic task scheduling optimization
    """
    
    def __init__(self):
        # FIX: Initialize ML models here
        # self.lstm_model = load_lstm_model()
        # self.drl_agent = load_drl_agent()
        self.fallback = LatencyAwareBalancer()
    
    async def select_service(self, services: List[AIService]) -> Optional[AIService]:
        # FIX: Implement ML-based selection
        # features = self._extract_features(services)
        # load_predictions = self.cnn_lstm_predict(features)
        # optimal_service = self.drl_agent.select_action(services, load_predictions)
        # return optimal_service
        
        # For now, fallback to latency-aware selection
        return await self.fallback.select_service(services)

"""
END OF LOAD BALANCING
"""

class ServiceListener:
    
    def __init__(self):
        self.services: Dict[str, AIService] = {}
        self._discovery_event = asyncio.Event()
        self._service_callbacks: List[Callable[[AIService], None]] = []
        self._removal_callbacks: List[Callable[[str], None]] = []
    
    def on_service_discovered(self, callback: Callable[[AIService], None]) -> None:
        self._service_callbacks.append(callback)
    
    def on_service_removed(self, callback: Callable[[str], None]) -> None:
        self._removal_callbacks.append(callback)
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            try:
                # Parse service properties
                properties = {}
                if info.properties:
                    properties = {k.decode('utf-8'): v.decode('utf-8') 
                                for k, v in info.properties.items()}
                
                # Extract specific fields
                models = properties.get('models', '').split(',')
                capabilities = properties.get('capabilities', '').split(',')
                api_format = properties.get('api_format', 'zeroconfai-v1')
                
                # Create service object
                service = AIService(
                    name=name,
                    host=socket.inet_ntoa(info.addresses[0]),
                    port=info.port,
                    properties=properties,
                    api_format=api_format,
                    models=[m.strip() for m in models if m.strip()],
                    capabilities=[c.strip() for c in capabilities if c.strip()]
                )
                
                self.services[name] = service
                logger.info(f"Discovered AI service: {service}")
                
                # Trigger callbacks
                for callback in self._service_callbacks:
                    try:
                        callback(service)
                    except Exception as e:
                        logger.error(f"Error in discovery callback: {e}")
                
                # Signal that discovery happened
                self._discovery_event.set()
                
            except Exception as e:
                logger.error(f"Error adding service {name}: {e}")
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when a service disappears"""
        if name in self.services:
            logger.info(f"Lost AI service: {name}")
            del self.services[name]
            
            # Trigger removal callbacks
            for callback in self._removal_callbacks:
                try:
                    callback(name)
                except Exception as e:
                    logger.error(f"Error in removal callback: {e}")
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Called when service info is updated"""
        self.remove_service(zc, type_, name)
        self.add_service(zc, type_, name)
    
    async def wait_for_discovery(self, timeout: Optional[float] = None) -> bool:
        """Wait for at least one service to be discovered"""
        try:
            await asyncio.wait_for(self._discovery_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


class ZeroConfAIClient:
    """Main client for discovering and using local AI services"""
    
    def __init__(
        self, 
        service_type: str = "_zeroconfai._tcp.local.",
        load_balancer: Optional[LoadBalancer] = None
    ):
        self.service_type = service_type
        self.listener = ServiceListener()
        self.zeroconf = None
        self.browser = None
        self.load_balancer = load_balancer or LatencyAwareBalancer()
        
        # Register default callbacks
        self.listener.on_service_discovered(self._on_service_discovered)
        self.listener.on_service_removed(self._on_service_removed)
    
    def _on_service_discovered(self, service: AIService) -> None:
        """Internal callback for service discovery"""
        logger.debug(f"Service discovered: {service.name}")
    
    def _on_service_removed(self, name: str) -> None:
        """Internal callback for service removal"""
        logger.debug(f"Service removed: {name}")
    
    def start_discovery(self) -> None:
        """Start discovering AI services on the network"""
        self.zeroconf = Zeroconf()
        self.browser = ServiceBrowser(
            self.zeroconf, 
            self.service_type, 
            self.listener
        )
        logger.info(f"Started discovery for {self.service_type}")
    
    def stop_discovery(self) -> None:
        """Stop service discovery and cleanup"""
        if self.zeroconf:
            self.zeroconf.close()
            self.zeroconf = None
            self.browser = None
    
    async def wait_for_services(self, timeout: float = 5.0) -> bool:
        """
        Wait for services to be discovered
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            True if services found, False if timeout
        """
        return await self.listener.wait_for_discovery(timeout)
    
    def get_services(self) -> List[AIService]:
        """Get list of currently discovered services"""
        return list(self.listener.services.values())
    
    def get_service(self, name: Optional[str] = None) -> Optional[AIService]:
        """Get a specific service by name, or use load balancer to select"""
        if name:
            return self.listener.services.get(name)
        
        # Use load balancer for selection
        services = self.get_services()
        return asyncio.run(self.load_balancer.select_service(services))
    
    async def complete(
        self, 
        prompt: str,
        service: Optional[AIService] = None,
        model: Optional[str] = None,
        max_tokens: int = 100,
        temperature: float = 0.7,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Send a completion request to an AI service
        
        Args:
            prompt: The prompt text
            service: Specific service to use (or auto-select via load balancer)
            model: Model to use (or use service default)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            timeout: Request timeout in seconds
            
        Returns:
            Response dictionary with 'text', 'model', and 'tokens_used'
            
        Raises:
            ValueError: If no services available
            httpx.HTTPError: If request fails
        """
        # Auto-select service using load balancer if not provided
        if not service:
            services = self.get_services()
            service = await self.load_balancer.select_service(services)
            if not service:
                raise ValueError("No healthy AI services discovered on network")
        
        # Use first available model if not specified
        if not model and service.models:
            model = service.models[0]
        elif not model:
            model = "llama2"  # fallback default
        
        # Build request based on API format
        # 
        if service.api_format == "zeroconfai-v1":
            request_data = {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            endpoint = f"{service.base_url}/v1/complete"
        else:
            # Could support other formats here (OpenAI, etc.)
            raise ValueError(f"Unsupported API format: {service.api_format}")
        
        # Make the request with timing
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    json=request_data,
                    timeout=timeout
                )
                response.raise_for_status()
                result = response.json()
            
            # Record success metrics
            elapsed = time.time() - start_time
            service.record_success(elapsed)
            logger.debug(f"Request to {service.name} completed in {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            # Record error metrics
            service.record_error()
            logger.warning(f"Request to {service.name} failed: {e}")
            
            # FIX: Add retry logic here
            # Could retry with another service from the load balancer
            # for attempt in range(max_retries):
            #     alternate_service = await self.load_balancer.select_service(services)
            #     if alternate_service != service:
            #         return await self.complete(prompt, alternate_service, ...)
            
            raise
    
    async def health_check(self, service: AIService) -> bool:
        """Check if a service is responding"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{service.base_url}/health",
                    timeout=5.0
                )
                is_healthy = response.status_code == 200
                service.is_healthy = is_healthy
                return is_healthy
        except Exception:
            service.is_healthy = False
            return False
    
    async def health_check_all(self) -> None:
        """Health check all discovered services"""
        services = self.get_services()
        tasks = [self.health_check(service) for service in services]
        await asyncio.gather(*tasks, return_exceptions=True)


# Convenience functions for simple usage

async def discover_ai_services(timeout: float = 3.0) -> List[AIService]:
    """
    Async function to discover services
    
    Args:
        timeout: How long to wait for discovery
        
    Returns:
        List of discovered AI services
    """
    client = ZeroConfAIClient()
    client.start_discovery()
    
    # Wait for discovery asynchronously
    await client.wait_for_services(timeout)
    
    services = client.get_services()
    client.stop_discovery()
    
    return services


async def query_ai(
    prompt: str, 
    max_tokens: int = 100,
    temperature: float = 0.7,
    timeout: float = 5.0
) -> Optional[str]:
    """
    Simple async function to query any available AI service
    
    Args:
        prompt: The prompt text
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        timeout: Discovery timeout
        
    Returns:
        Generated text or None if no services available
    """
    client = ZeroConfAIClient()
    client.start_discovery()
    
    # Wait for discovery
    found = await client.wait_for_services(timeout)
    
    if not found:
        logger.warning("No AI services found on network")
        client.stop_discovery()
        return None
    
    try:
        result = await client.complete(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return result.get("text")
    finally:
        client.stop_discovery()


# Example usage modes
async def test_mode():
    """Run automated tests with CONCURRENT prompts to stress test the system"""
    
    client = ZeroConfAIClient(load_balancer=LatencyAwareBalancer())
    client.start_discovery()
    
    print("Discovering AI services on network...")
    found = await client.wait_for_services(timeout=3.0)
    
    if not found:
        print("No AI services found! Make sure server.py is running.")
        client.stop_discovery()
        return
    
    services = client.get_services()
    print(f"\nFound {len(services)} AI service(s):")
    for service in services:
        print(f"  - {service}")
    
    # Test CONCURRENT completions - this is the power of async!
    print("\n=== Running Concurrent Test Prompts ===")
    prompts = [
        "Write a haiku about distributed systems",
        "Explain TCP/IP in one sentence",
        "What is the meaning of life?",
        "Generate a list of 5 random animals",
    ]
    
    print(f"Sending {len(prompts)} requests concurrently...")
    start_time = time.time()
    
    # Create all completion tasks at once
    tasks = [
        client.complete(prompt=prompt, max_tokens=100)
        for prompt in prompts
    ]
    
    # Run them all concurrently and gather results
    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        print(f"\nAll {len(prompts)} requests completed in {elapsed:.2f}s")
        print("(Sequential would have taken ~{:.2f}s)\n".format(
            sum(s.avg_response_time for s in services if s.response_times) * len(prompts)
        ))
        
        # Display results
        for prompt, response in zip(prompts, responses):
            print(f"\nPrompt: {prompt}")
            if isinstance(response, Exception):
                print(f"Error: {response}")
            else:
                print(f"Response: {response['text'][:100]}...")
                
    except Exception as e:
        print(f"Concurrent execution failed: {e}")
    
    # Show service metrics after concurrent load
    print("\n=== Service Metrics After Concurrent Load ===")
    for service in services:
        print(f"{service.name}:")
        print(f"  Requests handled: {len(service.response_times)}")
        print(f"  Avg Response Time: {service.avg_response_time:.2f}s")
        print(f"  Errors: {service.error_count}")
    
    client.stop_discovery()


async def interactive_mode():
    """Interactive prompt mode - this is what end users experience"""
    
    print("ZeroConfAI Interactive Mode")
    print("Discovering AI services...")
    
    # Create persistent client for the entire session
    client = ZeroConfAIClient()
    client.start_discovery()
    
    # Wait for discovery
    found = await client.wait_for_services(timeout=3.0)
    
    if not found:
        print("No AI services found! Make sure server.py is running.")
        client.stop_discovery()
        return
    
    services = client.get_services()
    print(f"Connected to {len(services)} AI service(s)")
    
    # Perform initial health check
    print("Checking service health...")
    await client.health_check_all()
    
    healthy = [s for s in services if s.is_healthy]
    if not healthy:
        print("No healthy services available!")
        client.stop_discovery()
        return
    
    print(f"{len(healthy)} healthy service(s) ready")
    print("Type 'quit' to exit\n")
    
    while True:
        try:
            # Get user input - NOTE: No technical params needed!
            prompt = input("You: ").strip()
            
            if prompt.lower() in ['quit', 'exit', 'q']:
                break
            
            if not prompt:
                continue
            
            # Make the request with sensible defaults
            # User doesn't need to know about models, tokens, temperature
            response = await client.complete(
                prompt=prompt,
                max_tokens=200,  # Reasonable default
                temperature=0.7   # Reasonable default
            )
            
            print(f"AI: {response['text']}\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}\n")
    
    client.stop_discovery()
    print("\nGoodbye!")


async def developer_mode():
    
    print("=== Developer Integration Example ===\n")
    print("# In your media player app:")
    print("from zeroconf_ai_client import query_ai\n")
    print("# That's the only import needed!\n")
    
    # This is ALL a developer needs to add AI to their app
    user_mood = "relaxing evening"
    prompt = f"Generate a playlist for a {user_mood}. Return 5 song suggestions."
    
    print(f"# User selected mood: {user_mood}")
    print("# Making AI request...")
    
    result = await query_ai(prompt, max_tokens=150)
    
    if result:
        print(f"\n# AI Response:\n{result}")
    else:
        print("\n# No AI service available - feature disabled")
    
    print("\n# The media player handles the response and creates the playlist")
    print("# User never sees any technical details!")


async def main():
    """Main entry point with menu"""
    
    print("ZeroConfAI Client Demo")
    print("=" * 40)
    print("1. Interactive Mode (chat with AI)")
    print("2. Test Mode (run test prompts)")
    print("3. Developer Example (integration demo)")
    print()
    
    choice = input("Select mode (1-3): ").strip()
    
    if choice == "1":
        await interactive_mode()
    elif choice == "2":
        await test_mode()
    elif choice == "3":
        await developer_mode()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    # Setup logging (less verbose for interactive use)
    logging.basicConfig(
        level=logging.WARNING,
        format='%(message)s'
    )
    
    # Run the selected mode
    asyncio.run(main())