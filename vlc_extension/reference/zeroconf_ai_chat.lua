function descriptor()
    return {
        title = "ZeroConf AI Chat",
        version = "2.0",
        author = "Joey Perrello",
        url = "https://github.com/yourrepo/zeroconfai",
        shortdesc = "AI chat with automatic service discovery",
        description = "Chat with AI about your media using automatic ZeroConf service discovery - truly zero configuration!",
        capabilities = {"input-listener", "meta-listener"}
    }
end

BRIDGE_PYTHON_CODE = [=[
import socket
import threading
import time
import argparse
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import requests
from zeroconf import ServiceListener, ServiceBrowser, Zeroconf
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class AIService:
    name: str
    address: str
    port: int
    priority: int
    last_seen: datetime = field(default_factory=datetime.now)
    is_healthy: bool = False
    available_models: List[str] = field(default_factory=list)
    first_check_complete: bool = False
    
    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "priority": self.priority,
            "is_healthy": self.is_healthy,
            "models": self.available_models,
            "last_seen": self.last_seen.isoformat()
        }

class ServiceDiscovery:
    def __init__(self):
        self.services: Dict[str, AIService] = {}
        self.lock = threading.Lock()
        self.zc = Zeroconf()
        self.listener = self._create_listener()
        self.browser = ServiceBrowser(self.zc, "_zeroconfai._tcp.local.", self.listener)
    
    def _create_listener(self) -> ServiceListener:
        discovery = self
        
        class Listener(ServiceListener):
            def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                info = zc.get_service_info(type_, name)
                if info and info.port:
                    address = socket.inet_ntoa(info.addresses[0])
                    port = info.port
                    priority = info.priority if info.priority else 50
                    
                    with discovery.lock:
                        discovery.services[name] = AIService(
                            name=name,
                            address=address,
                            port=port,
                            priority=priority
                        )
                    logger.info(f"Discovered: {name} at {address}:{port}")
            
            def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                self.add_service(zc, type_, name)
            
            def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                with discovery.lock:
                    if name in discovery.services:
                        del discovery.services[name]
                        logger.info(f"Removed: {name}")
        
        return Listener()
    
    def get_all_services(self) -> List[AIService]:
        with self.lock:
            return list(self.services.values())
    
    def get_service(self, name: str) -> Optional[AIService]:
        with self.lock:
            return self.services.get(name)
    
    def get_service_by_partial_name(self, partial_name: str) -> Optional[AIService]:
        with self.lock:
            partial_lower = partial_name.lower()
            for name, service in self.services.items():
                if partial_lower in name.lower():
                    return service
            return None
    
    def stop(self):
        self.browser.cancel()
        self.zc.close()

class HealthMonitor:
    def __init__(self, discovery: ServiceDiscovery, check_interval: int = 10):
        self.discovery = discovery
        self.check_interval = check_interval
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def _monitor_loop(self):
        while self.running:
            services = self.discovery.get_all_services()
            
            for service in services:
                was_healthy = service.is_healthy
                service.is_healthy = self._check_health(service.url)
                service.last_seen = datetime.now()
                
                if service.is_healthy:
                    service.available_models = self._fetch_models(service.url)
                
                if service.first_check_complete and service.is_healthy != was_healthy:
                    status = "healthy" if service.is_healthy else "unhealthy"
                    logger.info(f"{service.name} is now {status}")
                
                service.first_check_complete = True
            
            time.sleep(self.check_interval)
    
    def _check_health(self, url: str) -> bool:
        try:
            response = requests.get(f"{url}/v1/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def _fetch_models(self, url: str) -> List[str]:
        try:
            response = requests.get(f"{url}/v1/models", timeout=3)
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to fetch models from {url}: {e}")
        return []
    
    def stop(self):
        self.running = False

class BridgeManager:
    def __init__(self):
        self.discovery = ServiceDiscovery()
        self.health_monitor = HealthMonitor(self.discovery)
    
    def get_healthy_services(self) -> List[AIService]:
        services = self.discovery.get_all_services()
        return [s for s in services if s.is_healthy]
    
    def get_best_service(self) -> Optional[AIService]:
        services = self.get_healthy_services()
        if not services:
            return None
        return min(services, key=lambda s: s.priority)
    
    def get_service_by_name(self, name: str) -> Optional[AIService]:
        service = self.discovery.get_service(name)
        if service and service.is_healthy:
            return service
        
        service = self.discovery.get_service_by_partial_name(name)
        if service and service.is_healthy:
            return service
        
        return None
    
    def stop(self):
        self.health_monitor.stop()
        self.discovery.stop()

bridge_manager: Optional[BridgeManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge_manager
    bridge_manager = BridgeManager()
    logger.info("Discovery bridge started")
    time.sleep(2)
    
    yield
    
    if bridge_manager:
        bridge_manager.stop()
        logger.info("Discovery bridge stopped")

app = FastAPI(
    title="VLC AI Discovery Bridge",
    description="Bridge between VLC Lua extension and ZeroConf AI services",
    version="1.0",
    lifespan=lifespan
)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    stream: bool = False
    service: Optional[str] = None

@app.get("/")
async def root():
    return {
        "service": "VLC AI Discovery Bridge",
        "status": "running",
        "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/health", "/services"]
    }

@app.get("/services")
async def get_services():
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")
    
    services = bridge_manager.get_healthy_services()
    best = bridge_manager.get_best_service()
    
    return {
        "services": [s.to_dict() for s in services],
        "best": best.to_dict() if best else None,
        "count": len(services)
    }

@app.get("/v1/health")
async def health_check():
    if not bridge_manager:
        return {"status": "error", "message": "Bridge not initialized"}
    
    services = bridge_manager.get_healthy_services()
    
    if services:
        return {
            "status": "ready",
            "healthy_services": len(services),
            "services": [s.name for s in services]
        }
    else:
        return {
            "status": "no_services",
            "healthy_services": 0,
            "message": "No healthy AI services discovered"
        }

@app.get("/v1/models")
async def list_models(service: Optional[str] = None):
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")
    
    if service:
        target_service = bridge_manager.get_service_by_name(service)
        if not target_service:
            raise HTTPException(status_code=404, detail=f"Service '{service}' not found or unhealthy")
        
        return {
            "models": [{"id": m, "service": target_service.name} for m in target_service.available_models],
            "service": target_service.name
        }
    else:
        all_models = []
        for s in bridge_manager.get_healthy_services():
            for model in s.available_models:
                all_models.append({"id": model, "service": s.name})
        
        return {
            "models": all_models,
            "count": len(all_models)
        }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, raw_request: Request):
    if not bridge_manager:
        raise HTTPException(status_code=503, detail="Discovery not initialized")
    
    if request.service:
        target = bridge_manager.get_service_by_name(request.service)
        if not target:
            raise HTTPException(status_code=404, detail=f"Service '{request.service}' not found")
    else:
        target = bridge_manager.get_best_service()
        if not target:
            raise HTTPException(status_code=503, detail="No healthy AI services available")
    
    logger.info(f"Forwarding chat request to {target.name}")
    
    payload = {
        "model": request.model or (target.available_models[0] if target.available_models else "default"),
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        "stream": request.stream
    }
    
    if request.max_tokens:
        payload["max_tokens"] = request.max_tokens
    
    try:
        if request.stream:
            upstream_response = requests.post(
                f"{target.url}/v1/chat/completions",
                json=payload,
                stream=True,
                timeout=60
            )
            
            def generate():
                for chunk in upstream_response.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
        else:
            upstream_response = requests.post(
                f"{target.url}/v1/chat/completions",
                json=payload,
                timeout=60
            )
            
            if upstream_response.status_code != 200:
                raise HTTPException(
                    status_code=upstream_response.status_code,
                    detail=upstream_response.text
                )
            
            return upstream_response.json()
    
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail=f"Request to {target.name} timed out")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error communicating with {target.name}: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VLC AI Discovery Bridge")
    parser.add_argument("--port", type=int, default=9876, help="Port to run the bridge on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()
    
    logger.info(f"Starting bridge on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
]=]

dlg = nil
init_dlg = nil
status_label = nil
service_dropdown = nil
model_dropdown = nil
media_label = nil
chat_display = nil
input_box = nil
bridge_url_input = nil
debug_label = nil
init_status_label = nil

bridge_url = "http://127.0.0.1:9876"
chat_history = {}
current_media = {}
available_services = {}
selected_service_index = nil
selected_model = nil
bridge_process = nil
bridge_ready = false
python_script_path = nil
startup_check_count = 0
bridge_check_timer = nil

function activate()
    vlc.msg.info("[ZeroConf AI] Extension activated")
    start_bridge_initialization()
end

function deactivate()
    if bridge_check_timer then
        bridge_check_timer = nil
    end
    if dlg then
        dlg:delete()
        dlg = nil
    end
    if init_dlg then
        init_dlg:delete()
        init_dlg = nil
    end
    vlc.msg.info("[ZeroConf AI] Extension deactivated")
end

function meta_changed()
    update_media_context()
end

function input_changed()
    update_media_context()
end

function start_bridge_initialization()
    show_init_dialog()
    
    local userdata_path = vlc.config.userdatadir()
    python_script_path = userdata_path .. "/lua/bridge.py"
    local log_path = userdata_path .. "/lua/bridge.log"
    
    local file = io.open(python_script_path, "w")
    if file then
        file:write(BRIDGE_PYTHON_CODE)
        file:close()
        vlc.msg.info("[ZeroConf AI] Bridge script written to: " .. python_script_path)
        update_init_status("Bridge script prepared...")
    else
        vlc.msg.err("[ZeroConf AI] Failed to write bridge script")
        update_init_status("ERROR: Failed to write bridge script")
        return
    end
    
    update_init_status("Launching Python bridge...")
    
    local python_cmd = string.format('python "%s" --host 127.0.0.1 --port 9876 > "%s" 2>&1 &',
        python_script_path, log_path)
    
    vlc.msg.info("[ZeroConf AI] Executing: " .. python_cmd)
    local exec_result = os.execute(python_cmd)
    
    if exec_result == nil or exec_result == false then
        update_init_status("ERROR: Failed to start Python process")
        vlc.msg.err("[ZeroConf AI] Failed to execute Python bridge")
        return
    end
    
    update_init_status("Python bridge starting... (checking in background)")
    
    startup_check_count = 0
    bridge_ready = false
    bridge_check_timer = true
    vlc.msg.info("[ZeroConf AI] Background monitoring started")
end

function show_init_dialog()
    if init_dlg then
        init_dlg:delete()
    end
    
    init_dlg = vlc.dialog("ZeroConf AI - Initializing")
    init_dlg:add_label("<h2>ZeroConf AI Chat is starting...</h2>", 1, 1, 3, 1)
    init_status_label = init_dlg:add_label("Preparing bridge...", 1, 2, 3, 1)
    init_dlg:add_label("<i>The bridge will automatically discover AI services on your network.</i>", 1, 3, 3, 1)
    init_dlg:add_button("Close", close_init_dialog, 1, 4, 1, 1)
    init_dlg:show()
end

function update_init_status(message)
    if init_status_label then
        init_status_label:set_text(message)
        vlc.msg.info("[ZeroConf AI] " .. message)
    end
end

function close_init_dialog()
    if init_dlg then
        init_dlg:delete()
        init_dlg = nil
    end
end

function check_bridge_startup()
    if not bridge_check_timer or bridge_ready then
        return
    end
    
    startup_check_count = startup_check_count + 1
    
    local response = http_get(bridge_url .. "/v1/health")
    if response then
        vlc.msg.info("[ZeroConf AI] Bridge is ready!")
        bridge_ready = true
        bridge_check_timer = nil
        
        update_init_status("Bridge started successfully!")
        close_init_dialog()
        create_dialog()
        check_bridge_status()
        update_media_context()
    else
        if startup_check_count >= 30 then
            update_init_status("Bridge failed to start after 30 seconds")
            vlc.msg.err("[ZeroConf AI] Bridge did not start in time")
            bridge_check_timer = nil
        else
            update_init_status(string.format("Waiting for bridge... (%d/30)", startup_check_count))
        end
    end
end

function create_dialog()
    if dlg then
        dlg:delete()
    end
    
    dlg = vlc.dialog("ZeroConf AI Chat - Media Intelligence")
    
    dlg:add_label("<b>Bridge Configuration:</b>", 1, 1, 2, 1)
    bridge_url_input = dlg:add_text_input(bridge_url, 3, 1, 2, 1)
    dlg:add_button("Save URL", save_bridge_url, 5, 1, 1, 1)
    
    dlg:add_label("<b>Service Status:</b>", 1, 2, 2, 1)
    status_label = dlg:add_label("Checking...", 3, 2, 2, 1)
    
    dlg:add_label("<b>Available Services:</b>", 1, 3, 2, 1)
    service_dropdown = dlg:add_dropdown(3, 3, 2, 1)
    dlg:add_button("Refresh", refresh_services, 5, 3, 1, 1)
    dlg:add_button("Select", on_service_select_button, 6, 3, 1, 1)
    
    dlg:add_label("<b>Model Selection:</b>", 1, 4, 2, 1)
    model_dropdown = dlg:add_dropdown(3, 4, 2, 1)
    dlg:add_button("Select", on_model_select_button, 5, 4, 1, 1)
    
    dlg:add_label("<b>Media Context:</b>", 1, 5, 2, 1)
    media_label = dlg:add_label("No media playing", 3, 5, 3, 1)
    
    dlg:add_label("<b>Chat History:</b>", 1, 6, 2, 1)
    chat_display = dlg:add_html("", 1, 7, 6, 4)
    
    dlg:add_label("<b>Your Message:</b>", 1, 11, 2, 1)
    input_box = dlg:add_text_input("", 1, 12, 5, 1)
    dlg:add_button("Send", send_message, 6, 12, 1, 1)
    
    dlg:add_button("Clear Chat", clear_chat, 1, 13, 1, 1)
    
    debug_label = dlg:add_label("Debug: Ready", 1, 14, 6, 1)
    
    dlg:show()
end

function save_bridge_url()
    local new_url = bridge_url_input:get_text()
    if new_url and new_url ~= "" then
        bridge_url = new_url
        add_to_chat("System", "Bridge URL updated to: " .. bridge_url)
        check_bridge_status()
    end
end

function check_bridge_status()
    if not status_label then return end
    
    debug_label:set_text("Debug: Checking bridge...")
    local response = http_get(bridge_url .. "/v1/health")
    if response then
        local health = parse_json(response)
        if health and health.status == "ready" then
            local msg = string.format("Connected - %d service(s) available", 
                                     health.healthy_services or 0)
            status_label:set_text(msg)
            debug_label:set_text("Debug: Bridge OK")
            refresh_services()
        elseif health and health.status == "no_services" then
            status_label:set_text("Bridge connected but no AI services found")
            debug_label:set_text("Debug: No AI services")
        else
            status_label:set_text("Bridge in unknown state")
            debug_label:set_text("Debug: Unknown state")
        end
    else
        status_label:set_text("Cannot connect to bridge at " .. bridge_url)
        debug_label:set_text("Debug: Bridge unreachable")
    end
end

function refresh_services()
    local response = http_get(bridge_url .. "/services")
    if response then
        local data = parse_json(response)
        if data and data.services then
            available_services = {}
            
            service_dropdown:clear()
            model_dropdown:clear()
            
            selected_service_index = nil
            selected_model = nil
            
            if data.best then
                service_dropdown:add_value("Auto (Best Available)", 0)
            end
            
            for i, service in ipairs(data.services) do
                available_services[i] = service
                local model_count = 0
                if service.models and type(service.models) == "table" then
                    for _ in pairs(service.models) do
                        model_count = model_count + 1
                    end
                end
                local label = string.format("%s (%d models)", service.name, model_count)
                service_dropdown:add_value(label, i)
            end
            
            if data.count and data.count > 0 then
                status_label:set_text(string.format("Found %d AI service(s)", data.count))
                model_dropdown:add_value("(Select a service first)", 0)
                if data.best then
                    service_dropdown:set_text("Auto (Best Available)")
                end
            else
                status_label:set_text("No healthy AI services available")
            end
        end
    else
        status_label:set_text("Failed to query services")
    end
end

function on_service_select_button()
    local idx = service_dropdown:get_value()
    
    if idx == nil then
        debug_label:set_text("Debug: No service selected")
        return
    end
    
    selected_service_index = idx
    selected_model = nil
    
    if idx == 0 then
        debug_label:set_text("Debug: Auto mode - will use best service")
        update_model_dropdown_auto()
    elseif available_services[idx] then
        debug_label:set_text("Debug: Selected " .. available_services[idx].name)
        update_model_dropdown_for_service(available_services[idx])
    else
        debug_label:set_text("Debug: Invalid service index")
    end
end

function on_model_select_button()
    local model_idx = model_dropdown:get_value()
    
    if model_idx == nil or model_idx == 0 then
        debug_label:set_text("Debug: No valid model selected")
        return
    end
    
    local service = get_selected_service()
    if service and service.models and service.models[model_idx] then
        selected_model = service.models[model_idx]
        debug_label:set_text("Debug: Selected model " .. selected_model)
    else
        debug_label:set_text("Debug: Invalid model selection")
    end
end

function get_selected_service()
    if selected_service_index == nil then
        return nil
    end
    
    if selected_service_index == 0 then
        return get_best_service()
    end
    
    if available_services[selected_service_index] then
        return available_services[selected_service_index]
    end
    
    return nil
end

function get_best_service()
    local response = http_get(bridge_url .. "/services")
    if response then
        local data = parse_json(response)
        if data and data.best then
            return data.best
        end
    end
    return nil
end

function update_model_dropdown_auto()
    if not model_dropdown then
        return
    end
    
    model_dropdown:clear()
    
    selected_model = nil
    
    local best_service = get_best_service()
    if best_service then
        update_model_dropdown_for_service(best_service)
    else
        model_dropdown:add_value("(No services available)", 0)
        debug_label:set_text("Debug: No best service available")
    end
end

function update_model_dropdown_for_service(service)
    if not model_dropdown or not service then
        return
    end
    
    model_dropdown:clear()
    
    selected_model = nil
    
    if service.models and type(service.models) == "table" and #service.models > 0 then
        for i, model in ipairs(service.models) do
            model_dropdown:add_value(model, i)
        end
        model_dropdown:set_text(service.models[1])
        debug_label:set_text(string.format("Debug: Loaded %d models from %s", 
                                           #service.models, service.name))
    else
        model_dropdown:add_value("(No models available)", 0)
        debug_label:set_text("Debug: Service has no models")
    end
end

function update_media_context()
    if not media_label then
        return
    end
    
    local input = vlc.object.input()
    if not input then
        media_label:set_text("No media playing")
        current_media = {}
        return
    end
    
    local item = vlc.input.item()
    if not item then
        media_label:set_text("No media information available")
        current_media = {}
        return
    end
    
    local name = item:name() or "Unknown"
    local duration = vlc.var.get(input, "time")
    local length = vlc.var.get(input, "length")
    
    if not current_media.initial_position and duration and duration > 0 then
        current_media.initial_position = duration
    end
    
    current_media.title = name
    current_media.duration = duration
    current_media.length = length
    
    local position_text = format_time(duration)
    local length_text = format_time(length)
    
    media_label:set_text(string.format("%s [%s / %s]", name, position_text, length_text))
end

function send_message()
    local message = input_box:get_text()
    if not message or message == "" then
        debug_label:set_text("Debug: Empty message")
        return
    end
    
    input_box:set_text("")
    
    add_to_chat("You", message)
    
    local request_payload = {
        messages = {}
    }
    
    if current_media and current_media.title then
        local context = string.format("Currently watching: %s", current_media.title)
        if current_media.duration then
            context = context .. string.format(" at %s", format_time(current_media.duration))
        end
        table.insert(request_payload.messages, {
            role = "system",
            content = context
        })
    end
    
    for _, entry in ipairs(chat_history) do
        if entry.sender == "You" then
            table.insert(request_payload.messages, {
                role = "user",
                content = entry.message
            })
        elseif entry.sender == "AI" then
            table.insert(request_payload.messages, {
                role = "assistant",
                content = entry.message
            })
        end
    end
    
    if selected_model then
        request_payload.model = selected_model
    end
    
    local service = get_selected_service()
    if service and service.name then
        request_payload.service = service.name
    end
    
    debug_label:set_text("Debug: Sending request to AI...")
    
    local json_body = json_encode(request_payload)
    
    local temp_file = os.tmpname()
    local output_file = os.tmpname()
    
    local file = io.open(temp_file, "w")
    if not file then
        add_to_chat("Error", "Failed to create temporary request file")
        debug_label:set_text("Debug: Temp file creation failed")
        return
    end
    file:write(json_body)
    file:close()
    
    local curl_cmd = string.format(
        'curl -s -X POST "%s/v1/chat/completions" -H "Content-Type: application/json" -d @"%s" > "%s"',
        bridge_url, temp_file, output_file
    )
    
    local result = os.execute(curl_cmd)
    
    os.remove(temp_file)
    
    if result == nil or result == false then
        add_to_chat("Error", "Failed to execute HTTP request")
        debug_label:set_text("Debug: curl execution failed")
        os.remove(output_file)
        return
    end
    
    local response_file = io.open(output_file, "r")
    if not response_file then
        add_to_chat("Error", "Failed to read response")
        debug_label:set_text("Debug: Response file read failed")
        os.remove(output_file)
        return
    end
    
    local response_data = response_file:read("*a")
    response_file:close()
    os.remove(output_file)
    
    if response_data == "" then
        add_to_chat("Error", "No response from AI service")
        debug_label:set_text("Debug: Empty response")
        return
    end
    
    local response = parse_json(response_data)
    if response and response.choices and response.choices[1] then
        local ai_message = response.choices[1].message
        if ai_message and ai_message.content then
            add_to_chat("AI", ai_message.content)
            debug_label:set_text("Debug: Response received")
        else
            add_to_chat("Error", "Invalid AI response format")
            debug_label:set_text("Debug: Invalid response structure")
        end
    else
        local error_msg = "Failed to get AI response"
        if response and response.error then
            error_msg = response.error
        end
        add_to_chat("Error", error_msg)
        debug_label:set_text("Debug: " .. error_msg)
    end
end

function add_to_chat(sender, message)
    table.insert(chat_history, {sender = sender, message = message})
    update_chat_display()
    return #chat_history
end

function replace_chat_entry(index, sender, message)
    if index and chat_history[index] then
        chat_history[index].sender = sender
        chat_history[index].message = message
        update_chat_display()
    end
end

function update_chat_display()
    if not chat_display then return end
    
    local html = ""
    for _, entry in ipairs(chat_history) do
        if entry.sender == "You" then
            html = html .. "<div style='margin: 5px; padding: 8px; background: #e3f2fd; border-left: 3px solid #2196F3;'>"
            html = html .. "<b style='color: #1976D2;'>You:</b> " .. escape_html(entry.message) .. "</div>"
        elseif entry.sender == "AI" then
            html = html .. "<div style='margin: 5px; padding: 8px; background: #f5f5f5; border-left: 3px solid #4CAF50;'>"
            html = html .. "<b style='color: #388E3C;'>AI:</b> " .. escape_html(entry.message) .. "</div>"
        else
            html = html .. "<div style='margin: 5px; padding: 8px; background: #fff3e0; border-left: 3px solid #FF9800;'>"
            html = html .. "<b style='color: #F57C00;'>" .. escape_html(entry.sender) .. ":</b> " .. escape_html(entry.message) .. "</div>"
        end
    end

    chat_display:set_text(html)
end

function clear_chat()
    chat_history = {}
    if current_media then
        current_media.initial_position = nil
    end
    update_media_context()
    if chat_display then
        chat_display:set_text("")
    end
    if debug_label then
        debug_label:set_text("Debug: Chat cleared")
    end
end

function http_get(url)
    local stream = vlc.stream(url)
    if not stream then
        return nil
    end

    local data = ""
    local chunk_size = 8192
    while true do
        local chunk = stream:read(chunk_size)
        if not chunk or chunk == "" then
            break
        end
        data = data .. chunk
    end

    return data
end

function url_encode(str)
    if not str then return "" end
    str = tostring(str)
    str = str:gsub("\n", "\r\n")
    str = str:gsub("([^%w%-%.%_%~ ])", function(c)
        return string.format("%%%02X", string.byte(c))
    end)
    str = str:gsub(" ", "+")
    return str
end

function parse_json(str)
    if not str or str == "" then
        return nil
    end

    str = str:gsub('^%s*(.-)%s*$', '%1')

    local function decode_value(s, pos)
        local ws_pattern = "^[ \t\n\r]*"
        pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos

        local char = s:sub(pos, pos)

        if char == '"' then
            local end_pos = pos + 1
            while end_pos <= #s do
                if s:sub(end_pos, end_pos) == '"' and s:sub(end_pos - 1, end_pos - 1) ~= '\\' then
                    local value = s:sub(pos + 1, end_pos - 1)
                    value = value:gsub('\\n', '\n'):gsub('\\r', '\r'):gsub('\\t', '\t')
                    value = value:gsub('\\"', '"'):gsub('\\\\', '\\')
                    return value, end_pos + 1
                end
                end_pos = end_pos + 1
            end
            return nil, pos
        elseif char == '{' then
            local obj = {}
            pos = pos + 1
            pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos

            if s:sub(pos, pos) == '}' then
                return obj, pos + 1
            end

            while pos <= #s do
                local key, new_pos = decode_value(s, pos)
                if not key then break end
                pos = new_pos

                pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos
                if s:sub(pos, pos) ~= ':' then break end
                pos = pos + 1

                local value
                value, pos = decode_value(s, pos)
                obj[key] = value

                pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos
                if s:sub(pos, pos) == ',' then
                    pos = pos + 1
                elseif s:sub(pos, pos) == '}' then
                    return obj, pos + 1
                end
            end
            return obj, pos
        elseif char == '[' then
            local arr = {}
            pos = pos + 1
            pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos

            if s:sub(pos, pos) == ']' then
                return arr, pos + 1
            end

            while pos <= #s do
                local value
                value, pos = decode_value(s, pos)
                table.insert(arr, value)

                pos = s:match(ws_pattern, pos) and s:match(ws_pattern, pos):len() + pos or pos
                if s:sub(pos, pos) == ',' then
                    pos = pos + 1
                elseif s:sub(pos, pos) == ']' then
                    return arr, pos + 1
                end
            end
            return arr, pos
        elseif char == 't' and s:sub(pos, pos + 3) == 'true' then
            return true, pos + 4
        elseif char == 'f' and s:sub(pos, pos + 4) == 'false' then
            return false, pos + 5
        elseif char == 'n' and s:sub(pos, pos + 3) == 'null' then
            return nil, pos + 4
        else
            local num_str = s:match('^-?%d+%.?%d*', pos)
            if num_str then
                return tonumber(num_str), pos + #num_str
            end
        end

        return nil, pos
    end

    local result, _ = decode_value(str, 1)
    return result
end

function json_encode(tbl)
    if type(tbl) ~= "table" then
        if type(tbl) == "string" then
            return '"' .. escape_json(tbl) .. '"'
        elseif type(tbl) == "number" then
            return tostring(tbl)
        elseif type(tbl) == "boolean" then
            return tbl and "true" or "false"
        else
            return "null"
        end
    end

    local is_array = true
    local max_index = 0
    local count = 0

    for k, _ in pairs(tbl) do
        count = count + 1
        if type(k) == "number" and k > 0 and k == math.floor(k) then
            max_index = math.max(max_index, k)
        else
            is_array = false
        end
    end

    if is_array and max_index == count then
        local result = "["
        for i = 1, max_index do
            if i > 1 then
                result = result .. ","
            end
            result = result .. json_encode(tbl[i])
        end
        return result .. "]"
    else
        local result = "{"
        local first = true

        for k, v in pairs(tbl) do
            if not first then
                result = result .. ","
            end
            first = false

            result = result .. '"' .. escape_json(tostring(k)) .. '":'
            result = result .. json_encode(v)
        end

        return result .. "}"
    end
end

function escape_json(str)
    if not str then return "" end
    str = tostring(str)
    str = str:gsub('\\', '\\\\')
    str = str:gsub('"', '\\"')
    str = str:gsub('\n', '\\n')
    str = str:gsub('\r', '\\r')
    str = str:gsub('\t', '\\t')
    return str
end

function escape_html(str)
    if not str then return "" end
    str = tostring(str)
    str = str:gsub("&", "&amp;")
    str = str:gsub("<", "&lt;")
    str = str:gsub(">", "&gt;")
    str = str:gsub('"', "&quot;")
    str = str:gsub("'", "&#39;")
    return str
end

function format_time(microseconds)
    if not microseconds or microseconds < 0 then
        return "0:00"
    end

    local seconds = math.floor(microseconds / 1000000)
    local hours = math.floor(seconds / 3600)
    local mins = math.floor((seconds % 3600) / 60)
    local secs = seconds % 60

    if hours > 0 then
        return string.format("%d:%02d:%02d", hours, mins, secs)
    else
        return string.format("%d:%02d", mins, secs)
    end
end

function close()
    deactivate()
end