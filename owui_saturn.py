from pydantic import BaseModel, Field
import requests
import socket
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Generator, Union

from zeroconf import Zeroconf, ServiceBrowser, ServiceListener


SATURN = "_saturn._tcp.local."
DEFAULT_PRIORITY = 50
DISCOVERY_SETTLE_TIME = 3.0
HEALTH_CHECK_TIMEOUT = 5
REQUEST_TIMEOUT_DEFAULT = 60


@dataclass
class SaturnService:
    name: str
    address: str
    port: int
    priority: int = DEFAULT_PRIORITY
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def base_url(self) -> str:
        return f"http://{self.address}:{self.port}"


class SaturnServiceListener(ServiceListener):
    def __init__(self) -> None:
        self.services: Dict[str, SaturnService] = {}
        self.lock = threading.Lock()
        self.service_found = threading.Event()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if not info or not info.addresses:
            return

        with self.lock:
            address = socket.inet_ntoa(info.addresses[0])
            port = info.port
            priority = info.priority if info.priority else DEFAULT_PRIORITY

            if info.properties:
                priority_bytes = info.properties.get(b"priority")
                if priority_bytes:
                    try:
                        priority = int(priority_bytes.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        pass

            clean_name = name.replace(f".{type_}", "").replace(f"._saturn._tcp.local.", "")

            self.services[clean_name] = SaturnService(
                name=clean_name,
                address=address,
                port=port,
                priority=priority,
                last_seen=datetime.now()
            )
            self.service_found.set()

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        clean_name = name.replace(f".{type_}", "").replace(f"._saturn._tcp.local.", "")
        with self.lock:
            if clean_name in self.services:
                del self.services[clean_name]

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def get_services(self) -> Dict[str, SaturnService]:
        with self.lock:
            return dict(self.services)


class SaturnDiscovery:
    def __init__(self, discovery_timeout: float = DISCOVERY_SETTLE_TIME) -> None:
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.listener: Optional[SaturnServiceListener] = None
        self.lock = threading.Lock()
        self.discovery_timeout = discovery_timeout
        self._started = False

    def start(self) -> None:
        with self.lock:
            if self._started:
                return
            self.zeroconf = Zeroconf()
            self.listener = SaturnServiceListener()
            self.browser = ServiceBrowser(self.zeroconf, SATURN, self.listener)
            self._started = True

    def stop(self) -> None:
        with self.lock:
            if not self._started:
                return
            if self.browser:
                self.browser.cancel()
            if self.zeroconf:
                self.zeroconf.close()
            self._started = False

    def get_services(self) -> Dict[str, SaturnService]:
        with self.lock:
            if not self._started:
                return {}
            if self.listener:
                return self.listener.get_services()
            return {}

    def wait_for_services(self, timeout: float = None) -> bool:
        if timeout is None:
            timeout = self.discovery_timeout
        if self.listener:
            return self.listener.service_found.wait(timeout=timeout)
        return False


class Pipe:
    class Valves(BaseModel):
        NAME_PREFIX: str = Field(
            default="SATURN/",
            description="Prefix to be added before model names.",
        )
        DISCOVERY_TIMEOUT: float = Field(
            default=DISCOVERY_SETTLE_TIME,
            description="Timeout in seconds for Saturn service discovery.",
        )
        ENABLE_FAILOVER: bool = Field(
            default=True,
            description="Enable automatic failover to other Saturn services if primary fails.",
        )
        CACHE_TTL: int = Field(
            default=60,
            description="Time-to-live in seconds for cached service discovery results.",
        )
        REQUEST_TIMEOUT: int = Field(
            default=REQUEST_TIMEOUT_DEFAULT,
            description="Timeout in seconds for requests to Saturn services.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self.discovery = SaturnDiscovery()
        self.last_discovery_time: float = 0
        self.cached_services: Dict[str, SaturnService] = {}
        self.model_service_map: Dict[str, List[Dict]] = {}
        self.lock = threading.Lock()
        self._discovery_started = False

    def _ensure_discovery_started(self) -> None:
        if not self._discovery_started:
            self.discovery.start()
            self.discovery.wait_for_services(timeout=self.valves.DISCOVERY_TIMEOUT)
            self._discovery_started = True

    def _get_services(self) -> Dict[str, SaturnService]:
        current_time = time.time()

        with self.lock:
            if current_time - self.last_discovery_time < self.valves.CACHE_TTL and self.cached_services:
                return self.cached_services.copy()

        self._ensure_discovery_started()
        services = self.discovery.get_services()

        with self.lock:
            self.cached_services = services
            self.last_discovery_time = current_time

        return services

    def _fetch_models_from_service(self, service: SaturnService) -> List[Dict]:
        try:
            r = requests.get(
                f"{service.base_url}/v1/models",
                timeout=HEALTH_CHECK_TIMEOUT
            )
            r.raise_for_status()
            models_data = r.json()

            models_list = models_data.get("data") or models_data.get("models", [])

            return [
                {
                    "id": f"{service.name}:{model['id']}",
                    "name": f"{self.valves.NAME_PREFIX}{service.name}:{model.get('name', model['id'])}",
                    "service_name": service.name,
                    "model_id": model["id"],
                    "base_url": service.base_url,
                    "priority": service.priority
                }
                for model in models_list
                if isinstance(model, dict) and "id" in model
            ]

        except Exception:
            return []

    def pipes(self) -> List[Dict]:
        try:
            services = self._get_services()

            if not services:
                return [
                    {
                        "id": "no-services",
                        "name": "No Saturn services discovered. Ensure Saturn servers are running.",
                    }
                ]

            all_models: List[Dict] = []
            model_to_services: Dict[str, List[Dict]] = {}

            for service in services.values():
                models = self._fetch_models_from_service(service)
                for model in models:
                    all_models.append(model)
                    model_id = model["model_id"]
                    if model_id not in model_to_services:
                        model_to_services[model_id] = []
                    model_to_services[model_id].append(model)

            with self.lock:
                self.model_service_map = {
                    mid: sorted(svc_list, key=lambda x: x["priority"])
                    for mid, svc_list in model_to_services.items()
                }

            if not all_models:
                return [
                    {
                        "id": "no-models",
                        "name": f"Found {len(services)} Saturn service(s) but no models available.",
                    }
                ]

            all_models.sort(key=lambda m: (m["priority"], m["service_name"]))

            return [
                {
                    "id": model["id"],
                    "name": model["name"]
                }
                for model in all_models
            ]

        except Exception as e:
            return [
                {
                    "id": "error",
                    "name": f"Error discovering Saturn services: {str(e)}",
                }
            ]

    def _parse_model_string(self, model_string: str) -> tuple[Optional[str], Optional[str]]:
        if model_string.startswith(self.valves.NAME_PREFIX):
            model_string = model_string[len(self.valves.NAME_PREFIX):]

        if "." in model_string and ":" in model_string:
            dot_idx = model_string.find(".")
            remainder = model_string[dot_idx + 1:]
            if ":" in remainder:
                service_name, model_id = remainder.split(":", 1)
                return service_name, model_id

        if ":" in model_string:
            service_name, model_id = model_string.split(":", 1)
            return service_name, model_id

        return None, model_string

    def _get_service_by_name(self, service_name: str) -> Optional[SaturnService]:
        services = self._get_services()
        return services.get(service_name)

    def _get_fallback_services(self, model_id: str, exclude_service: str) -> List[SaturnService]:
        with self.lock:
            service_list = self.model_service_map.get(model_id, [])

        services = self._get_services()
        fallbacks: List[SaturnService] = []

        for svc_info in service_list:
            if svc_info["service_name"] != exclude_service:
                service = services.get(svc_info["service_name"])
                if service:
                    fallbacks.append(service)

        return fallbacks

    def _make_request(
        self,
        service: SaturnService,
        payload: dict,
        stream: bool
    ) -> Union[Dict, Generator]:
        r = requests.post(
            url=f"{service.base_url}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=stream,
            timeout=self.valves.REQUEST_TIMEOUT
        )

        r.raise_for_status()

        if stream:
            return self._stream_response(r)
        else:
            return r.json()

    def _stream_response(self, response: requests.Response) -> Generator:
        try:
            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        yield decoded + "\n\n"
                    elif decoded.strip():
                        yield f"data: {decoded}\n\n"
        finally:
            response.close()

    def pipe(self, body: dict, __user__: dict) -> Union[str, Dict, Generator]:
        model_string = body.get("model", "")
        service_name, model_id = self._parse_model_string(model_string)

        if not model_id:
            return f"Error: Invalid model format. Got: {model_string}"

        if not service_name:
            return f"Error: Could not determine service name from model: {model_string}"

        service = self._get_service_by_name(service_name)

        if not service:
            return f"Error: Saturn service '{service_name}' not found or unavailable."

        payload = {**body, "model": model_id}
        stream = body.get("stream", False)
        last_error: Optional[str] = None

        try:
            return self._make_request(service, payload, stream)
        except Exception as e:
            last_error = str(e)

            if not self.valves.ENABLE_FAILOVER:
                return f"Error: Service {service_name} failed: {last_error}"

        fallbacks = self._get_fallback_services(model_id, service_name)

        for fallback_service in fallbacks:
            try:
                return self._make_request(fallback_service, payload, stream)
            except Exception as e:
                last_error = str(e)
                continue

        return f"Error: All Saturn services failed for model '{model_id}'. Last error: {last_error}"