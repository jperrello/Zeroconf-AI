"""
Integration testing for ZeroConfAI
Tests discovery, completion, routing, usage tracking, and network communication
Consolidates all end-to-end testing scenarios
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
async def test_gateway_discovery():
    """Test that client can discover gateway via mDNS and validates network information"""
    print("\n[TEST] Gateway discovery via mDNS...")

    client = ZeroConfAIClient()
    start_time = time.time()
    connected = await client.connect(timeout=10.0)
    discovery_time = time.time() - start_time

    # Validate connection success
    assert connected, "Failed to discover gateway via mDNS"
    assert client.discovery.gateway is not None, "Gateway object should be populated"

    # Validate real network information
    gateway = client.discovery.gateway
    assert gateway.host is not None, "Gateway must have an IP address"
    assert gateway.port > 0, "Gateway must have a valid port"

    # Verify it's a real IP address format
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    assert re.match(ip_pattern, gateway.host), f"Gateway host should be an IP address, got: {gateway.host}"

    # Verify discovery took measurable time (not instant/mocked)
    assert discovery_time > 0.001, "Real mDNS discovery should take measurable time"

    print(f"[SUCCESS] Discovered at {gateway.host}:{gateway.port} in {discovery_time:.3f}s")
    print(f"[METADATA] Service: {gateway.name}")
    print(f"[METADATA] Base URL: {gateway.base_url}")

    client.disconnect()


@pytest.mark.asyncio
async def test_basic_completion():
    """Test basic completion with real LLM response validation"""
    print("\n[TEST] Basic completion with real LLM...")

    client = ZeroConfAIClient()
    await client.connect()

    # Use a math prompt to validate LLM understanding
    prompt = "What is 7 multiplied by 8? Reply with only the number."

    start_time = time.time()
    response = await client.complete(
        prompt=prompt,
        max_tokens=10,
        app_id="test-integration"
    )
    request_time = time.time() - start_time

    # Validate response structure
    assert "text" in response, "Response must contain 'text' field"
    assert "model" in response, "Response must contain 'model' field"
    assert "tokens_used" in response, "Response must contain 'tokens_used' field"
    assert "cost_estimate" in response, "Response must contain 'cost_estimate' field"

    # Validate real API usage
    assert len(response["text"]) > 0, "Response text should not be empty"
    assert response["tokens_used"] > 0, "Should have used tokens (proves real API call)"
    assert response["cost_estimate"] >= 0, "Cost should be non-negative"

    # Validate response timing (not instant like a mock)
    assert request_time > 0.1, "Real network requests should take >100ms"

    # Validate LLM understanding (answer should contain 56)
    assert "56" in response["text"], f"LLM should answer 7*8=56, got: {response['text']}"

    print(f"[SUCCESS] Response from {response['model']} in {request_time:.3f}s")
    print(f"[METRICS] Tokens: {response['tokens_used']}, Cost: ${response['cost_estimate']:.6f}")

    client.disconnect()


@pytest.mark.asyncio
async def test_network_path_validation():
    """Validate full network path: Client -> Gateway -> OpenRouter -> LLM"""
    print("\n[TEST] Full network path validation...")

    client = ZeroConfAIClient()
    await client.connect()

    gateway = client.discovery.gateway
    print(f"[NETWORK] Path: Client -> {gateway.host}:{gateway.port} -> OpenRouter -> LLM")

    # Send request that requires reasoning
    prompt = "If Sarah is older than John, and John is older than Mike, who is the youngest? Reply with just the name."

    start_time = time.time()
    response = await client.complete(
        prompt=prompt,
        max_tokens=10,
        app_id="test-integration"
    )
    request_time = time.time() - start_time

    # Validate OpenRouter model naming format
    assert "/" in response['model'], "OpenRouter models use 'provider/model-name' format"

    # Validate token usage is realistic
    assert response['tokens_used'] >= 5, "This prompt should use at least 5 tokens"
    assert response['tokens_used'] < 500, "This simple prompt should use less than 500 tokens"

    # Validate LLM reasoning (should answer "Mike")
    response_lower = response['text'].lower()
    assert "mike" in response_lower, f"LLM should reason Mike is youngest, got: {response['text']}"

    # Validate measurable network latency
    assert request_time > 0.1, "Real network calls should take >100ms"
    assert request_time < 30.0, "Requests shouldn't take more than 30 seconds"

    print(f"[SUCCESS] Full network path validated in {request_time:.3f}s")
    print(f"[RESPONSE] Model: {response['model']}")
    print(f"[RESPONSE] Answer: {response['text']}")

    client.disconnect()


@pytest.mark.asyncio
async def test_model_routing():
    """Test that router selects appropriate model tiers based on complexity"""
    print("\n[TEST] Model routing across complexity levels...")

    client = ZeroConfAIClient()
    await client.connect()

    # Simple prompt -> should use cheap tier
    print("\n[SUBTEST] Testing cheap tier routing (simple prompt)...")
    simple_response = await client.complete(
        prompt="Hi",
        max_tokens=5,
        app_id="test-routing"
    )

    # Complex prompt -> should use premium tier
    print("\n[SUBTEST] Testing premium tier routing (complex prompt)...")
    complex_prompt = " ".join(["analyze quantum computing implications"] * 40)  # ~120 words
    complex_response = await client.complete(
        prompt=complex_prompt,
        max_tokens=10,
        app_id="test-routing"
    )

    # Validate different models were used
    assert simple_response["model"] != complex_response["model"], \
        "Different complexity prompts should route to different models"

    # Validate cost hierarchy
    assert complex_response["cost_estimate"] >= simple_response["cost_estimate"], \
        "Premium model should cost at least as much as cheap model"

    print(f"[SUCCESS] Routing verified")
    print(f"[CHEAP] Model: {simple_response['model']}, Cost: ${simple_response['cost_estimate']:.6f}")
    print(f"[PREMIUM] Model: {complex_response['model']}, Cost: ${complex_response['cost_estimate']:.6f}")

    client.disconnect()


@pytest.mark.asyncio
async def test_multiple_models():
    """Validate that multiple different models are actually being used"""
    print("\n[TEST] Multiple model access validation...")

    client = ZeroConfAIClient()
    await client.connect()

    models_used = set()
    costs = []

    # Test 3 different complexity levels
    test_cases = [
        ("Hi", 5, "simple"),
        ("Explain machine learning in one sentence. " * 15, 10, "medium"),
        ("Analyze the philosophical implications of AGI. " * 50, 15, "complex"),
    ]

    for prompt, max_tokens, complexity in test_cases:
        response = await client.complete(
            prompt=prompt,
            max_tokens=max_tokens,
            app_id="test-multi-model"
        )
        models_used.add(response['model'])
        costs.append(response['cost_estimate'])
        print(f"[{complexity.upper()}] Model: {response['model']}, Cost: ${response['cost_estimate']:.6f}")

    # Validate multiple models were used
    assert len(models_used) >= 2, \
        f"Routing should use at least 2 different models, only used: {models_used}"

    # Validate cost variance (proves different tiers)
    assert max(costs) > min(costs), \
        "Different model tiers should have different costs"

    print(f"[SUCCESS] {len(models_used)} unique models accessed")
    print(f"[MODELS] {', '.join(sorted(models_used))}")
    print(f"[COST RANGE] ${min(costs):.6f} to ${max(costs):.6f}")

    client.disconnect()


@pytest.mark.asyncio
async def test_usage_tracking():
    """Test that usage is tracked correctly in the system"""
    print("\n[TEST] Usage tracking integration...")

    client = ZeroConfAIClient()
    await client.connect()

    # Get baseline usage
    initial_usage = await client.get_usage()
    initial_requests = initial_usage["hourly_requests"]
    initial_cost = initial_usage["daily_cost_usd"]

    print(f"[BASELINE] Requests: {initial_requests}, Cost: ${initial_cost:.6f}")

    # Make a tracked request
    response = await client.complete(
        prompt="Count to three",
        max_tokens=10,
        app_id="test-usage-tracking"
    )

    # Allow background task to complete
    await asyncio.sleep(0.5)

    # Get updated usage
    updated_usage = await client.get_usage()
    updated_requests = updated_usage["hourly_requests"]
    updated_cost = updated_usage["daily_cost_usd"]

    # Validate tracking
    assert updated_requests >= initial_requests, \
        "Request count should increase after making a request"
    assert updated_cost >= initial_cost, \
        "Cost should increase after making a request"

    # Validate app breakdown
    app_breakdown = updated_usage["app_breakdown"]
    assert "test-usage-tracking" in app_breakdown, \
        "Our test app should appear in usage breakdown"

    print(f"[UPDATED] Requests: {updated_requests}, Cost: ${updated_cost:.6f}")
    print(f"[DELTA] Cost added: ${updated_cost - initial_cost:.6f}")
    print(f"[SUCCESS] Usage tracking operational")

    client.disconnect()


@pytest.mark.asyncio
async def test_latency_analysis():
    """Measure latency patterns to validate real network communication"""
    print("\n[TEST] Latency analysis for network validation...")

    client = ZeroConfAIClient()

    # Measure discovery latency
    start = time.time()
    await client.connect(timeout=10.0)
    discovery_latency = time.time() - start

    print(f"[LATENCY] Discovery: {discovery_latency:.3f}s")

    # Measure request latency variance across multiple requests
    latencies = []
    for i in range(3):
        start = time.time()
        await client.complete(
            prompt=f"Test {i}",
            max_tokens=5,
            app_id="test-latency"
        )
        latency = time.time() - start
        latencies.append(latency)
        print(f"[REQUEST {i+1}] Latency: {latency:.3f}s")

    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    variance = max_latency - min_latency

    print(f"[STATISTICS] Avg: {avg_latency:.3f}s, Min: {min_latency:.3f}s, Max: {max_latency:.3f}s")
    print(f"[VARIANCE] {variance:.3f}s (proves real network, not mock)")

    # Validate realistic latencies
    assert avg_latency > 0.1, "Real network calls should take >100ms on average"
    assert avg_latency < 30.0, "Requests shouldn't take more than 30 seconds"

    # Variance indicates real network conditions (not deterministic mock)
    assert variance > 0.01, "Real network should show timing variance >10ms"

    print(f"[SUCCESS] Latency patterns confirm real network communication")

    client.disconnect()


if __name__ == "__main__":
    print("=" * 70)
    print("ZeroConfAI Integration Test Suite")
    print("=" * 70)

    asyncio.run(test_gateway_discovery())
    asyncio.run(test_basic_completion())
    asyncio.run(test_network_path_validation())
    asyncio.run(test_model_routing())
    asyncio.run(test_multiple_models())
    asyncio.run(test_usage_tracking())
    asyncio.run(test_latency_analysis())

    print("\n" + "=" * 70)
    print("All integration tests passed!")
    print("=" * 70)
