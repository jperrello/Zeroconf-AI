# ZeroConfAI Test Suite

This directory contains comprehensive tests for the ZeroConfAI system, demonstrating real network communication with LLM providers.

## Test Files

### test_e2e.py
**End-to-end functional tests** covering the core features:
- Gateway discovery via mDNS
- Basic completion requests with LLM validation
- Model routing based on complexity
- Usage tracking integration

Run with: `pytest tests/test_e2e.py -v -s`

### test_network_proof.py
**Network verification tests** that prove real network communication:
- Network path verification (Client -> Gateway -> OpenRouter)
- OpenRouter integration with metadata validation
- Multiple model routing demonstration
- Latency breakdown and timing analysis

Run with: `pytest tests/test_network_proof.py -v -s`

### test_demo.py
**Executive demonstration** - A single comprehensive test perfect for live demos:
- Step-by-step walkthrough with detailed output
- Proves real network traffic and LLM responses
- Shows all system capabilities in one test
- Great for presenting to stakeholders

Run directly: `python tests/test_demo.py`

Or with pytest: `pytest tests/test_demo.py -v -s`

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

### Run all tests:
```bash
pytest tests/ -v -s
```

### Run specific test file:
```bash
pytest tests/test_e2e.py -v -s
```

### Run specific test:
```bash
pytest tests/test_e2e.py::test_gateway_discovery -v -s
```

### Run demo for boss presentation:
```bash
python tests/test_demo.py
```

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

1. Run `test_demo.py` directly (not through pytest) for cleanest output
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
