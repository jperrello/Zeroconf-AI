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

Derek already pays for OpenRouter/Claude/OpenAI. He uses it for work, for fun, for randomly inserting references to _Hollow Knight_ into his code.

He thinks: "I'm already paying for this. Why can't my family's apps just... use it?"

So Derek runs our script on a Raspberry Pi. Now every app on his home network can discover and use AI. No API keys. No configuration. It just works.

**But wait, there's more!** Derek's tech-savvy neighbor also runs Ollama locally. Derek's apps automatically discover BOTH services and pick the best one. If OpenRouter goes down? Seamless failover to local Ollama. It's like RAID, but for AI.

## What Exists Right Now

This repository contains a working ZeroConf AI implementation that:

1. **Broadcasts AI services** on your local network using mDNS
2. **Proxies requests** to multiple providers (OpenRouter, Ollama, Gemini)
3. **Requires zero configuration** on client devices - they just discover it automatically
4. **Handles failover** - if one service dies, clients automatically switch to another
5. **Priority-based routing** - prefer local models over cloud, or vice versa

## What's In This Repo

### The Servers

**Gemini Server (`gemini_server.py`)**
- FastAPI server that proxies to Google's Gemini models via OpenRouter
- Supports Gemini 2.0 Flash, 2.5 Flash, 2.5 Pro, and image preview models
- Full streaming support for real-time responses
- Automatic priority negotiation (defaults to priority 50)

**Ollama Server (`ollama_server.py`)**
- Proxies to your local Ollama installation
- Automatically discovers whatever models you have installed
- Zero external API costs - it's all running on your hardware
- Perfect for offline work or privacy-sensitive tasks
- Converts Ollama's native format to OpenAI-compatible responses

**Fallback Server (`fallback_server.py`)**
- The world's most honest server
- Model literally named "dont_pick_me"
- If you actually pick it, it roasts you
- Great for testing client failover logic
- Contains the condensed wisdom of ignoring clear warnings

### The Clients

**Simple Chat Client (`simple_chat_client.py`)**
- Bare-bones example of service discovery
- Automatically finds the highest-priority service
- Basic chat loop with history
- Under 100 lines - read it to understand the protocol

**Local Proxy Client (`local_proxy_client.py`)**
- Full-featured client with health monitoring
- Discovers ALL services on your network
- Automatic failover if a service goes down
- Priority-based selection (use local before cloud, or configure your own preferences)
- Maintains chat history across provider switches

## Quick Start

### Server Setup

1. **Set up your environment:**
```bash
git clone https://github.com/jperrello/Zeroconf-AI.git
cd zeroconf-ai

pip install fastapi uvicorn zeroconf python-dotenv requests pydantic
```

2. **For Gemini Server:**
```bash
echo "OPENROUTER_API_KEY=your-key-here" > .env
echo "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1/chat/completions" >> .env

python gemini_server.py
python gemini_server.py --priority 10
python gemini_server.py --port 8081 --priority 5
```

3. **For Ollama Server (requires Ollama running locally):**
```bash
python ollama_server.py
python ollama_server.py --priority 100
```

4. **For Fallback Server (for testing or amusement):**
```bash
python fallback_server.py --priority 999
```

### Priority System

Lower numbers = higher priority. Clients pick the lowest-priority service available.

Example setup:
- Local Ollama: priority 10 (use this first - it's free and private)
- Gemini via OpenRouter: priority 50 (use if Ollama is down)
- Fallback server: priority 999 (only if you're truly desperate)

Priorities are auto-negotiated. If you try to start two services with the same priority, the second one automatically increments until it finds an available slot. No conflicts, no drama.

### Client Usage

**Simple client:**
```python
python simple_chat_client.py
```

**Advanced client:**
```python
from local_proxy_client import ServiceManager, ZeroconfAIClient

manager = ServiceManager()
time.sleep(2)

for url, name in manager.items():
    client = ZeroconfAIClient(manager, url)
    break

response = client.chat("What's the meaning of life?")
print(response)
```

## What This Actually Does

When you run servers:
- Each broadcasts "Hey, I'm an AI service!" with its priority
- Clients automatically discover ALL services
- Clients pick the best one based on priority
- If a service goes down, clients seamlessly switch to the next-best option

**Example network:**
- Derek's Raspberry Pi: Running Gemini server (priority 50)
- Derek's gaming PC: Running Ollama server (priority 10)
- Derek's definitely-not-overkill homelab: Running fallback server (priority 999)

All of Derek's family's apps automatically use the gaming PC first (priority 10), fall back to the Raspberry Pi if it's busy (priority 50), and... well, hopefully never hit the fallback server (priority 999).

## Architecture

**mDNS Service Type**: `_zeroconfai._tcp.local.`

**API Endpoints**:
- `/v1/health` - Check if service is alive
- `/v1/models` - List available models
- `/v1/chat/completions` - OpenAI-compatible chat endpoint

**Request Format**:
```json
{
  "model": "model-name",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "stream": true
}
```

All servers speak OpenAI-compatible API. Whether you're hitting Gemini, Ollama, or even the sarcastic fallback server, the request/response format is identical. This means your client code works with ANY ZeroConf AI server without modification.


## FAQ

**"Wait, I can mix cloud and local AI?"**
Yes! Run Ollama locally for free/private stuff, plus a cloud proxy for heavy lifting. Clients pick the best one automatically.

**"What if multiple people try to use my Ollama at once?"**
Set Ollama to lower priority (higher number). Clients will prefer your cloud services when local is busy.

**"Is this secure?"**
It's as secure as your home network. If you trust devices on your WiFi, you can trust this. Want more security? Run it on a separate VLAN or add authentication (PRs welcome).

**"What about costs?"**
Ollama server: Free (uses your hardware)
Gemini server: You pay for your own OpenRouter usage
Your whole network shares one account instead of everyone getting their own.

**"Can I run ALL the servers?"**
Absolutely! Run one of each, give them different priorities, and let clients pick the best one. That's the whole point.

**"Why does the fallback server exist?"**
Mostly for laughs. Also great for testing client failover logic. Try it, you'll see.

**"What happens when Ollama is generating and someone else makes a request?"**
Depends on your Ollama configuration, but typically it'll queue. Or just run another server at higher priority as overflow.

---

**Not available in stores!** *(Available on GitHub)*

**But wait, there's more!** *(There isn't. This is it.)*

---

Built with ❤️ and mild frustration.
