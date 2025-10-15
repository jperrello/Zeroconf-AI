# ZeroConfAI Test Suite

This directory contains comprehensive tests for the ZeroConfAI system, demonstrating real network communication with LLM providers.

## Test Files

### test_integration.py
**Comprehensive integration tests** covering all system functionality:
- Gateway discovery via mDNS with network validation
- Basic completion requests with LLM validation
- Full network path verification (Client -> Gateway -> OpenRouter -> LLM)
- Model routing based on complexity
- Multiple model access validation
- Usage tracking integration
- Latency analysis and timing validation

Run all tests:
```bash
pytest tests/test_integration.py -v -s
```

Run specific test:
```bash
pytest tests/test_integration.py::test_gateway_discovery -v -s
```

### Available Test Functions:
- `test_gateway_discovery` - mDNS discovery with IP validation
- `test_basic_completion` - Basic LLM request/response
- `test_network_path_validation` - Full network path verification
- `test_model_routing` - Complexity-based model selection
- `test_multiple_models` - Multiple model tier validation
- `test_usage_tracking` - Usage tracking integration
- `test_latency_analysis` - Network timing validation

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the gateway server** (in a separate terminal):
   ```bash
   python -m src.server
   ```

3. **Set environment variables:**
   ```bash
   # Windows
   set OPENROUTER_API_KEY=your_key_here

   # Linux/Mac
   export OPENROUTER_API_KEY=your_key_here
   ```

## Running Tests

### Run all integration tests:
```bash
pytest tests/test_integration.py -v -s
```

### Run specific test:
```bash
pytest tests/test_integration.py::test_gateway_discovery -v -s
```

### Run live demonstration (for presentations):
```bash
python examples/demo.py
```

The demo script (`examples/demo.py`) provides a step-by-step executive presentation showing all system capabilities with detailed output formatting - perfect for stakeholder demonstrations.

## Test Output Flags

- `-v` : Verbose output showing test names
- `-s` : Show print statements (essential for seeing detailed output)
- `--tb=short` : Shorter traceback on failures (already configured in pytest.ini)

## What the Tests Prove

These tests demonstrate:

1. **Real Network Communication**
   - Actual IP addresses discovered via mDNS
   - Measurable network latency (not instant mocks)
   - HTTP requests going over real network interfaces

2. **Real LLM Integration**
   - Responses from OpenRouter cloud API
   - Multiple real models (GPT-4, Claude, Llama)
   - Token usage from actual API calls
   - Real costs calculated

3. **System Intelligence**
   - LLMs answer questions correctly (math, reasoning)
   - Model routing based on complexity
   - Cost optimization working

4. **Usage Tracking**
   - Requests logged to database
   - Costs tracked accurately
   - Per-app breakdown working

## Troubleshooting

**"No gateway found"**
- Make sure server is running: `python -m src.server`
- Check firewall isn't blocking port 8000
- Verify mDNS/Bonjour service is running

**"Rate limit exceeded"**
- Wait an hour or adjust MAX_REQUESTS_PER_HOUR in config/settings.py

**"OpenRouter credits exhausted"**
- Add credits at https://openrouter.ai
- Check OPENROUTER_API_KEY is set correctly

**Tests are slow**
- This is expected - real LLM calls take 1-5 seconds
- Network latency is part of what we're proving

## Demo Tips for Presentations

1. Run `examples/demo.py` directly for cleanest presentation output
2. Have server running in visible terminal window
3. Show real-time logs in both terminals
4. Point out network addresses, timing, and costs in output
5. Explain that delays prove real network communication
6. Show usage database after: `sqlite3 zeroconf_ai_usage.db "SELECT * FROM usage ORDER BY timestamp DESC LIMIT 5;"`

## Notes

- Tests require active internet connection (calls OpenRouter API)
- Tests will incur small costs (typically $0.01-0.05 per full test run)
- Some tests may take 30+ seconds due to multiple LLM calls
- First test may be slower due to cold start
