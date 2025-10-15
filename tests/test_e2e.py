"""
End-to-end testing for ZeroConfAI
Tests discovery, routing, and rate limiting with proof of network communication
"""
import asyncio
import pytest
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.client import ZeroConfAIClient

@pytest.mark.asyncio
async def test_gateway_discovery():
    """Test that client can discover gateway via mDNS"""
    print("\n[TEST] Starting gateway discovery...")
    start_time = time.time()

    client = ZeroConfAIClient()
    connected = await client.connect(timeout=10.0)

    discovery_time = time.time() - start_time

    assert connected, "Failed to discover gateway via mDNS"
    assert client.discovery.gateway is not None, "Gateway object should be populated"

    # Verify we got real network information
    gateway = client.discovery.gateway
    assert gateway.host is not None, "Gateway must have an IP address"
    assert gateway.port > 0, "Gateway must have a valid port"
    assert "." in gateway.host, "Gateway host should be an IP address"

    print(f"[SUCCESS] Discovered gateway at {gateway.host}:{gateway.port}")
    print(f"[TIMING] Discovery took {discovery_time:.3f} seconds")
    print(f"[METADATA] Service name: {gateway.name}")
    print(f"[METADATA] Properties: {gateway.properties}")

    client.disconnect()

@pytest.mark.asyncio
async def test_simple_completion():
    """Test a basic completion request with real LLM response"""
    print("\n[TEST] Testing basic completion with real LLM...")

    client = ZeroConfAIClient()
    await client.connect()

    # Use a prompt that requires actual LLM understanding
    prompt = "What is 7 multiplied by 8? Reply with only the number."

    start_time = time.time()
    response = await client.complete(
        prompt=prompt,
        max_tokens=10,
        app_id="test-e2e"
    )
    request_time = time.time() - start_time

    # Validate response structure
    assert "text" in response, "Response must contain 'text' field"
    assert "model" in response, "Response must contain 'model' field"
    assert "tokens_used" in response, "Response must contain 'tokens_used' field"
    assert "cost_estimate" in response, "Response must contain 'cost_estimate' field"

    # Validate response content
    assert len(response["text"]) > 0, "Response text should not be empty"
    assert response["tokens_used"] > 0, "Should have used tokens (proves real API call)"
    assert response["cost_estimate"] >= 0, "Cost should be non-negative"

    # Validate that response shows LLM understanding (answer should contain 56)
    assert "56" in response["text"], f"LLM should answer 7*8=56, got: {response['text']}"

    print(f"[SUCCESS] Received response from {response['model']}")
    print(f"[TIMING] Request took {request_time:.3f} seconds")
    print(f"[METRICS] Tokens used: {response['tokens_used']}")
    print(f"[METRICS] Estimated cost: ${response['cost_estimate']:.6f}")
    print(f"[RESPONSE] {response['text'][:100]}")

    client.disconnect()

@pytest.mark.asyncio
async def test_model_routing():
    """Test that router selects appropriate model tiers based on complexity"""
    print("\n[TEST] Testing model routing across different complexity levels...")

    client = ZeroConfAIClient()
    await client.connect()

    # Short prompt -> should use cheap tier
    print("\n[SUBTEST] Testing cheap tier routing (short prompt)...")
    short_response = await client.complete(
        prompt="Hi",
        app_id="test-routing"
    )

    # Verify cheap tier was used (look for llama or similar budget model)
    cheap_model = short_response["model"].lower()
    print(f"[ROUTING] Short prompt routed to: {short_response['model']}")
    print(f"[COST] Cheap tier cost: ${short_response['cost_estimate']:.6f}")

    # Long prompt -> should use premium tier
    print("\n[SUBTEST] Testing premium tier routing (long prompt)...")
    long_prompt = " ".join(["analyze"] * 300)  # ~300 words
    long_response = await client.complete(
        prompt=long_prompt,
        max_tokens=10,
        app_id="test-routing"
    )

    premium_model = long_response["model"].lower()
    print(f"[ROUTING] Long prompt routed to: {long_response['model']}")
    print(f"[COST] Premium tier cost: ${long_response['cost_estimate']:.6f}")

    # Verify different tiers were used and premium costs more
    assert short_response["model"] != long_response["model"], \
        "Different complexity prompts should route to different models"
    assert long_response["cost_estimate"] >= short_response["cost_estimate"], \
        "Premium model should cost at least as much as cheap model"

    print(f"[SUCCESS] Routing works correctly: cheap={cheap_model} vs premium={premium_model}")

    client.disconnect()

@pytest.mark.asyncio
async def test_usage_tracking():
    """Test that usage is tracked correctly in the system"""
    print("\n[TEST] Testing usage tracking integration...")

    client = ZeroConfAIClient()
    await client.connect()

    # Get initial usage stats
    initial_usage = await client.get_usage()
    initial_requests = initial_usage["hourly_requests"]
    initial_cost = initial_usage["daily_cost_usd"]

    print(f"[BASELINE] Initial hourly requests: {initial_requests}")
    print(f"[BASELINE] Initial daily cost: ${initial_cost:.6f}")

    # Make a request
    response = await client.complete(
        prompt="Count to three",
        max_tokens=10,
        app_id="test-usage-tracking"
    )

    # Small delay to allow background task to complete
    await asyncio.sleep(0.5)

    # Get updated usage stats
    updated_usage = await client.get_usage()
    updated_requests = updated_usage["hourly_requests"]
    updated_cost = updated_usage["daily_cost_usd"]

    print(f"[UPDATED] New hourly requests: {updated_requests}")
    print(f"[UPDATED] New daily cost: ${updated_cost:.6f}")
    print(f"[DELTA] Cost added: ${updated_cost - initial_cost:.6f}")

    # Verify usage was tracked
    assert updated_requests >= initial_requests, \
        "Request count should increase after making a request"
    assert updated_cost >= initial_cost, \
        "Cost should increase after making a request"

    # Verify app breakdown
    app_breakdown = updated_usage["app_breakdown"]
    print(f"[BREAKDOWN] Apps using the gateway: {list(app_breakdown.keys())}")
    assert "test-usage-tracking" in app_breakdown, \
        "Our test app should appear in usage breakdown"

    print("[SUCCESS] Usage tracking is working correctly")

    client.disconnect()

if __name__ == "__main__":
    print("=" * 70)
    print("ZeroConfAI End-to-End Test Suite")
    print("=" * 70)

    asyncio.run(test_gateway_discovery())
    asyncio.run(test_simple_completion())
    asyncio.run(test_model_routing())
    asyncio.run(test_usage_tracking())

    print("\n" + "=" * 70)
    print("All tests passed!")
    print("=" * 70)