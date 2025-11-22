# VLC Saturn Extensions - Build Instructions

## Overview

These VLC extensions integrate Saturn's mDNS service discovery into VLC media player. The extensions use PyInstaller to bundle the discovery bridge into a standalone executable, enabling true "zero configuration" deployment - users no longer need Python installed.

The bridge automatically discovers Saturn AI services on your local network using the same `dns-sd` mDNS discovery mechanism as all other Saturn components.

### Available Extensions

**Saturn Chat** (`saturn_chat.lua`)
- Interactive AI chat interface within VLC
- Provides media-aware conversations by passing VLC playback context to AI
- Allows asking questions about what you're watching/listening to
- Full service and model selection capabilities

**Saturn Roast** (`saturn_roast.lua`)
- Entertainment extension that roasts your media taste
- Analyzes currently playing media (title, artist, album, genre)
- Generates witty, sarcastic commentary about your media choices
- Lighthearted and fun AI-powered roasting experience

Both extensions share the same discovery bridge and architecture, providing seamless access to all Saturn AI services on your network.

## Architecture

```
vlc_extension/
├── saturn_chat.lua                # VLC chat extension (UI and logic)
├── saturn_roast.lua               # VLC roast extension (UI and logic)
├── vlc_discovery_bridge.py        # Python bridge (source code)
├── vlc_discovery_bridge.spec      # PyInstaller spec file
├── requirements.txt               # Python dependencies
└── bridge/                        # Bundled executables
    ├── vlc_discovery_bridge       # Linux/macOS executable
    └── vlc_discovery_bridge.exe   # Windows executable
```

## How It Works

1. User installs the VLC extensions (copies directory to VLC extensions folder)
2. User activates an extension in VLC:
   - **Saturn Chat**: View → Extensions → Saturn Chat
   - **Saturn Roast**: View → Extensions → Saturn Roast Extension
3. Lua extension automatically:
   - Detects the operating system
   - Locates the bundled bridge executable
   - Launches the bridge with `--port-file` argument
   - Reads the port file to discover where the bridge is running
   - Connects to the bridge via HTTP
4. Bridge discovers Saturn services:
   - Uses `dns-sd` commands to browse for `_saturn._tcp.local` services
   - Same discovery pattern as `simple_chat_client.py` and other Saturn components
   - Monitors service health and available models
   - Routes requests to best service based on priority (lowest = highest priority)
5. When extension deactivates:
   - Sends `/shutdown` request to bridge
   - Bridge exits cleanly

## Building the Executable

### Prerequisites

- Python 3.11+
- pip

### Build Steps

1. **Install dependencies:**
   ```bash
   cd vlc_extension
   pip install -r requirements.txt
   ```

2. **Build the executable:**
   ```bash
   python -m PyInstaller vlc_discovery_bridge.spec --clean
   ```

3. **Move the executable to the bridge directory:**
   ```bash
   mv dist/vlc_discovery_bridge bridge/
   ```

   On Windows:
   ```cmd
   move dist\vlc_discovery_bridge.exe bridge\
   ```

### Platform-Specific Builds

PyInstaller creates platform-specific executables. To support all platforms:

- **Linux**: Build on Linux (creates ELF binary)
- **macOS**: Build on macOS (creates Mach-O binary)
- **Windows**: Build on Windows (creates .exe)

## Key Architecture Details

### Python Bridge (vlc_discovery_bridge.py)

The bridge is a Saturn CLIENT that discovers and routes to Saturn services:

1. **DNS-SD Service Discovery** (v2.0):
   - Uses `dns-sd` subprocess commands (same pattern as `simple_chat_client.py`)
   - Removed dependency on `python-zeroconf` library for consistency across Saturn
   - Discovers services by running `dns-sd -B _saturn._tcp local`
   - Gets service details with `dns-sd -L <service_name> _saturn._tcp local`
   - Parses hostname, port, and priority from dns-sd output
   - Continuous background discovery with configurable interval (default: 10s)

2. **Service Health Monitoring**:
   - Continuously checks `/v1/health` on discovered services
   - Fetches available models from `/v1/models`
   - Only routes requests to healthy services
   - Automatic failover when services become unavailable

3. **Priority-Based Routing**:
   - Routes requests to service with lowest priority number (highest preference)
   - Same priority system as Saturn servers (1-20 = local, 21-100 = standard, 101+ = fallback)
   - Users can optionally specify a specific service by name

4. **Endpoints**:
   - `/shutdown` - Allows Lua to cleanly terminate the bridge
   - `/v1/health` - Health check endpoint
   - `/v1/models` - Aggregates models from all healthy services
   - `/v1/chat/completions` - Routes chat requests to best available service
   - `/services` - Lists all discovered services with health status
   - Both GET and POST supported for chat (VLC Lua compatibility)

5. **Port File System**:
   - Accepts `--port-file` argument for Lua discovery
   - Writes `host:port` to file only after server is ready
   - Auto-cleanup on exit

### Lua Extensions (saturn_chat.lua & saturn_roast.lua)

Both extensions share common functionality:

1. **OS Detection**: Automatically detects Windows, macOS, or Linux
2. **Bridge Launcher**: Launches the appropriate executable using `os.execute()`
3. **Port Discovery**: Reads the port file to find where the bridge is running
4. **Dynamic URL**: Bridge URL is no longer hardcoded - discovered at runtime
5. **Service Selection**: Displays all discovered Saturn services with model counts
6. **Automatic Routing**: "Auto" mode selects best service by priority
7. **Media Context**: Extracts VLC playback context (title, artist, album, genre, timestamp)
8. **Graceful Shutdown**: Sends shutdown signal to bridge on deactivation

**Saturn Chat** specific features:
- Interactive chat interface with conversation history
- Media-aware AI that can answer questions about current playback
- Full conversation management and context passing

**Saturn Roast** specific features:
- Entertainment-focused roasting functionality
- Custom system prompt for witty, sarcastic AI personality
- Styled HTML output with purple/red "verdict" theming
- Short-form responses (2-3 sentences) optimized for quick laughs

## Testing the Integration

### Testing with Saturn Servers

Before testing the VLC extension, you need running Saturn services to discover:

1. **Start a Saturn server** (e.g., OpenRouter):
   ```bash
   # Ensure you have OPENROUTER_API_KEY and OPENROUTER_BASE_URL in .env
   cd servers/
   python openrouter_server.py
   ```

   You should see:
   ```
   OpenRouter has been registered via dns-sd with priority 50.
   ```

2. **Verify service registration** (optional):
   ```bash
   # In another terminal
   dns-sd -B _saturn._tcp local
   ```

   You should see your OpenRouter service appear.

### Manual Bridge Test

1. Build the executable (see above)
2. Test the executable directly:
   ```bash
   # Windows
   .\bridge\vlc_discovery_bridge.exe --port-file test_port.txt

   # Linux/macOS
   ./bridge/vlc_discovery_bridge --port-file /tmp/test_port.txt
   ```

3. You should see:
   ```
   [INFO] Starting Saturn discovery bridge...
   [INFO] Discovery bridge started - listening for Saturn services via mDNS
   [INFO] Discovered: OpenRouter at http://192.168.1.10:8080 (priority=50)
   [INFO] OpenRouter is now healthy
   ```

4. Verify the port file was created:
   ```bash
   # Windows
   type test_port.txt

   # Linux/macOS
   cat /tmp/test_port.txt
   # Should output: 127.0.0.1:9876
   ```

5. Test the endpoints:
   ```bash
   # Check health
   curl http://127.0.0.1:9876/v1/health

   # List discovered services
   curl http://127.0.0.1:9876/services

   # List available models
   curl http://127.0.0.1:9876/v1/models

   # Shutdown
   curl -X POST http://127.0.0.1:9876/shutdown
   ```

### VLC Extension Test

1. Copy the entire `vlc_extension/` directory to your VLC extensions directory:
   - **Linux**: `~/.local/share/vlc/lua/extensions/`
   - **macOS**: `~/Library/Application Support/org.videolan.vlc/lua/extensions/`
   - **Windows**: `%APPDATA%\vlc\lua\extensions\`

2. Restart VLC

3. Activate an extension:
   - **Saturn Chat**: View → Extensions → Saturn Chat
   - **Saturn Roast**: View → Extensions → Saturn Roast Extension

4. Check VLC logs (Tools → Messages) for:
   ```
   [Saturn] OS detected: linux (or [Saturn Roast] for the roast extension)
   [Saturn] Extension dir: /path/to/extensions/vlc_extension/
   [Saturn] Launching bridge: /path/to/bridge/vlc_discovery_bridge
   [Saturn] Bridge running at: http://127.0.0.1:9876
   ```

**Note**: Both extensions can share the same bridge instance if launched from the same VLC session. The first extension to activate will launch the bridge, and the second will connect to it.

## Version History

### v2.1 - Saturn Roast Extension
**Changes:**
- Added new entertainment extension: `saturn_roast.lua`
- Roast extension provides witty AI commentary on user's media choices
- Shares same bridge architecture and service discovery as Saturn Chat
- Custom system prompt for comedic AI personality
- Styled purple/red HTML output for roast display
- Optimized for short-form responses (2-3 sentences)

**Features:**
- Analyzes currently playing media (title, artist, album, genre)
- Interactive roasting experience with service/model selection
- Same retry logic and connection handling as Saturn Chat
- Supports all Saturn AI services discovered via mDNS

### v2.0 - Saturn Integration
**Changes:**
- **Migrated to dns-sd subprocess discovery** for consistency with Saturn infrastructure
- Removed `python-zeroconf` library dependency
- Bridge now uses same discovery pattern as `simple_chat_client.py`
- Consistent priority-based routing across all Saturn components
- Better logging and service health monitoring
- Updated requirements.txt (removed zeroconf)

**Benefits:**
- Single discovery mechanism across entire Saturn ecosystem
- No proprietary Python libraries - uses native dns-sd commands
- Works with existing Saturn servers (openrouter_server.py, ollama_server.py)
- Easier to debug (can manually test with `dns-sd` commands)
- Smaller executable size

### v1.5.1 - Race Condition Fixes

### Fixed Race Condition & Windows Launch Issues

**Problem:** The VLC extension was experiencing HTTP connection failures with errors like:
```
access error: HTTP connection failure
main error: connection failed: Connection refused by peer
http error: cannot connect to 127.0.0.1:9876
```

**Root Causes:**
1. **Windows Launch Bug**: Used `io.popen()` instead of `os.execute()` with `start /B`, causing the bridge to fail to background properly on Windows
2. **Race Condition**: Lua was connecting to the bridge immediately after the port file appeared, before the server was fully ready to accept connections

**Fixes Applied:**
1. **Lua Extension (`saturn_chat.lua`)**:
   - Changed from `io.popen()` to `os.execute()` with `start /B` on Windows for proper backgrounding
   - Increased port file wait timeout from 5s to 10s
   - Added 500ms safety delay AFTER port file appears before attempting connection
   - Improved retry logic with 7 attempts and exponential backoff (0.1s to 2.5s)
   - Added detailed logging for troubleshooting

2. **Bridge Server (`vlc_discovery_bridge.py`)**:
   - Improved `wait_for_server_ready()` with better error handling and logging
   - Increased readiness check timeout from 10s to 15s
   - Added extra 200ms safety margin after server responds as ready
   - Enhanced error messages for debugging
   - Added verification that server can actually handle requests before writing port file

**How It Works Now:**
1. Lua launches bridge with `os.execute()` (proper backgrounding)
2. Bridge starts FastAPI server in background thread
3. Bridge polls `/v1/health` endpoint until server responds HTTP 200
4. Bridge adds 200ms safety margin for network stack initialization
5. Bridge writes port file (ONLY when server is confirmed ready)
6. Lua detects port file and parses the address
7. Lua waits additional 500ms safety margin
8. Lua attempts connection with 7 retries and exponential backoff
9. Connection succeeds!

## Troubleshooting

### Bridge executable not found

The extension looks for the executable at:
- Linux/macOS: `<extension_dir>/bridge/vlc_discovery_bridge`
- Windows: `<extension_dir>\bridge\vlc_discovery_bridge.exe`

Ensure the `bridge/` directory exists and contains the executable with the correct name.

### Bridge fails to start

Check VLC logs (Tools → Messages, set verbosity to 2-Debug) for detailed error messages.

Common issues:
- **Executable doesn't have execute permissions** (Linux/macOS): `chmod +x bridge/vlc_discovery_bridge`
- **Missing system dependencies** (Linux): Install glibc, libssl, etc.
- **Port already in use**: Close other applications using port 9876 or let the bridge auto-detect an available port
- **Firewall blocking**: Allow the bridge executable through your firewall
- **Antivirus interference**: Some antivirus software may block PyInstaller executables

### Port file timeout

If Lua times out waiting for the port file (now 10 seconds):
- The bridge may be crashing on startup - run it manually to see error messages:
  ```bash
  # Windows
  cd %APPDATA%\vlc\lua\extensions\vlc_extension\bridge\
  vlc_discovery_bridge.exe --port-file test.txt

  # Linux/macOS
  cd ~/.local/share/vlc/lua/extensions/vlc_extension/bridge/
  ./vlc_discovery_bridge --port-file test.txt
  ```
- Check if port 9876 is already in use: `netstat -ano | findstr 9876` (Windows) or `lsof -i :9876` (Linux/macOS)
- Verify the bridge executable has correct permissions

### Connection refused errors

If you see "Connection refused by peer" errors:
- The bridge may have started but crashed immediately - check VLC logs for crash details
- Firewall may be blocking localhost connections (unusual but possible)
- Try running the bridge manually (see above) to verify it starts correctly
- Ensure no other service is running on port 9876

### Debugging Tips

Enable detailed logging in VLC:
1. Tools → Messages
2. Set verbosity to "2 - Debug"
3. Look for `[Saturn]` messages
4. You should see a sequence like:
   ```
   [Saturn] Extension activated
   [Saturn] OS detected: windows
   [Saturn] Launching bridge: C:\...\bridge\vlc_discovery_bridge.exe
   [Saturn] Bridge process launched
   [Saturn] Port file found: http://127.0.0.1:9876
   [Saturn] Waiting for server to fully initialize...
   [Saturn] Bridge should be ready
   [Saturn] Health check attempt 1/7
   [Saturn] Bridge connection successful!
   ```

If the sequence breaks, the last message will tell you where the failure occurred.

## Benefits of This Approach

1. **Zero Configuration**: No Python installation required
2. **Single Installation**: One directory contains everything
3. **Platform Independent**: Same code works on all platforms (with platform-specific builds)
4. **No External Dependencies**: All Python packages bundled in the executable
5. **Clean Integration**: Lua has full control over bridge lifecycle

## Future Enhancements

- Add pre-built executables for all platforms to the repository
- Create an installer script that downloads the appropriate executable
- Add auto-update mechanism for the bridge
- Support for multiple concurrent VLC instances (unique port files)
