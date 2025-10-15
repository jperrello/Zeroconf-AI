# ZeroConf AI: Technical Design Fiction

## Core Protocol Design

### mDNS Service Discovery
- **Service Type**: `_zeroconfai._tcp.local.`
- **Port Range**: 8000-9000 (configurable)
- **TXT Record Fields**:
  - `version=1.0` - Protocol version
  - `models=gpt-4,claude-3,llama-2` - Comma-separated available models
  - `provider=openai|anthropic|ollama|router-llm|custom`
  - `capabilities=completion,streaming,embeddings,vision`
  - `auth=none|token|mtls` - Authentication mechanism
  - `priority=100` - Server priority (lower = preferred)
  - `cost=free|metered|subscription` - Cost model indicator
  - `backend=local|proxy` - Inference location
  - `admin=admin@home.local` - Admin contact

### HTTP API Specification

#### Service Endpoint Structure
```
http://{hostname}:{port}/v1/
```

#### Core Endpoints
- `GET /v1/models` - List available models with capabilities
- `POST /v1/completions` - Text completion (streaming/non-streaming)
- `POST /v1/chat/completions` - Chat-style completion
- `POST /v1/embeddings` - Vector embeddings generation
- `GET /v1/health` - Server health/availability
- `GET /v1/status` - Usage stats, queue depth, rate limits

#### Request/Response Format
- **Content-Type**: `application/json`
- **Streaming**: Server-Sent Events (SSE) for streaming responses
- **Error Format**: Standard JSON with `error.type`, `error.message`, `error.code`

### Authentication Mechanisms

#### Option 1: No Auth (LAN Trust)
- Trust local network boundary
- MAC address filtering at server level

#### Option 2: Token-Based
- Server broadcasts token via mDNS TXT record (rotated hourly)
- Client includes `Authorization: Bearer {token}` header
- Token broadcast encrypted with local network PSK

#### Option 3: mTLS
- Server generates CA, signs client certs on first discovery
- Cert pinning for subsequent connections
- Auto-renewal before expiration

## Client Implementation

### Discovery Manager
```python
class DiscoveryManager:
    - async scan_network() -> List[Provider]
    - watch_for_changes(callback) -> None
    - filter_by_capabilities(caps) -> List[Provider]
    - select_best_provider(preferences) -> Provider
```

### Provider Selection Logic
1. Filter by required capabilities
2. Sort by priority value (TXT record)
3. Check health endpoint
4. Apply user preferences (pinned provider, cost preference)
5. Fallback chain if primary fails

### Connection Pooling
- Maintain persistent connections to discovered providers
- Max 5 concurrent connections per provider
- Reconnect on network change events
- Health check every 30s for active providers

### Session Continuity
- **Provider ID**: Hash of hostname + MAC address
- **Session Store**: SQLite DB mapping conversations to provider IDs
- **Migration Logic**: If provider disappears mid-session:
  1. Attempt reconnect (5s timeout)
  2. Query for equivalent model on other providers
  3. Inject context summary to new provider
  4. Log provider switch to user

## Server Implementation

### Backend Abstraction Layer
```python
class BackendAdapter:
    - normalize_request(request) -> backend_format
    - normalize_response(backend_response) -> standard_format
    - supports_streaming() -> bool
    - get_model_info() -> ModelMetadata
```

### Supported Backend Adapters
- **OpenAI API** (direct or proxy)
- **Anthropic API**
- **Ollama** (localhost:11434)
- **Router-LLM** (dynamic routing logic)
- **LiteLLM** (unified interface)
- **vLLM** (local inference)
- **llama.cpp server**

### Configuration Schema
```yaml
server:
  hostname: "ai-server-1"
  port: 8080
  priority: 100
  auth_mode: token  # none|token|mtls

backends:
  - name: "ollama-local"
    type: ollama
    endpoint: "http://localhost:11434"
    models:
      - llama-2-7b
      - codellama-13b
    
  - name: "openai-proxy"
    type: openai
    api_key: ${OPENAI_API_KEY}
    models:
      - gpt-4
      - gpt-3.5-turbo
    cost_limit: 50.00  # USD/month
    
  - name: "router"
    type: router-llm
    routing_logic: "complexity_based"
    fallback_chain: ["ollama-local", "openai-proxy"]

usage_tracking:
  enabled: true
  storage: sqlite  # sqlite|postgres|influxdb
  alerts:
    - type: cost_threshold
      value: 40.00
      notify: admin@home.local
```

### mDNS Broadcasting
- Use `python-zeroconf` library
- Broadcast on service start
- Update TXT records when config changes
- Graceful unregister on shutdown
- TTL: 120 seconds with refresh every 60s

### Usage Tracking
- Per-user token counting (IP-based attribution)
- Per-model cost accumulation
- Rate limiting: token/minute, requests/minute
- Admin dashboard at `/admin/usage`
- Export to CSV/JSON

## Network Architecture

### Discovery Flow
1. Client broadcasts mDNS query for `_zeroconfai._tcp.local.`
2. Servers respond with TXT records + IP addresses
3. Client queries `/v1/health` to verify reachability
4. Client caches provider list with 5min TTL

### Request Flow
1. Client selects provider from cached list
2. Establish HTTP/2 connection (or reuse pooled)
3. Send completion request with timeout (30s default)
4. Handle streaming response or wait for full response
5. On error: retry with exponential backoff, then try next provider

### Provider Update Flow
1. Client maintains background mDNS listener
2. On new provider: add to available pool
3. On provider removed: mark as unavailable, migrate sessions
4. On TXT record change: update capabilities, re-evaluate selection

## Edge Cases & Error Handling

### Multiple Providers, Same Model
- Prioritize by `priority` TXT field
- Load balance if priorities equal
- Sticky sessions for multi-turn conversations

### Provider Disappears Mid-Request
- Timeout after 30s
- Retry once on same provider
- Fallback to next provider with same model
- If streaming: attempt to resume from last token
- Return error if no alternatives available

### No Providers Available
- Client should cache last successful provider list
- Display user-friendly error: "No AI providers found on network"
- Optionally: fallback to direct cloud API with user consent

### Model Unavailable on Preferred Provider
- Check other providers for same model
- Offer user alternative models with capabilities mapping
- Remember user choice for future requests

### Network Segmentation
- Clients may not see all providers (VLANs, subnets)
- Firewall rules must allow mDNS multicast (224.0.0.251:5353)
- Server HTTP ports must be accessible from client subnet

### Cost Exhaustion
- Server returns `429 Too Many Requests` with `Retry-After` header
- Client displays quota exhaustion message
- Admin gets notification (email/webhook)

## Security Considerations

### Threat Model
- **In Scope**: Malicious actor on local network
- **Out of Scope**: Internet-based attacks (assume firewall)

### Mitigations
- Default to token-based auth minimum
- Rate limiting per IP address
- Input validation on all endpoints
- No execution of user code on server
- Audit logging of all requests
- TLS optional but recommended (self-signed OK)

### Privacy
- No request logging by default (opt-in)
- Personal data stays on local network
- Admin can enable request/response logging for debugging

## Performance Targets

### Discovery Latency
- Initial scan: < 2s
- Provider update detection: < 1s

### Request Latency
- Overhead vs direct backend call: < 50ms
- Time to first token (streaming): < 500ms

### Throughput
- Concurrent users per server: 20+
- Requests/second per server: 10+

### Resource Usage (Server)
- RAM: < 100MB baseline
- CPU: < 5% idle, < 30% under load
- Network: minimal (proxy passthrough)

## Implementation Phases

### Phase 1: MVP
- mDNS broadcasting/discovery
- Single backend support (Ollama)
- Basic completion endpoint
- No auth
- Python server + client library

### Phase 2: Multi-Backend
- Backend adapter abstraction
- Support OpenAI, Anthropic, LiteLLM
- Configuration file loading
- Basic usage tracking

### Phase 3: Robustness
- Token authentication
- Provider failover logic
- Session continuity
- Health monitoring

### Phase 4: Advanced
- mTLS support
- Router-LLM integration
- Admin dashboard
- Client SDK for multiple languages

## Open Questions

1. **Model aliasing**: Map "generic-chat" → provider-specific models?
2. **Prompt caching**: Cache at server or rely on backend?
3. **Multi-modal**: Image/audio handling for vision/speech models?
4. **Federation**: Can providers discover each other for load balancing?
5. **Offline mode**: Local SQLite cache of past responses?
6. **Version negotiation**: How to handle protocol version mismatches?
7. **Model metadata**: Temperature limits, context windows, costs - TXT record or API?
8. **IPv6 support**: Does mDNS work correctly in IPv6-only networks?
9. **Container networking**: Docker bridge networks vs host networking?
10. **WebSocket alternative**: For bidirectional streaming and lower latency?
