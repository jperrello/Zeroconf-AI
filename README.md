# ZeroConf AI

*Are you tired of managing API keys for every single app that wants to use AI?*

*Does your open-source project need AI features but you don't want to become a SaaS company?*

*Have you ever thought "Why can't AI just work like printers do?"*

## Meet Sarah, Open Source Developer

Sarah maintains a photo organization app. Users keep asking for AI features - auto-tagging, smart search, caption generation. 

Her options suck:
- Option 1: Make every user get their own API keys (*47-step setup guide, anyone?*)
- Option 2: Pay for everyone's AI usage (*goodbye, rent money*)
- Option 3: Just... don't add AI features (*sad trombone*)

**But what if there was another way?**

## Now Meet Derek, The Home IT Wizard

Derek already pays for OpenRouter/Claude/OpenAI. He uses it for work, for fun, for arguing with strangers on the internet about Star Trek.

He thinks: "I'm already paying for this. Why can't my family's apps just... use it?"

So Derek runs our script on a Raspberry Pi. Now every app on his home network can discover and use AI. No API keys. No configuration. It just works.

## What Exists Right Now

This repository contains a working ZeroConf AI implementation that:

1. **Broadcasts an AI service** on your local network using mDNS
2. **Proxies requests** to OpenRouter (which gives you access to GPT-4, Claude, etc.)
3. **Requires zero configuration** on client devices - they just discover it automatically

## What's In This Repo

### The Server (`server.py`)
- FastAPI server that proxies OpenAI-compatible chat requests to OpenRouter
- mDNS broadcasting so clients can auto-discover it
- Automatic port selection (or specify your own)
- Health check endpoint for monitoring

### The Client (`client.py`)
- ServiceManager that discovers all AI services on your network
- ZeroconfAIClient that maintains connections and handles failover
- Automatic health monitoring (removes dead services)
- Chat history management
- Multi-provider support 

## Quick Start

### Server Setup

1. **Set up your environment:**
```bash
# Clone the repo
git clone https://github.com/jperrello/Zeroconf-AI.git
cd zeroconf-ai

# Install dependencies
pip install fastapi uvicorn zeroconf python-dotenv requests

# Create .env file
echo "OPENROUTER_API_KEY=your-key-here" > .env
echo "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1/chat/completions" >> .env
```

2. **Run the server:**
```bash
python server.py
# Server starts on port 8080 (or finds an available port)
# Now broadcasting as "_zeroconfai._tcp.local."
```

That's it. Any device on your network can now discover and use AI.

### Client Usage

```python
from client import ServiceManager, ZeroconfAIClient

# Discover services automatically
manager = ServiceManager()
# Wait a moment for discovery...

# Connect to first available service
for url, name in manager.items():
    client = ZeroconfAIClient(manager, url)
    break

# Use it!
response = client.chat("Hello, AI!")
print(response)
```

## What This Actually Does

When you run the server:
- It starts broadcasting "Hey, I'm an AI service!" on your local network
- Any app using the client library automatically finds it
- Apps can send chat requests without knowing the server's IP or having API keys
- The server proxies requests to OpenRouter using YOUR api key
- Responses come back to the app

**It's literally like a printer.** Apps don't need printer API keys. They just discover printers and print. Same thing here, but for AI.


## Current Limitations that I plan on improvinf 

- **OpenRouter Only** - Currently just proxies to OpenRouter (OpenAI-compatible endpoints coming soon)
- **Python Only** - Client library only in Python (JS, Go, Rust)
- **No Authentication** - Anyone on your network can use it 
- **No Usage Tracking** - Can't see who's using how much (dashboard coming soon)

## Technical Details

**mDNS Service Type**: `_zeroconfai._tcp.local.`

**API Endpoint**: `/v1/chat/completions` (OpenAI-compatible)

**Request Format**:
```json
{
  "model": "claude-3-sonnet",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ]
}
```

## 🤔 FAQ

**"Is this secure?"**
It's as secure as your home network. If you trust devices on your WiFi, you can trust this.

**"What about costs?"**
You pay for your own OpenRouter usage. But now your whole network can share one account instead of everyone needing their own.

**"Can I run multiple servers?"**
Yes! The client automatically picks the best available one based on priority settings.

**"What if the internet goes down?"**
Then the proxy can't reach OpenRouter. Local model support (Ollama) is on the roadmap.


---

**Not available in stores!** *(Available on GitHub)*

---

Built with ❤️ and mild frustration..

Special interest in:
- Client libraries for more languages
- UI for non-technical admins
- Cost tracking dashboards
- Model routing strategies
