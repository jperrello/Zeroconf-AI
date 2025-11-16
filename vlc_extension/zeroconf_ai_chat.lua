function descriptor()
    return {
        title = "ZeroConf AI Chat",
        version = "1.5.1",
        author = "Joey Perrello",
        url = "https://github.com/yourrepo/zeroconfai",
        shortdesc = "AI chat with automatic service discovery",
        description = "Chat with AI about your media using automatic ZeroConf service discovery - Fixed race condition and Windows launch issues",
        capabilities = {"input-listener", "meta-listener"}
    }
end

dlg = nil
status_label = nil
service_dropdown = nil
model_dropdown = nil
media_label = nil
chat_display = nil
input_box = nil
bridge_url_input = nil
debug_label = nil

bridge_url = "http://127.0.0.1:9876"
chat_history = {}
current_media = {}
available_services = {}
selected_service_index = nil
selected_model = nil

-- Bridge process management
bridge_process = nil
bridge_port_file = nil
bridge_launched = false

function activate()
    vlc.msg.info("[ZeroConf AI] Extension activated")

    -- Try to launch the bundled bridge executable
    launch_bridge()

    create_dialog()
    check_bridge_status()
    update_media_context()
end

function deactivate()
    -- Shutdown the bridge if we launched it
    shutdown_bridge()

    if dlg then
        dlg:delete()
        dlg = nil
    end
    vlc.msg.info("[ZeroConf AI] Extension deactivated")
end

function meta_changed()
    update_media_context()
end

function input_changed()
    update_media_context()
end

function create_dialog()
    dlg = vlc.dialog("ZeroConf AI Chat - Media Intelligence")
    
    dlg:add_label("<b>Bridge Configuration:</b>", 1, 1, 2, 1)
    bridge_url_input = dlg:add_text_input(bridge_url, 3, 1, 2, 1)
    dlg:add_button("Save URL", save_bridge_url, 5, 1, 1, 1)
    
    dlg:add_label("<b>Service Status:</b>", 1, 2, 2, 1)
    status_label = dlg:add_label("Initializing...", 3, 2, 2, 1)
    
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
    debug_label:set_text("Debug: Checking bridge...")

    -- Retry connection with exponential backoff
    -- Note: The bridge should already be ready by the time we call this,
    -- but we retry in case of transient network issues
    local max_retries = 7
    local retry_delays = {0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 2.5}  -- seconds

    for retry = 1, max_retries do
        vlc.msg.info("[ZeroConf AI] Health check attempt " .. retry .. "/" .. max_retries)
        local response = http_get(bridge_url .. "/v1/health")
        if response then
            local health = parse_json(response)
            if health and health.status == "ready" then
                local msg = string.format("Connected - %d service(s) available",
                                         health.healthy_services or 0)
                status_label:set_text(msg)
                debug_label:set_text("Debug: Bridge OK")
                vlc.msg.info("[ZeroConf AI] Bridge connection successful!")
                refresh_services()
                return
            elseif health and health.status == "no_services" then
                status_label:set_text("Bridge connected but no AI services found")
                debug_label:set_text("Debug: No AI services")
                vlc.msg.info("[ZeroConf AI] Bridge connected, waiting for AI services...")
                return
            elseif health and health.status == "starting" then
                -- Bridge is still initializing
                vlc.msg.info("[ZeroConf AI] Bridge still starting, waiting...")
                status_label:set_text("Bridge initializing...")
                debug_label:set_text("Debug: Bridge starting")
                -- Continue to retry
            elseif health and health.status then
                status_label:set_text("Bridge in state: " .. health.status)
                debug_label:set_text("Debug: " .. health.status)
                vlc.msg.info("[ZeroConf AI] Bridge state: " .. health.status)
                return
            end
        end

        -- If we get here, connection failed - retry with delay
        if retry < max_retries then
            vlc.msg.info("[ZeroConf AI] Connection attempt " .. retry .. " failed, retrying in " .. retry_delays[retry] .. "s...")
            local delay = retry_delays[retry]
            local start = os.clock()
            while os.clock() - start < delay do end
        end
    end

    -- All retries exhausted
    vlc.msg.err("[ZeroConf AI] Bridge connection failed after " .. max_retries .. " attempts")
    status_label:set_text("Cannot connect to bridge at " .. bridge_url)
    debug_label:set_text("Debug: Bridge unreachable after retries")
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
        selected_model = service.models[1]
        debug_label:set_text("Debug: Loaded " .. #service.models .. " models from " .. service.name)
    else
        model_dropdown:add_value("(No models available)", 0)
        model_dropdown:set_text("(No models available)")
        debug_label:set_text("Debug: No models available for " .. service.name)
    end
end

function update_model_dropdown()
    update_model_dropdown_for_service(get_selected_service())
end

function get_current_timestamp()
    local input_obj = vlc.object.input()
    if input_obj then
        local time_microsec = vlc.var.get(input_obj, "time")
        if time_microsec and time_microsec > 0 then
            return time_microsec
        end
    end
    return 0
end

function update_media_context()
    local input_obj = vlc.object.input()
    if not input_obj then
        media_label:set_text("No media playing")
        current_media = {}
        return
    end
    
    local item = vlc.input.item()
    if not item then
        media_label:set_text("No media item")
        current_media = {}
        return
    end
    
    local uri = vlc.strings.decode_uri(item:uri())
    
    local title = item:name()
    if not title or title == "" then
        title = uri
    end
    
    local duration = item:duration()
    local current_time = get_current_timestamp()
    
    if not current_media.initial_position and #chat_history == 0 then
        current_media.initial_position = current_time
    end
    
    current_media = {
        title = title,
        uri = uri,
        duration = duration,
        current_time = current_time,
        formatted_time = format_time(current_time),
        formatted_duration = format_time(duration),
        initial_position = current_media.initial_position,
        formatted_initial = format_time(current_media.initial_position or 0)
    }
    
    local meta_fields = {"artist", "album", "genre", "track_number", "description", "rating", "date"}
    for _, field in ipairs(meta_fields) do
        local value = item:metas()[field]
        if value and value ~= "" then
            current_media[field] = value
        end
    end
    
    local display_text = string.format("%s [%s / %s]", 
        title, 
        current_media.formatted_time, 
        current_media.formatted_duration
    )
    
    if current_media.artist then
        display_text = display_text .. "\nArtist: " .. current_media.artist
    end
    if current_media.album then
        display_text = display_text .. " | Album: " .. current_media.album
    end
    
    media_label:set_text(display_text)
end

function build_context_string()
    if not current_media or not current_media.title then
        return "No media context available."
    end
    
    local context = string.format("Currently playing: %s", current_media.title)
    
    if current_media.artist then
        context = context .. string.format(" by %s", current_media.artist)
    end
    
    if current_media.album then
        context = context .. string.format(" from the album '%s'", current_media.album)
    end
    
    if current_media.genre then
        context = context .. string.format(" (Genre: %s)", current_media.genre)
    end
    
    if current_media.current_time and current_media.duration then
        context = context .. string.format("\nPlayback position: %s out of %s", 
            current_media.formatted_time, 
            current_media.formatted_duration
        )
    end
    
    if current_media.initial_position and current_media.initial_position > 0 then
        context = context .. string.format("\n(Conversation started at: %s)", 
            current_media.formatted_initial
        )
    end
    
    return context
end

function send_message()
    local message = input_box:get_text()
    if not message or message == "" then
        debug_label:set_text("Debug: Empty message")
        return
    end
    
    input_box:set_text("")
    
    local service = get_selected_service()
    if not service then
        add_to_chat("Error", "No AI service selected. Please select a service first.")
        debug_label:set_text("Debug: No service available")
        return
    end
    
    local model = selected_model
    if not model and service.models and #service.models > 0 then
        model = service.models[1]
        selected_model = model
    end
    
    if not model then
        add_to_chat("Error", "No model available for selected service")
        debug_label:set_text("Debug: No model available")
        return
    end
    
    local user_index = add_to_chat("You", message)
    local thinking_index = add_to_chat("AI", "Thinking...")
    
    local messages = {}
    
    local context = build_context_string()
    table.insert(messages, {
        role = "system",
        content = "You are a helpful AI assistant integrated into VLC media player. " ..
                 "You can see what the user is currently playing and help them with questions about their media. " ..
                 "Keep responses concise and relevant. Current media context: " .. context
    })
    
    for i, entry in ipairs(chat_history) do
        if i < user_index then
            if entry.sender == "You" then
                table.insert(messages, {role = "user", content = entry.message})
            elseif entry.sender == "AI" then
                table.insert(messages, {role = "assistant", content = entry.message})
            end
        end
    end
    
    table.insert(messages, {role = "user", content = message})
    
    local payload = {
        model = model,
        messages = messages,
        max_tokens = 500
    }
    
    local service_param = ""
    if selected_service_index ~= 0 and service.name then
        service_param = "&service=" .. url_encode(service.name)
    end
    
    local encoded_payload = url_encode(json_encode(payload))
    local url = string.format("%s/v1/chat/completions?payload=%s%s", 
        bridge_url, encoded_payload, service_param)
    
    debug_label:set_text("Debug: Sending to " .. service.name .. " with model " .. model)
    
    local response = http_get(url)
    
    if response then
        local data = parse_json(response)
        if data and data.choices and data.choices[1] and data.choices[1].message then
            local ai_response = data.choices[1].message.content
            replace_chat_entry(thinking_index, "AI", ai_response)
            debug_label:set_text("Debug: Response received")
        elseif data and data.detail then
            replace_chat_entry(thinking_index, "Error", "API Error: " .. data.detail)
            debug_label:set_text("Debug: API error")
        else
            replace_chat_entry(thinking_index, "Error", "Unexpected response format")
            debug_label:set_text("Debug: Bad response format")
        end
    else
        replace_chat_entry(thinking_index, "Error", "Failed to connect to AI service")
        debug_label:set_text("Debug: Connection failed")
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
    chat_display:set_text("")
    debug_label:set_text("Debug: Chat cleared")
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

function detect_os()
    local sep = package.config:sub(1, 1)
    if sep == "\\" then
        return "windows"
    else
        -- Try to detect macOS vs Linux
        local handle = io.popen("uname -s 2>/dev/null")
        if handle then
            local uname = handle:read("*a")
            handle:close()
            if uname and uname:match("Darwin") then
                return "macos"
            end
        end
        return "linux"
    end
end

function get_extension_dir()
    -- Get the directory where this Lua script is located
    local info = debug.getinfo(1, "S")
    if info and info.source then
        local script_path = info.source:match("@?(.*)")
        if script_path then
            -- Extract directory from the script path
            local dir = script_path:match("(.*/)")
            if not dir then
                dir = script_path:match("(.*\\)")
            end
            return dir or ""
        end
    end
    return ""
end

function get_temp_dir()
    local os_type = detect_os()
    if os_type == "windows" then
        return os.getenv("TEMP") or os.getenv("TMP") or "C:\\Temp"
    else
        return os.getenv("TMPDIR") or "/tmp"
    end
end

function launch_bridge()
    local os_type = detect_os()
    local extension_dir = get_extension_dir()

    vlc.msg.info("[ZeroConf AI] OS detected: " .. os_type)
    vlc.msg.info("[ZeroConf AI] Extension dir: " .. extension_dir)

    -- Determine the bridge executable path
    local bridge_exe
    if os_type == "windows" then
        bridge_exe = extension_dir .. "bridge\\vlc_discovery_bridge.exe"
    else
        bridge_exe = extension_dir .. "bridge/vlc_discovery_bridge"
    end

    -- Check if the bridge executable exists
    local file = io.open(bridge_exe, "r")
    if not file then
        vlc.msg.warn("[ZeroConf AI] Bridge executable not found at: " .. bridge_exe)
        vlc.msg.info("[ZeroConf AI] Will use external bridge if running")
        return
    end
    file:close()

    -- Create port file path
    local temp_dir = get_temp_dir()
    bridge_port_file = temp_dir .. (os_type == "windows" and "\\" or "/") .. "vlc_bridge_port.txt"

    vlc.msg.info("[ZeroConf AI] Launching bridge: " .. bridge_exe)
    vlc.msg.info("[ZeroConf AI] Port file: " .. bridge_port_file)

    -- Clean up old port file if it exists
    os.remove(bridge_port_file)

    -- Launch the bridge with port file argument
    -- CRITICAL: Use os.execute with proper backgrounding, NOT io.popen
    local cmd
    local exec_result
    if os_type == "windows" then
        -- Use 'start /B' to run in background without opening new window
        cmd = string.format('start /B "" "%s" --port-file "%s"', bridge_exe, bridge_port_file)
        exec_result = os.execute(cmd)
    else
        -- Unix/Linux/macOS: use & to background
        cmd = string.format('"%s" --port-file "%s" > /dev/null 2>&1 &', bridge_exe, bridge_port_file)
        exec_result = os.execute(cmd)
    end

    if exec_result == nil or exec_result == false then
        vlc.msg.err("[ZeroConf AI] Failed to launch bridge process")
        return
    end

    vlc.msg.info("[ZeroConf AI] Bridge process launched")
    bridge_launched = true

    -- Wait for the port file to be created AND valid (max 10 seconds)
    local max_wait = 100  -- 100 * 100ms = 10 seconds
    local wait_count = 0
    while wait_count < max_wait do
        local port_file = io.open(bridge_port_file, "r")
        if port_file then
            local content = port_file:read("*all")
            port_file:close()
            if content and content ~= "" then
                -- Parse host:port from file
                local host, port = content:match("([^:]+):(%d+)")
                if host and port then
                    bridge_url = "http://" .. host .. ":" .. port
                    vlc.msg.info("[ZeroConf AI] Port file found: " .. bridge_url)

                    -- CRITICAL: Add additional delay after port file appears
                    -- The bridge writes the port file AFTER the server is ready,
                    -- but we add a small safety margin for network stack initialization
                    vlc.msg.info("[ZeroConf AI] Waiting for server to fully initialize...")
                    local safety_delay = 0.5  -- 500ms safety margin
                    local start = os.clock()
                    while os.clock() - start < safety_delay do end

                    vlc.msg.info("[ZeroConf AI] Bridge should be ready")
                    return
                end
            end
        end
        -- Sleep for 100ms
        local start = os.clock()
        while os.clock() - start < 0.1 do end
        wait_count = wait_count + 1
    end

    vlc.msg.warn("[ZeroConf AI] Timeout waiting for bridge to start")
    vlc.msg.warn("[ZeroConf AI] Check VLC messages for errors or try running bridge manually")
end

function shutdown_bridge()
    if not bridge_launched then
        return
    end

    vlc.msg.info("[ZeroConf AI] Shutting down bridge...")

    -- Send shutdown request to bridge
    local shutdown_url = bridge_url .. "/shutdown"
    local success = pcall(function()
        http_post(shutdown_url)
    end)

    if success then
        vlc.msg.info("[ZeroConf AI] Bridge shutdown signal sent")
    else
        vlc.msg.warn("[ZeroConf AI] Failed to send shutdown signal to bridge")
    end

    -- Clean up port file
    if bridge_port_file then
        os.remove(bridge_port_file)
    end

    bridge_launched = false
    bridge_process = nil
end

function http_post(url)
    -- Simple POST request using stream
    -- For VLC Lua, we can use io.popen with curl if available, or just ignore
    -- Since the bridge will exit anyway when VLC closes
    local os_type = detect_os()
    local cmd
    if os_type == "windows" then
        cmd = string.format('powershell -Command "Invoke-WebRequest -Uri \'%s\' -Method POST" 2>nul', url)
    else
        cmd = string.format('curl -X POST "%s" 2>/dev/null', url)
    end

    local handle = io.popen(cmd)
    if handle then
        handle:close()
    end
end

function close()
    deactivate()
end