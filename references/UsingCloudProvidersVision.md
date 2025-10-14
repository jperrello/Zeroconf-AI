# Zeroconf AI project update

**human** (Oct 14, 2025, 01:07 PM)

I'd like to remind you of my Zeroconf AI project. we have had chats about it and I attached all the context. 

I want to talk to you about a new discovery I had. I was talking to my professor about the code so far and he told me to  Avoid ollama for now stick to cloud based provider. I am going to use OpenRouter instead: https://openrouter.ai/docs/quickstart Since i will be using this I was thinking that the pi I need to configure this whole thing doesn't need to be that strong, at the end of the day it is just running an api call. I was originally going to suggest putting this code in the router, but i dont even think routers can run python. Anyways here is a diagram of what this system looks like:

**assistant** (Oct 14, 2025, 01:08 PM)
Looking at your architectural pivot from local Ollama to cloud-based OpenRouter - this is fascinating but also fundamentally changes what you're building. Let me be critical here as you've asked.

**The Good:**
Your Pi becomes a lightweight gateway - basically just running mDNS advertising and proxying HTTP requests. No heavy ML inference, minimal resource requirements. You could probably run this on a $15 Pi Zero W. The code simplifies significantly - no need to worry about model management, just API translation.

**The Concerning:**

Your original vision was brilliant precisely because it *avoided* the cloud dependency. You wrote:
> "apps that would be reluctant to include AI features could perhaps include them now because they don't have to force their users into some complicated technical configuration or grow a whole side business to charge them subscription fees"

But now you're introducing:
1. **API key management** - Someone needs an OpenRouter account and has to pay per token
2. **Internet dependency** - Your "local" AI service dies when the internet goes down
3. **Privacy concerns** - All prompts leave the local network
4. **Latency** - Every request has WAN round-trip time

**Technical Issues in Your Current Code:**

Looking at your `server.py`, you'd need to completely rewrite the `/v1/complete` endpoint:

```python
@app.post("/v1/complete", response_model=CompletionResponse)
async def complete(req: CompletionRequest):
    # This whole function needs rewriting for OpenRouter
    # Where do you store the API key? Environment variable on the Pi?
    # How do you handle rate limits from OpenRouter?
    # What about cost tracking?
```

Your load balancing code becomes mostly irrelevant - you're not balancing between local services anymore, just hitting one cloud endpoint.

**A Critical Question:**
If you're using cloud providers anyway, why do users need local discovery at all? They could just... use OpenRouter directly? What value does the Pi gateway add beyond what a simple browser extension with an API key could provide?

**Alternative Approach:**
Consider a **hybrid model** where your protocol supports both local and cloud backends. Your mDNS advertisement could include:
```python
properties={
    "backend": "cloud",  # or "local"
    "provider": "openrouter",
    "capabilities": "completion,chat",
    "requires_auth": "true"
}
```

This way, power users can still run local Ollama, while others can use cloud gateways. The client library stays the same - it just discovers what's available and uses it.

What's your professor's reasoning for avoiding Ollama? Performance? Setup complexity?

**human** (Oct 14, 2025, 01:20 PM)

answer to your critical question:

well, the reason is partially the scope of the project. currently we are more interested in making Zeroconf AI a thing that exists. This project is more to help open source developers who want to incorporate AI into their apps but they don't want to configure API keys or force users to pay for a subscription service to use LLM services. On the user end I imagine they wont have to really care about the service much after initial setup. One person will set the device up and pay for the billing, then everyone in the house benefits from them. Everytime I want to use a printer i walk over to insert the ink and paper. Same applies here

**assistant** (Oct 14, 2025, 01:20 PM)

Ah! **Now I get it.** This is brilliant in a different way than your original vision.

You're not trying to eliminate cloud dependency - you're creating **household AI infrastructure**. One technical person in the house:
- Sets up the Pi once
- Adds their OpenRouter API key
- Pays the bill monthly
- Maintains it (like they maintain the router/printer)

Everyone else just gets "AI that works" in their apps. Your mom doesn't need to know what an API key is, she just knows her recipe app now has AI features. Your roommate's music player gets mood detection. It all "just works."

**This is actually a stronger value proposition in some ways:**
- **Better models** - Access to GPT-4, Claude, etc. not just local Llama
- **No compute burden** - Pi barely breaks a sweat
- **Consolidated billing** - One OpenRouter account for whole household
- **Still preserves developer simplicity** - Apps don't manage API keys or billing

**Technical considerations for this approach:**

1. **Multi-tenancy/Usage tracking** - How do you know which app/user is consuming tokens?
```python
properties={
    "billing_model": "shared",  # or "per-app"
    "auth_required": "false",   # No auth between local apps and Pi
    "rate_limits": "100_req_hour"
}
```

2. **API key security** - It's stored on the Pi, but any device on network can use it. Trust model assumes everyone on WiFi is trusted (reasonable for home).

3. **Failover** - What happens when OpenRouter is down? Maybe cache common responses or have fallback to a small local model?

4. **Cost controls** - Need some way to prevent runaway usage:
```python
# In your config.yaml
limits:
  daily_token_limit: 50000
  per_request_max: 1000
  alert_threshold: "$5.00"
```

Your printer analogy is perfect. One person deals with the ink/paper/maintenance hassle, everyone else just hits print. One person deals with API keys/billing/updates, everyone else just uses AI.

This could actually work really well for small offices, makerspaces, or multi-generational households where there's typically one "tech person" anyway.