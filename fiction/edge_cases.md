# Saturn: Edge Cases

## Network Topology

- **Multiple VLANs**: Client on guest network can't see provider on main LAN
- **Double NAT**: ISP router + home router breaking mDNS multicast
- **VPN active**: Client's VPN tunnel routes all traffic away from LAN
- **IPv6-only networks**: mDNS behavior differs, dual-stack confusion
- **Mesh WiFi**: Client switches between nodes mid-request
- **WiFi extenders**: mDNS doesn't propagate through repeaters
- **Docker bridge networks**: Container can't see host mDNS broadcasts
- **Kubernetes clusters**: Pod-to-pod networking vs host networking
- **Airplane mode toggle**: Network interface rapidly up/down
- **Ethernet + WiFi simultaneously**: Which interface to prefer?
- **Captive portals**: Hotel/coffee shop WiFi blocking mDNS
- **Cellular hotspot**: No LAN broadcast domain at all

## Multiple Providers

- **Same model, different providers**: Load balancing logic needed
- **Provider priority ties**: How to break tie between priority=50 servers?
- **Flapping availability**: Provider keeps appearing/disappearing
- **Version mismatches**: v1.0 client discovering v2.0 server
- **Duplicate hostnames**: Two servers named "ai-server.local"
- **Split-brain**: Client sees provider A, another client sees provider B
- **Stale cache**: Provider gone but client still has it cached
- **Race conditions**: Two providers respond simultaneously
- **Asymmetric routes**: Can discover but can't reach HTTP port
- **Model subset**: Provider A has GPT-4, Provider B has Claude, need both

## Provider Lifecycle

- **Mid-request shutdown**: Server stops during active streaming response
- **Graceful shutdown ignored**: Server killed without unregistering mDNS
- **Config hot-reload**: Backend list changes while requests in flight
- **Certificate expiry**: mTLS certs expire during long-running session
- **API key rotation**: Backend API key invalidated while proxying
- **Quota exhaustion**: Backend hits rate limit mid-request
- **Out of memory**: Server OOMs under load, kernel kills process
- **Disk full**: Log files fill disk, server hangs
- **Clock skew**: Server time wrong, breaks token expiration logic
- **DNS poisoning**: Malicious mDNS response hijacks traffic

## Client Behavior

- **App backgrounded**: iOS/Android suspend app mid-discovery
- **Battery saver mode**: OS throttles network scanning
- **Offline-first**: Client caches responses, doesn't realize provider available
- **Concurrent apps**: Multiple apps fighting for same provider
- **Request timeout ambiguity**: Network slow vs provider slow vs model slow
- **Retry storms**: Client retries too aggressively, DDOSs provider
- **Stale connections**: TCP connection reused after provider restart
- **DNS caching**: Client caches hostname resolution, misses IP change
- **TLS session resumption**: Breaks when server restarts
- **Cookie persistence**: Client expects stateless, server uses sessions

## Model & Backend Issues

- **Model name changes**: "gpt-4" becomes "gpt-4-0125-preview"
- **Capability drift**: Model updated, capabilities change
- **Context length limits**: Client sends 100k tokens, model supports 32k
- **Streaming support inconsistent**: Model claims streaming but hangs
- **Vision model blind spots**: Image too large, format unsupported
- **Embeddings dimension mismatch**: Client expects 1536, gets 768
- **Temperature clamping**: Backend silently adjusts invalid params
- **System prompts forbidden**: Backend doesn't support system role
- **Function calling formats**: OpenAI vs Anthropic vs custom schema
- **Tokenizer differences**: Client counts tokens wrong, hits limits

## Authentication & Security

- **Token replay**: Attacker captures token from mDNS broadcast
- **ARP spoofing**: Malicious device impersonates provider
- **MAC filtering bypass**: Attacker clones authorized MAC address
- **Certificate pinning**: Client pins cert, server rotates it
- **Shared secret leak**: Token broadcast readable by network sniffer
- **Session hijacking**: Request lacks CSRF protection
- **Injection attacks**: Client sends malicious prompts
- **DoS attacks**: Attacker spams provider with expensive requests
- **Timing attacks**: Auth token validation reveals info via timing
- **Admin panel exposed**: No auth on /admin/usage endpoint

## Cost & Usage

- **Bill shock**: User runs 10k requests, $500 bill
- **Cost attribution**: Multiple users share IP (NAT), who pays?
- **Quota gaming**: User disconnects/reconnects to reset limits
- **Unused provider waste**: Server running, nobody using it, still costs money (if local GPU)
- **Peak pricing**: Cloud backend costs more during business hours
- **Currency conversion**: Admin in USD, backend charges EUR
- **Fractional cents**: Token costs round wrong, accumulate errors
- **Refunds & credits**: Backend refunds tokens, usage tracking doesn't know
- **Shared family plan**: Claude allows 5 users, 6 people on LAN
- **Background requests**: App prefetches, wastes tokens

## Data & Privacy

- **Request logging**: Admin logs PII without user knowledge
- **Conversation replay**: Debugging exposes private chats
- **Cached responses**: Sensitive data persists in cache
- **Backup leakage**: Server backup includes conversation history
- **Metrics collection**: Usage stats reveal user behavior patterns
- **Cross-user contamination**: Model cache leaks between users
- **GDPR compliance**: EU user requests data deletion, where is it?
- **Age-inappropriate content**: Kid accesses adult content via family server
- **Work from home**: Corporate laptop uses home AI, leaks company data
- **Malware scanning**: Antivirus reads API keys from config file

## Performance & Scale

- **Thundering herd**: All clients rediscover on network bounce
- **Queue depth explosion**: 50 requests queued, server melts
- **Memory leaks**: Slow leak eventually crashes server
- **Connection exhaustion**: Server runs out of file descriptors
- **Bandwidth saturation**: Vision requests saturate home uplink
- **Streaming stalls**: Network jitter causes buffering
- **Request amplification**: One client request = 10 backend calls
- **Model loading time**: Local LLM takes 30s to load into VRAM
- **Cold start penalty**: First request slow, subsequent fast
- **Background model updates**: Ollama pulls 7GB update, saturates network

## User Experience

- **No feedback**: User doesn't know why caption failed
- **Silent fallback**: Client switches providers, user confused why slow
- **Partial results**: Streaming cut off, incomplete response shown
- **Duplicate responses**: Retry logic sends request twice, user sees both
- **Model confusion**: User doesn't know which model answered
- **Capability discovery**: User doesn't know vision is available
- **Provider naming**: "ai-server-1" vs "ai-server-2" meaningless to user
- **Error message quality**: "HTTP 500" vs "The AI is taking a nap"
- **Progress indication**: Long request, no feedback, user thinks frozen
- **Multi-language**: Provider names in ASCII, user expects Chinese

## Hardware & Infrastructure

- **Power outage**: Server on battery backup, how long?
- **Thermal throttling**: Raspberry Pi overheats, slows down
- **SD card corruption**: Server won't boot after power loss
- **Router reboot**: Loses DHCP leases, IP addresses change
- **Firmware updates**: Router update breaks mDNS forwarding
- **USB power insufficient**: Pi browns out under GPU load
- **WiFi channel crowding**: Interference causes packet loss
- **Port forwarding conflicts**: Another service using port 8080
- **Firewall rules**: pfSense blocks mDNS by default
- **IoT device spam**: 50 smart devices saturate mDNS traffic

## Integration & Compatibility

- **Platform-specific APIs**: Android mDNS works differently than iOS
- **Browser limitations**: Web apps can't do mDNS discovery
- **Electron quirks**: Desktop app mDNS behaves differently than native
- **Library bugs**: python-zeroconf has race condition
- **OS updates**: macOS 15 changes mDNS behavior
- **Antivirus interference**: Blocks mDNS packets as suspicious
- **Proxy software**: Charles/Fiddler intercepts, breaks connections
- **Corporate MDM**: Mobile device management blocks local network access
- **Ad blockers**: Browser extension blocks WebSocket connections
- **Legacy clients**: Old app version doesn't understand new TXT fields

## Multi-User Scenarios

- **Concurrent edits**: Two users editing same document with AI
- **Session stealing**: User A's conversation appears in User B's app
- **Quota fairness**: One user hogs all tokens
- **Priority conflicts**: Admin request vs regular user request
- **Time zone differences**: Usage reporting in wrong timezone
- **Language preferences**: User wants Spanish, provider only configured for English
- **Accessibility needs**: Screen reader doesn't announce provider changes
- **Parental controls**: No way to restrict kids from expensive models
- **Guest access**: Visitor's phone floods network with discovery requests
- **Shared device**: Multiple users, one phone, usage attribution wrong

## Compliance & Legal

- **Terms of Service**: Backend ToS prohibits proxying
- **License violations**: Local model license forbids commercial use
- **Export controls**: Model can't be used in certain countries
- **Content filtering**: Backend requires safety filters, proxy bypasses
- **Data residency**: GDPR requires EU processing, backend uses US servers
- **Audit trails**: Legal requirement for request logging
- **Age verification**: COPPA compliance for users under 13
- **Accessibility laws**: Provider must support screen readers
- **Right to explanation**: User wants to know why AI said something
- **Warranty disclaimers**: Who's liable when AI gives bad advice?

## Exotic Scenarios

- **Time travel**: Client clock in future, server in past
- **Loop detection**: Provider A proxies to Provider B proxies to Provider A
- **Broadcast storms**: Two servers fight over same hostname
- **Unicode chaos**: Emoji in model names break parsing
- **JSON injection**: Model name contains `"`, breaks JSON
- **Path traversal**: Model name "../../../etc/passwd"
- **XXL requests**: 10MB prompt crashes parser
- **Negative costs**: Backend gives credits, usage goes negative
- **Quantum requests**: Request succeeds AND fails (race condition)
- **Schrödinger's model**: TXT record says available, health check says no
- **Recursion**: AI prompt asks AI to generate prompts for AI
- **Feedback loops**: AI critiques its own output infinitely
- **Cross-provider chains**: Request to A, which calls B, which calls C
- **Zombie providers**: Server process dead, mDNS entry persists
- **Split personality**: Server has two network interfaces, two IPs, same hostname