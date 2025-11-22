function descriptor()
    return {
        title = "Saturn Roast Extension",
        version = "1.0.0",
        author = "Joey Perrello",
        url = "https://github.com/jperrello/Zeroconf-AI",
        shortdesc = "Get Roasted!",
        description = "Let AI roast your media taste using automatic ZeroConf service discovery",
        capabilities = {"input-listener", "meta-listener"}
    }
end

dlg = nil
status_label = nil
service_dropdown = nil
model_dropdown = nil
media_label = nil
roast_display = nil
bridge_url_input = nil
debug_label = nil
roast_button = nil

bridge_url = "http://127.0.0.1:9876"
current_media = {}
last_roast = ""
available_services = {}
selected_service_index = nil
selected_model = nil

-- Bridge process management
bridge_process = nil
bridge_port_file = nil
bridge_launched = false

function activate()
    vlc.msg.info("[Saturn Roast] Extension activated")

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
    vlc.msg.info("[Saturn Roast] Extension deactivated")
end

function meta_changed()
    update_media_context()
end

function input_changed()
    update_media_context()
end

function create_dialog()
    dlg = vlc.dialog("Saturn Roast - Prepare to be Judged")

    dlg:add_label("<b>Bridge Configuration:</b>", 1, 1, 2, 1)
    bridge_url_input = dlg:add_text_input(bridge_url, 3, 1, 2, 1)
    dlg:add_button("Save URL", save_bridge_url, 5, 1, 1, 1)

    dlg:add_label("<b>Service Status:</b>", 1, 2, 2, 1)
    status_label = dlg:add_label("Initializing...", 3, 2, 3, 1)

    dlg:add_label("<b>Available Services:</b>", 1, 3, 2, 1)
    service_dropdown = dlg:add_dropdown(3, 3, 2, 1)
    dlg:add_button("Refresh", refresh_services, 5, 3, 1, 1)
    dlg:add_button("Select", on_service_select_button, 6, 3, 1, 1)

    dlg:add_label("<b>Model Selection:</b>", 1, 4, 2, 1)
    model_dropdown = dlg:add_dropdown(3, 4, 2, 1)
    dlg:add_button("Select", on_model_select_button, 5, 4, 1, 1)

    dlg:add_label("<b>Currently Playing:</b>", 1, 5, 2, 1)
    media_label = dlg:add_label("No media playing", 1, 6, 6, 2)

    dlg:add_label("<b></b>", 1, 8, 6, 1)  -- Spacer

    roast_button = dlg:add_button("🔥 Roast Me! 🔥", get_roasted, 2, 9, 3, 1)

    dlg:add_label("<b>The Verdict:</b>", 1, 10, 2, 1)
    roast_display = dlg:add_html("", 1, 11, 6, 6)

    debug_label = dlg:add_label("Debug: Ready", 1, 17, 6, 1)

    dlg:show()

    -- Set initial message after dialog is shown
    update_roast_display("System", "Click the button above to get roasted!")
end

function save_bridge_url()
    local new_url = bridge_url_input:get_text()
    if new_url and new_url ~= "" then
        bridge_url = new_url
        update_roast_display("System", "Bridge URL updated to: " .. bridge_url)
        check_bridge_status()
    end
end

function check_bridge_status()
    debug_label:set_text("Debug: Checking bridge...")

    -- Retry connection with exponential backoff
    local max_retries = 7
    local retry_delays = {0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 2.5}  -- seconds

    for retry = 1, max_retries do
        vlc.msg.info("[Saturn Roast] Health check attempt " .. retry .. "/" .. max_retries)
        local response = http_get(bridge_url .. "/v1/health")
        if response then
            local health = parse_json(response)
            if health and health.status == "ready" then
                local msg = string.format("Ready to roast! (%d AI service(s) available)",
                                         health.healthy_services or 0)
                status_label:set_text(msg)
                debug_label:set_text("Debug: Bridge OK")
                vlc.msg.info("[Saturn Roast] Bridge connection successful!")
                refresh_services()
                return
            elseif health and health.status == "no_services" then
                status_label:set_text("Bridge connected but no AI services found")
                debug_label:set_text("Debug: No AI services")
                vlc.msg.info("[Saturn Roast] Bridge connected, waiting for AI services...")
                return
            elseif health and health.status == "starting" then
                vlc.msg.info("[Saturn Roast] Bridge still starting, waiting...")
                status_label:set_text("Bridge initializing...")
                debug_label:set_text("Debug: Bridge starting")
            elseif health and health.status then
                status_label:set_text("Bridge in state: " .. health.status)
                debug_label:set_text("Debug: " .. health.status)
                vlc.msg.info("[Saturn Roast] Bridge state: " .. health.status)
                return
            end
        end

        -- If we get here, connection failed - retry with delay
        if retry < max_retries then
            vlc.msg.info("[Saturn Roast] Connection attempt " .. retry .. " failed, retrying in " .. retry_delays[retry] .. "s...")
            local delay = retry_delays[retry]
            local start = os.clock()
            while os.clock() - start < delay do end
        end
    end

    -- All retries exhausted
    vlc.msg.err("[Saturn Roast] Bridge connection failed after " .. max_retries .. " attempts")
    status_label:set_text("Cannot connect to bridge at " .. bridge_url)
    debug_label:set_text("Debug: Bridge unreachable after retries")
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
        media_label:set_text("No media playing - Play something to get roasted!")
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

    current_media = {
        title = title,
        uri = uri,
        duration = duration,
        current_time = current_time,
        formatted_time = format_time(current_time),
        formatted_duration = format_time(duration)
    }

    local meta_fields = {"artist", "album", "genre", "track_number", "description", "rating", "date"}
    for _, field in ipairs(meta_fields) do
        local value = item:metas()[field]
        if value and value ~= "" then
            current_media[field] = value
        end
    end

    local display_text = string.format(" %s [%s / %s]",
        title,
        current_media.formatted_time,
        current_media.formatted_duration
    )

    if current_media.artist then
        display_text = display_text .. "\n Artist: " .. current_media.artist
    end
    if current_media.album then
        display_text = display_text .. " |  Album: " .. current_media.album
    end
    if current_media.genre then
        display_text = display_text .. "\n Genre: " .. current_media.genre
    end

    media_label:set_text(display_text)
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
                status_label:set_text(string.format("Ready to roast! (%d AI service(s))", data.count))
                model_dropdown:add_value("(Select a service first)", 0)
                if data.best then
                    service_dropdown:set_text("Auto (Best Available)")
                    selected_service_index = 0
                    update_model_dropdown_auto()
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

function build_roast_prompt()
    if not current_media or not current_media.title then
        return nil
    end

    local prompt = "Roast my media taste! I'm currently watching/listening to: " .. current_media.title

    if current_media.artist then
        prompt = prompt .. " by " .. current_media.artist
    end

    if current_media.album then
        prompt = prompt .. " from the album '" .. current_media.album .. "'"
    end

    if current_media.genre then
        prompt = prompt .. " (Genre: " .. current_media.genre .. ")"
    end

    prompt = prompt .. ". Give me a funny, creative roast about my choice in media. Be witty and sarcastic but keep it lighthearted and fun!"

    return prompt
end

function get_roasted()
    if not current_media or not current_media.title then
        update_roast_display("Error", "No media playing! Play something first so I have something to roast.")
        debug_label:set_text("Debug: No media to roast")
        return
    end

    local service = get_selected_service()
    if not service then
        update_roast_display("Error", "No AI service selected. Please select a service first or click Refresh.")
        debug_label:set_text("Debug: No service available")
        return
    end

    local model = selected_model
    if not model and service.models and #service.models > 0 then
        model = service.models[1]
        selected_model = model
    end

    if not model then
        update_roast_display("Error", "No model available for selected service!")
        debug_label:set_text("Debug: No model available")
        return
    end

    -- Update UI to show "Thinking..." state
    update_roast_display("Thinking", "AI is thinking of ways to roast you...")
    debug_label:set_text("Debug: Preparing roast request...")

    -- Force a small delay to allow UI to update before blocking HTTP call
    local start = os.clock()
    while os.clock() - start < 0.1 do end

    debug_label:set_text("Debug: Sending roast request to " .. service.name)

    local roast_prompt = build_roast_prompt()

    local messages = {
        {
            role = "system",
            content = "You are a witty AI comedian who loves to playfully roast people's media choices. " ..
                     "Be creative, funny, and sarcastic but keep it lighthearted and fun. " ..
                     "Keep your roast to 2-3 sentences maximum."
        },
        {
            role = "user",
            content = roast_prompt
        }
    }

    local payload = {
        model = model,
        messages = messages,
        max_tokens = 200
    }

    local service_param = ""
    if selected_service_index ~= 0 and service.name then
        service_param = "&service=" .. url_encode(service.name)
    end

    local encoded_payload = url_encode(json_encode(payload))
    local url = string.format("%s/v1/chat/completions?payload=%s%s",
        bridge_url, encoded_payload, service_param)

    local ai_response = http_get(url)

    if ai_response then
        vlc.msg.info("[Saturn Roast] Response received, length: " .. string.len(ai_response))
        vlc.msg.info("[Saturn Roast] Response preview: " .. string.sub(ai_response, 1, 200))

        local ai_data = parse_json(ai_response)
        if ai_data and ai_data.choices and ai_data.choices[1] and ai_data.choices[1].message then
            local roast = ai_data.choices[1].message.content
            vlc.msg.info("[Saturn Roast] Roast content: " .. roast)
            last_roast = roast
            debug_label:set_text("Debug: Roast received from " .. service.name)
            update_roast_display("AI Roast", roast)
            vlc.msg.info("[Saturn Roast] Display updated successfully")
        elseif ai_data and ai_data.detail then
            vlc.msg.err("[Saturn Roast] API Error: " .. ai_data.detail)
            update_roast_display("Error", "API Error: " .. ai_data.detail)
            debug_label:set_text("Debug: API error")
        else
            vlc.msg.err("[Saturn Roast] Bad response format, ai_data type: " .. type(ai_data))
            if ai_data then
                vlc.msg.err("[Saturn Roast] ai_data.choices exists: " .. tostring(ai_data.choices ~= nil))
            end
            update_roast_display("Error", "Unexpected response format from AI service")
            debug_label:set_text("Debug: Bad response format")
        end
    else
        vlc.msg.err("[Saturn Roast] No response received from HTTP request")
        update_roast_display("Error", "Failed to get response from AI service")
        debug_label:set_text("Debug: AI request failed")
    end
end

function update_roast_display(title, message)
    vlc.msg.info("[Saturn Roast] update_roast_display called with title: " .. title .. ", message length: " .. string.len(message or ""))

    if not roast_display then
        vlc.msg.err("[Saturn Roast] roast_display is nil!")
        return
    end

    local html = ""

    if title == "AI Roast" then
        html = "<div style='margin: 10px; padding: 20px; background-color: #9370db; border: 3px solid #ff6b6b;'>"
        html = html .. "<div style='color: #ffffff; font-size: 18px; font-weight: bold; text-align: center; margin-bottom: 15px;'>"
        html = html .. "THE VERDICT</div>"
        html = html .. "<div style='color: #000000; font-size: 16px; text-align: center;'>"
        html = html .. escape_html(message)
        html = html .. "</div></div>"
    elseif title == "Thinking" then
        html = "<div style='padding: 30px; text-align: center; background-color: #f0f0f0;'>"
        html = html .. "<div style='color: #666666; font-size: 16px;'>" .. escape_html(message) .. "</div>"
        html = html .. "</div>"
    elseif title == "Error" then
        html = "<div style='padding: 20px; background-color: #ffebee; border-left: 4px solid #f44336;'>"
        html = html .. "<div style='color: #c62828; font-weight: bold;'>Error</div>"
        html = html .. "<div style='color: #c62828; margin-top: 10px;'>" .. escape_html(message) .. "</div>"
        html = html .. "</div>"
    elseif title == "System" then
        html = "<div style='padding: 20px; text-align: center; color: #666666;'>" .. escape_html(message) .. "</div>"
    else
        html = "<div style='padding: 20px; text-align: center; color: #999999;'>" .. escape_html(message) .. "</div>"
    end

    vlc.msg.info("[Saturn Roast] Setting roast_display HTML, length: " .. string.len(html))
    vlc.msg.info("[Saturn Roast] HTML content: " .. string.sub(html, 1, 100))
    roast_display:set_text(html)
    vlc.msg.info("[Saturn Roast] roast_display:set_text() called successfully")
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

    vlc.msg.info("[Saturn Roast] OS detected: " .. os_type)
    vlc.msg.info("[Saturn Roast] Extension dir: " .. extension_dir)

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
        vlc.msg.warn("[Saturn Roast] Bridge executable not found at: " .. bridge_exe)
        vlc.msg.info("[Saturn Roast] Will use external bridge if running")
        return
    end
    file:close()

    -- Create port file path
    local temp_dir = get_temp_dir()
    bridge_port_file = temp_dir .. (os_type == "windows" and "\\" or "/") .. "vlc_bridge_port.txt"

    vlc.msg.info("[Saturn Roast] Launching bridge: " .. bridge_exe)
    vlc.msg.info("[Saturn Roast] Port file: " .. bridge_port_file)

    -- Clean up old port file if it exists
    os.remove(bridge_port_file)

    -- Launch the bridge with port file argument
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
        vlc.msg.err("[Saturn Roast] Failed to launch bridge process")
        return
    end

    vlc.msg.info("[Saturn Roast] Bridge process launched")
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
                    vlc.msg.info("[Saturn Roast] Port file found: " .. bridge_url)

                    -- Add additional delay after port file appears
                    vlc.msg.info("[Saturn Roast] Waiting for server to fully initialize...")
                    local safety_delay = 0.5  -- 500ms safety margin
                    local start = os.clock()
                    while os.clock() - start < safety_delay do end

                    vlc.msg.info("[Saturn Roast] Bridge should be ready")
                    return
                end
            end
        end
        -- Sleep for 100ms
        local start = os.clock()
        while os.clock() - start < 0.1 do end
        wait_count = wait_count + 1
    end

    vlc.msg.warn("[Saturn Roast] Timeout waiting for bridge to start")
    vlc.msg.warn("[Saturn Roast] Check VLC messages for errors or try running bridge manually")
end

function shutdown_bridge()
    if not bridge_launched then
        return
    end

    vlc.msg.info("[Saturn Roast] Shutting down bridge...")

    -- Send shutdown request to bridge
    local shutdown_url = bridge_url .. "/shutdown"
    local success = pcall(function()
        http_post(shutdown_url)
    end)

    if success then
        vlc.msg.info("[Saturn Roast] Bridge shutdown signal sent")
    else
        vlc.msg.warn("[Saturn Roast] Failed to send shutdown signal to bridge")
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
