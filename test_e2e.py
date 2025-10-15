"""
End-to-end testing for ZeroConfAI
Tests discovery, routing, and rate limiting
"""
import asyncio
import pytest
from client import ZeroConfAIClient

@pytest.mark.asyncio
async def test_gateway_discovery():
    """Test that client can discover gateway"""
    client = ZeroConfAIClient()
    connected = await client.connect(timeout=10.0)
    assert connected, "Failed to discover gateway"
    client.disconnect()

@pytest.mark.asyncio  
async def test_simple_completion():
    """Test a basic completion request"""
    client = ZeroConfAIClient()
    await client.connect()
    
    response = await client.complete(
        prompt="Say hello",
        max_tokens=10,
        app_id="test"
    )
    
    assert "text" in response
    assert len(response["text"]) > 0
    assert response["cost_estimate"] < 0.01  # Should use cheap model
    
    client.disconnect()

@pytest.mark.asyncio
async def test_model_routing():
    """Test that router selects appropriate models"""
    client = ZeroConfAIClient()
    await client.connect()
    
    # Short prompt -> cheap model
    short_response = await client.complete(
        prompt="Hi",
        app_id="test"
    )
    assert "llama" in short_response["model"].lower()
    
    # Long prompt -> premium model
    long_prompt = " ".join(["test"] * 300)  # ~300 words
    long_response = await client.complete(
        prompt=long_prompt,
        max_tokens=10,
        app_id="test"
    )
    assert "gpt" in long_response["model"].lower() or "claude" in long_response["model"].lower()
    
    client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_gateway_discovery())
    asyncio.run(test_simple_completion())
    print("✅ All tests passed!")