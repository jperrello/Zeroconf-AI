#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================"
echo "  VLC ZeroConf AI Chat Installer"
echo "======================================"
echo ""

check_vlc() {
    if ! command -v vlc &> /dev/null; then
        echo "✗ VLC not found. Please install VLC first."
        echo "  - macOS: brew install --cask vlc"
        echo "  - Linux: sudo apt install vlc (Debian/Ubuntu) or sudo dnf install vlc (Fedora)"
        exit 1
    fi
    
    VLC_VERSION=$(vlc --version 2>/dev/null | head -n1 | awk '{print $3}')
    echo "✓ Found VLC version: $VLC_VERSION"
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        echo "✗ Python 3 not found. Please install Python 3."
        echo "  - macOS: brew install python3"
        echo "  - Linux: sudo apt install python3 python3-pip"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo "✓ Found Python 3: $PYTHON_VERSION"
}

install_dependencies() {
    echo ""
    echo "Installing Python dependencies..."
    
    REQUIRED_PACKAGES="fastapi uvicorn requests zeroconf pydantic"
    
    if python3 -m pip --version &> /dev/null; then
        python3 -m pip install --user $REQUIRED_PACKAGES
    else
        echo "✗ pip not found. Please install pip first."
        exit 1
    fi
    
    echo "✓ Python dependencies installed"
}

detect_platform() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        VLC_EXTENSIONS_DIR="$HOME/Library/Application Support/org.videolan.vlc/lua/extensions"
        BRIDGE_INSTALL_DIR="$HOME/.vlc"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        VLC_EXTENSIONS_DIR="$HOME/.local/share/vlc/lua/extensions"
        BRIDGE_INSTALL_DIR="$HOME/.vlc"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        VLC_EXTENSIONS_DIR="$APPDATA/vlc/lua/extensions"
        BRIDGE_INSTALL_DIR="$APPDATA/vlc"
    else
        echo "✗ Unsupported operating system: $OSTYPE"
        exit 1
    fi
    
    echo "✓ Detected platform: $OSTYPE"
}

install_extension() {
    echo ""
    echo "Installing VLC extension..."
    
    mkdir -p "$VLC_EXTENSIONS_DIR"
    
    if [ ! -f "$SCRIPT_DIR/zeroconf_ai_chat.lua" ]; then
        echo "✗ zeroconf_ai_chat.lua not found in $SCRIPT_DIR"
        exit 1
    fi
    
    cp "$SCRIPT_DIR/zeroconf_ai_chat.lua" "$VLC_EXTENSIONS_DIR/"
    echo "✓ Extension installed to: $VLC_EXTENSIONS_DIR"
}

install_bridge() {
    echo ""
    echo "Installing discovery bridge..."
    
    mkdir -p "$BRIDGE_INSTALL_DIR"
    
    if [ ! -f "$SCRIPT_DIR/vlc_discovery_bridge.py" ]; then
        echo "✗ vlc_discovery_bridge.py not found in $SCRIPT_DIR"
        exit 1
    fi
    
    cp "$SCRIPT_DIR/vlc_discovery_bridge.py" "$BRIDGE_INSTALL_DIR/"
    chmod +x "$BRIDGE_INSTALL_DIR/vlc_discovery_bridge.py"
    echo "✓ Bridge installed to: $BRIDGE_INSTALL_DIR"
}

create_launcher() {
    echo ""
    echo "Creating launcher script..."
    
    cat > "$BRIDGE_INSTALL_DIR/start_bridge.sh" << 'EOF'
#!/bin/bash

BRIDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$BRIDGE_DIR/bridge.pid"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Bridge already running (PID: $OLD_PID)"
        exit 0
    fi
fi

python3 "$BRIDGE_DIR/vlc_discovery_bridge.py" > "$BRIDGE_DIR/bridge.log" 2>&1 &
echo $! > "$PID_FILE"
echo "Bridge started (PID: $!)"
echo "Logs: $BRIDGE_DIR/bridge.log"
EOF
    
    chmod +x "$BRIDGE_INSTALL_DIR/start_bridge.sh"
    
    cat > "$BRIDGE_INSTALL_DIR/stop_bridge.sh" << 'EOF'
#!/bin/bash

BRIDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$BRIDGE_DIR/bridge.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        kill "$PID"
        echo "Bridge stopped (PID: $PID)"
    else
        echo "Bridge not running"
    fi
    rm "$PID_FILE"
else
    echo "No PID file found"
fi
EOF
    
    chmod +x "$BRIDGE_INSTALL_DIR/stop_bridge.sh"
    
    echo "✓ Launcher scripts created"
}

print_usage() {
    echo ""
    echo "======================================"
    echo "  Installation Complete!"
    echo "======================================"
    echo ""
    echo "To use the extension:"
    echo ""
    echo "1. Start the discovery bridge:"
    echo "   $BRIDGE_INSTALL_DIR/start_bridge.sh"
    echo ""
    echo "   Or manually:"
    echo "   python3 $BRIDGE_INSTALL_DIR/vlc_discovery_bridge.py"
    echo ""
    echo "2. Open VLC and play any media"
    echo ""
    echo "3. Go to: View → Extensions → ZeroConf AI Chat"
    echo ""
    echo "4. The extension will discover AI services on your network"
    echo ""
    echo "Additional commands:"
    echo "  Stop bridge:  $BRIDGE_INSTALL_DIR/stop_bridge.sh"
    echo "  View logs:    $BRIDGE_INSTALL_DIR/bridge.log"
    echo ""
    echo "Make sure you have ZeroConf AI services running!"
    echo ""
}

main() {
    check_vlc
    check_python
    install_dependencies
    detect_platform
    install_extension
    install_bridge
    create_launcher
    print_usage
}

main