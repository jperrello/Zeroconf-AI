# VLC ZeroConf AI Chat Extension

**Chat with AI about your media - with zero configuration**

This VLC extension automatically discovers AI services on your network and provides an intelligent chat interface for your media. Ask questions about what you're watching, get summaries, or have contextual discussions about your content.

## ✨ The Magic of Zero Configuration

The core innovation of this project is **true zero-configuration AI integration**. The extension:
- Automatically discovers all AI services on your network via mDNS/ZeroConf
- Requires no API keys, URLs, or manual configuration
- Intelligently routes to the best available service
- Falls back gracefully when services appear/disappear

## 🎯 Features

- **Automatic Discovery**: Finds Ollama, OpenRouter, and other ZeroConf AI services
- **Media Context Awareness**: AI knows what you're watching/listening to
- **Service Selection**: Choose specific AI services or use automatic routing
- **Streaming Responses**: Real-time AI responses (where supported)
- **Priority-Based Routing**: Automatically uses the best available service
- **Health Monitoring**: Continuously checks service availability

## 🏗️ Architecture

```
[VLC Media Player]
        ↓
[Lua Extension (UI)]
        ↓ HTTP
[Discovery Bridge (Python)]
        ↓ mDNS
[ZeroConf AI Services]
```

### Components

1. **VLC Lua Extension** (`zeroconf_ai_chat.lua`)
   - Provides the chat UI within VLC
   - Extracts media metadata
   - Communicates with the discovery bridge

2. **Discovery Bridge** (`vlc_discovery_bridge.py`)
   - Runs on localhost:9876
   - Discovers AI services via mDNS
   - Routes requests to appropriate services
   - Handles streaming responses

3. **AI Services** (Ollama, OpenRouter, etc.)
   - Must advertise via `_zeroconfai._tcp` service type
   - OpenAI-compatible API (`/v1/chat/completions`)

## 📦 Installation

### Quick Install (Linux/macOS)

```bash
chmod +x install.sh
./install.sh
```

### Manual Installation

1. **Install Dependencies**
```bash
pip3 install fastapi uvicorn requests zeroconf pydantic
```

2. **Copy Extension to VLC**
- Linux: `~/.local/share/vlc/lua/extensions/`
- macOS: `~/Library/Application Support/org.videolan.vlc/lua/extensions/`
- Windows: `%APPDATA%\vlc\lua\extensions\`

3. **Install Discovery Bridge**
```bash
cp vlc_discovery_bridge.py ~/.vlc/
chmod +x ~/.vlc/vlc_discovery_bridge.py
```

## 🚀 Usage

1. **Start the Discovery Bridge** (optional - extension tries auto-start)
```bash
python3 ~/.vlc/vlc_discovery_bridge.py
```

2. **Open VLC and play media**

3. **Activate the extension**
   - View → Extensions → ZeroConf AI Chat

4. **Chat with AI about your media!**

## 💬 Example Questions

- "What's this movie about?"
- "Who's the actor playing the main character?"
- "Explain what just happened in that scene"
- "What genre is this music?"
- "Give me some similar recommendations"

## 🔧 Technical Details

### Service Discovery Protocol

Services must advertise with:
- Service type: `_zeroconfai._tcp`
- Priority: Lower number = higher priority (default: 50)
- Port: HTTP server port
- Required endpoints:
  - `GET /v1/health` - Health check
  - `GET /v1/models` - List available models
  - `POST /v1/chat/completions` - OpenAI-compatible chat

### Media Context

The extension provides AI with:
- Title, artist, album
- Current playback position
- Total duration
- File/stream information

### Routing Algorithm

1. Discovers all services via mDNS
2. Health checks every 10 seconds
3. Routes to lowest priority number (highest priority)
4. Falls back to next service on failure
5. Automatic retry with exponential backoff

## 🐛 Troubleshooting

### Bridge won't start
- Check Python dependencies: `pip3 list | grep -E "fastapi|uvicorn|zeroconf"`
- Verify port 9876 is free: `lsof -i:9876`
- Check firewall allows local connections

### No services discovered
- Verify AI services are running: `avahi-browse -a | grep zeroconfai`
- Check mDNS is enabled on your network
- Ensure services advertise correct service type

### Extension not appearing in VLC
- Verify installation directory
- Restart VLC after installation
- Check VLC messages: Tools → Messages (set to debug)

## 📝 Development

### Running in Development

```bash
python3 vlc_discovery_bridge.py

vlc --verbose=2 --lua-intf=luaintf --lua-config "luaintf={intf='dummy'}"
```

### Testing Service Discovery

```python
from zeroconf import ServiceBrowser, Zeroconf

zc = Zeroconf()
browser = ServiceBrowser(zc, "_zeroconfai._tcp.local.", handlers=[])
```

## 🎓 Project Context

This is a master's project demonstrating the power and simplicity of zero-configuration networking for AI services. The goal is to showcase how modern AI can be seamlessly integrated into existing applications without complex setup or configuration.

### Key Innovations

1. **True Zero Config**: No API keys, no URLs, no configuration files
2. **Automatic Failover**: Seamlessly handles service availability changes
3. **Context Awareness**: AI understands your media without manual input
4. **Universal Compatibility**: Works with any OpenAI-compatible service


## 🙏 Acknowledgments

- Built on the ZeroConf AI specification
- Inspired by the simplicity of mDNS/Bonjour
- VLC's powerful Lua extension system

## 📧 Contact

Joey Perrello - jperrell@ucsc.edu
https://jperrello.netlify.app/

---

*"The best interface is no interface" - This extension embodies that philosophy by making AI assistance truly effortless.*
