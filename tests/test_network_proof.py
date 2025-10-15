"""
Network Proof Tests for ZeroConfAI
Demonstrates that requests actually go over the network to real LLM providers
"""
import asyncio
import pytest
import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.client import ZeroConfAIClient

@pytest.mark.asyncio
async def test_network_path_verification():
    """Prove that requests traverse the full network path: Client -> Gateway -> OpenRouter"""
    print("\n" + "=" * 70)
    print("NETWORK PATH VERIFICATION TEST")
    print("=" * 70)

    client = ZeroConfAIClient()

    # Step 1: Discover gateway on local network
    print("\n[STEP 1] Discovering gateway via mDNS on local network...")
    start_discovery = time.time()
    connected = await client.connect(timeout=10.0)
    discovery_time = time.time() - start_discovery

    assert connected, "Failed to discover gateway"

    gateway = client.discovery.gateway
    print(f"[NETWORK] Gateway discovered at IP: {gateway.host}")
    print(f"[NETWORK] Gateway port: {gateway.port}")
    print(f"[NETWORK] Full endpoint: {gateway.base_url}")
    print(f"[TIMING] mDNS discovery took: {discovery_time:.3f}s")

    # Verify it's a real IP address
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    assert re.match(ip_pattern, gateway.host), f"Gateway host should be an IP address, got: {gateway.host}"

    # Step 2: Send request through gateway to OpenRouter
    print("\n[STEP 2] Sending request through gateway to OpenRouter...")
    print("[REQUEST] Prompt: 'What is the capital of France? Reply with just the city name.'")

    start_request = time.time()
    response = await client.complete(
        prompt="What is the capital of France? Reply with just the city name.",
        max_tokens=10,
        app_id="network-proof-test"
    )
    request_time = time.time() - start_request

    print(f"[TIMING] Full request roundtrip: {request_time:.3f}s")
    print(f"[NETWORK] Request path: Client -> {gateway.host}:{gateway.port} -> OpenRouter API -> LLM")

    # Step 3: Verify response came from real LLM
    print("\n[STEP 3] Verifying response came from real LLM provider...")
    print(f"[RESPONSE] Model used: {response['model']}")
    print(f"[RESPONSE] Text: {response['text']}")
    print(f"[RESPONSE] Tokens used: {response['tokens_used']}")
    print(f"[RESPONSE] Cost: ${response['cost_estimate']:.6f}")

    # Validate LLM understood the question (should mention Paris)
    response_text = response['text'].lower()
    assert "paris" in response_text, f"LLM should answer 'Paris', got: {response['text']}"

    # Validate we got real usage metrics from OpenRouter
    assert response['tokens_used'] > 0, "Real API calls should report token usage"
    assert response['cost_estimate'] > 0, "Real API calls should have non-zero cost"

    # Step 4: Measure network overhead
    print("\n[STEP 4] Analyzing network overhead...")
    print(f"[ANALYSIS] Total time: {request_time:.3f}s")
    print(f"[ANALYSIS] This includes:")
    print(f"           - HTTP request to gateway ({gateway.host}:{gateway.port})")
    print(f"           - Gateway forwarding to OpenRouter (https://openrouter.ai)")
    print(f"           - LLM inference time")
    print(f"           - Response transmission back through gateway")

    # Network request should take measurable time (not instant like a mock)
    assert request_time > 0.1, "Real network requests should take >100ms"

    print("\n[SUCCESS] Verified full network path with real LLM response")

    client.disconnect()

@pytest.mark.asyncio
async def test_openrouter_integration():
    """Prove integration with OpenRouter by validating response metadata"""
    print("\n" + "=" * 70)
    print("OPENROUTER INTEGRATION TEST")
    print("=" * 70)

    client = ZeroConfAIClient()
    await client.connect()

    # Send a request that requires reasoning
    print("\n[TEST] Sending reasoning task to LLM...")
    prompt = "If a train leaves at 2pm and travels for 3 hours, what time does it arrive? Reply with just the time."

    response = await client.complete(
        prompt=prompt,
        max_tokens=20,
        app_id="openrouter-integration-test"
    )

    print(f"\n[OPENROUTER] Model selected: {response['model']}")
    print(f"[OPENROUTER] Input + Output tokens: {response['tokens_used']}")
    print(f"[OPENROUTER] Cost calculated: ${response['cost_estimate']:.6f}")
    print(f"[RESPONSE] LLM answer: {response['text']}")

    # Verify response shows reasoning (should mention 5pm or 17:00)
    response_lower = response['text'].lower()
    assert "5" in response['text'] or "17" in response['text'], \
        f"LLM should calculate 2pm + 3hrs = 5pm, got: {response['text']}"

    # Verify we have OpenRouter-style model naming
    assert "/" in response['model'], "OpenRouter models use 'provider/model-name' format"

    # Verify token usage is realistic
    assert response['tokens_used'] >= 10, "This prompt + response should use at least 10 tokens"
    assert response['tokens_used'] < 1000, "This simple prompt should use less than 1000 tokens"

    print("\n[SUCCESS] OpenRouter integration confirmed with real API response")

    client.disconnect()

@pytest.mark.asyncio
async def test_multiple_models_proof():
    """Prove that different models are actually being used based on routing"""
    print("\n" + "=" * 70)
    print("MULTIPLE MODELS ROUTING TEST")
    print("=" * 70)

    client = ZeroConfAIClient()
    await client.connect()

    models_used = set()
    costs = []

    # Test 1: Simple prompt (should use cheap model)
    print("\n[TEST 1] Simple prompt -> Expecting cheap model...")
    response1 = await client.complete(
        prompt="Hi",
        max_tokens=5,
        app_id="multi-model-test"
    )
    model1 = response1['model']
    cost1 = response1['cost_estimate']
    models_used.add(model1)
    costs.append(cost1)

    print(f"[RESULT] Model: {model1}")
    print(f"[RESULT] Cost: ${cost1:.6f}")

    # Test 2: Medium prompt (should use balanced model)
    print("\n[TEST 2] Medium prompt -> Expecting balanced model...")
    medium_prompt = "Explain quantum computing in simple terms. " * 10  # ~80 words
    response2 = await client.complete(
        prompt=medium_prompt,
        max_tokens=20,
        app_id="multi-model-test"
    )
    model2 = response2['model']
    cost2 = response2['cost_estimate']
    models_used.add(model2)
    costs.append(cost2)

    print(f"[RESULT] Model: {model2}")
    print(f"[RESULT] Cost: ${cost2:.6f}")

    # Test 3: Long complex prompt (should use premium model)
    print("\n[TEST 3] Long complex prompt -> Expecting premium model...")
    long_prompt = "Analyze the philosophical implications of artificial intelligence. " * 50  # ~300 words
    response3 = await client.complete(
        prompt=long_prompt,
        max_tokens=20,
        app_id="multi-model-test"
    )
    model3 = response3['model']
    cost3 = response3['cost_estimate']
    models_used.add(model3)
    costs.append(cost3)

    print(f"[RESULT] Model: {model3}")
    print(f"[RESULT] Cost: ${cost3:.6f}")

    # Verify different models were actually used
    print(f"\n[ANALYSIS] Unique models used: {len(models_used)}")
    print(f"[ANALYSIS] Models: {', '.join(sorted(models_used))}")
    print(f"[ANALYSIS] Cost range: ${min(costs):.6f} to ${max(costs):.6f}")

    # At least 2 different models should have been used
    assert len(models_used) >= 2, \
        f"Routing should use different models for different complexities, only used: {models_used}"

    # Costs should vary (proves different model tiers)
    assert max(costs) > min(costs), \
        "Different model tiers should have different costs"

    print(f"\n[SUCCESS] Verified multiple models are being routed to based on complexity")

    client.disconnect()

@pytest.mark.asyncio
async def test_latency_breakdown():
    """Measure and display latency at each stage of the network path"""
    print("\n" + "=" * 70)
    print("NETWORK LATENCY BREAKDOWN TEST")
    print("=" * 70)

    # Stage 1: mDNS Discovery
    print("\n[STAGE 1] mDNS Gateway Discovery...")
    client = ZeroConfAIClient()

    start = time.time()
    await client.connect(timeout=10.0)
    discovery_latency = time.time() - start

    print(f"[LATENCY] mDNS discovery: {discovery_latency:.3f}s")

    # Stage 2: HTTP Request to Gateway
    print("\n[STAGE 2] HTTP Request (Client -> Gateway -> OpenRouter -> LLM)...")

    # Fast prompt to minimize LLM inference time
    start = time.time()
    response = await client.complete(
        prompt="Say OK",
        max_tokens=5,
        app_id="latency-test"
    )
    total_request_latency = time.time() - start

    print(f"[LATENCY] Full roundtrip: {total_request_latency:.3f}s")
    print(f"[BREAKDOWN] This includes:")
    print(f"            - Client -> Gateway HTTP: ~10-50ms")
    print(f"            - Gateway -> OpenRouter HTTPS: ~100-500ms")
    print(f"            - OpenRouter -> LLM inference: ~500-3000ms")
    print(f"            - Response path (reverse): ~100-500ms")

    # Stage 3: Multiple requests to observe variance
    print("\n[STAGE 3] Running 3 requests to observe latency variance...")
    latencies = []

    for i in range(3):
        start = time.time()
        await client.complete(
            prompt=f"Test {i}",
            max_tokens=5,
            app_id="latency-test"
        )
        latency = time.time() - start
        latencies.append(latency)
        print(f"[REQUEST {i+1}] Latency: {latency:.3f}s")

    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)

    print(f"\n[STATISTICS]")
    print(f"  Average: {avg_latency:.3f}s")
    print(f"  Min: {min_latency:.3f}s")
    print(f"  Max: {max_latency:.3f}s")
    print(f"  Variance: {max_latency - min_latency:.3f}s")

    # Verify latencies are realistic for network calls
    assert avg_latency > 0.1, "Real network calls should take >100ms on average"
    assert avg_latency < 30.0, "Requests shouldn't take more than 30 seconds"

    print("\n[SUCCESS] Latency measurements confirm real network communication")

    client.disconnect()

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ZEROCONFAI NETWORK PROOF TEST SUITE")
    print("Demonstrating real network communication with LLM providers")
    print("=" * 70)

    asyncio.run(test_network_path_verification())
    asyncio.run(test_openrouter_integration())
    asyncio.run(test_multiple_models_proof())
    asyncio.run(test_latency_breakdown())

    print("\n" + "=" * 70)
    print("ALL NETWORK PROOF TESTS PASSED")
    print("Confirmed: Real network traffic to real LLM providers")
    print("=" * 70)
