# VLC Saturn Extension - Build Instructions

## Overview

This VLC extension has been upgraded to use PyInstaller to bundle the discovery bridge into a standalone executable. This enables true "zero configuration" deployment - users no longer need Python installed.

## Architecture

```
vlc_extension/
├── saturn_chat.lua          # VLC extension (UI and logic)
├── vlc_discovery_bridge.py       # Python bridge (source code)
├── vlc_discovery_bridge.spec     # PyInstaller spec file
├── requirements.txt              # Python dependencies
└── bridge/                       # Bundled executables
    ├── vlc_discovery_bridge      # Linux/macOS executable
    └── vlc_discovery_bridge.exe  # Windows executable
```

## How It Works

1. User installs the VLC extension (copies directory to VLC extensions folder)
2. User activates extension in VLC (View → Extensions → Saturn Chat)
3. Lua extension automatically:
   - Detects the operating system
   - Locates the bundled bridge executable
   - Launches the bridge with `--port-file` argument
   - Reads the port file to discover where the bridge is running
   - Connects to the bridge via HTTP
4. When extension deactivates:
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

## Key Changes from Previous Version

### Python Bridge (vlc_discovery_bridge.py)

1. **Added `/shutdown` endpoint**: Allows Lua to cleanly terminate the bridge
   ```python
   @app.post("/shutdown")
   async def shutdown():
       logger.info("Shutdown requested")
       # Schedule shutdown after returning response
       def stop_server():
           time.sleep(0.5)
           os._exit(0)
       threading.Thread(target=stop_server, daemon=True).start()
       return {"status": "shutting_down"}
   ```

2. **Added `--port-file` argument**: Writes host:port to a file for Lua discovery
   ```bash
   ./bridge/vlc_discovery_bridge --port-file /tmp/vlc_bridge_port.txt
   ```

   The bridge creates the file containing:
   ```
   127.0.0.1:9876
   ```

3. **Auto-cleanup**: Port file is automatically deleted when the bridge exits

### Lua Extension (saturn_chat.lua)

1. **OS Detection**: Automatically detects Windows, macOS, or Linux
2. **Bridge Launcher**: Launches the appropriate executable using `io.popen()`
3. **Port Discovery**: Reads the port file to find where the bridge is running
4. **Dynamic URL**: Bridge URL is no longer hardcoded - discovered at runtime
5. **Graceful Shutdown**: Sends shutdown signal to bridge on deactivation

## Testing the Integration

### Manual Test

1. Build the executable (see above)
2. Test the executable directly:
   ```bash
   ./bridge/vlc_discovery_bridge --port-file /tmp/test_port.txt
   ```
3. Verify the port file was created:
   ```bash
   cat /tmp/test_port.txt
   # Should output: 127.0.0.1:9876
   ```
4. Test the endpoints:
   ```bash
   curl http://127.0.0.1:9876/v1/health
   curl -X POST http://127.0.0.1:9876/shutdown
   ```

### VLC Extension Test

1. Copy the entire `vlc_extension/` directory to your VLC extensions directory:
   - **Linux**: `~/.local/share/vlc/lua/extensions/`
   - **macOS**: `~/Library/Application Support/org.videolan.vlc/lua/extensions/`
   - **Windows**: `%APPDATA%\vlc\lua\extensions\`

2. Restart VLC

3. Activate the extension: View → Extensions → Saturn Chat

4. Check VLC logs (Tools → Messages) for:
   ```
   [Saturn] OS detected: linux
   [Saturn] Extension dir: /path/to/extensions/vlc_extension/
   [Saturn] Launching bridge: /path/to/bridge/vlc_discovery_bridge
   [Saturn] Bridge running at: http://127.0.0.1:9876
   ```

## Recent Fixes (v1.5.1)

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
