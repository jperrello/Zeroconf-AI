from pydantic import BaseModel, Field
import requests
import socket
import subprocess
import time
import threading
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Generator, Union


@dataclass
class SaturnService:
    name: str
    address: str
    port: int
    priority: int = 100
    last_seen: datetime = field(default_factory=datetime.now)

    @property
    def base_url(self) -> str:
        return f"http://{self.address}:{self.port}"


class SaturnDiscovery:
    def __init__(self, discovery_timeout: float = 2.0):
        self.services: Dict[str, SaturnService] = {}
        self.lock = threading.Lock()
        self.discovery_timeout = discovery_timeout

    def discover(self) -> Dict[str, SaturnService]:
        try:
            browse_proc = subprocess.Popen(
                ['dns-sd', '-B', '_saturn._tcp', 'local'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            time.sleep(self.discovery_timeout)
            browse_proc.terminate()

            try:
                stdout, _ = browse_proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                browse_proc.kill()
                stdout, _ = browse_proc.communicate()

            service_names = []
            for line in stdout.split('\n'):
                if 'Add' in line and '_saturn._tcp' in line:
                    parts = line.split()
                    if len(parts) > 6:
                        service_names.append(parts[6])

            discovered = {}

            for service_name in service_names:
                service = self._lookup_service(service_name)
                if service:
                    discovered[service_name] = service

            with self.lock:
                self.services = discovered

            return discovered

        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def _lookup_service(self, service_name: str) -> Optional[SaturnService]:
        try:
            lookup_proc = subprocess.Popen(
                ['dns-sd', '-L', service_name, '_saturn._tcp', 'local'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            time.sleep(1.5)
            lookup_proc.terminate()

            try:
                stdout, _ = lookup_proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                lookup_proc.kill()
                stdout, _ = lookup_proc.communicate()

            hostname = None
            port = None
            priority = 100

            for line in stdout.split('\n'):
                if 'can be reached at' in line:
                    match = re.search(r'can be reached at (.+):(\d+)', line)
                    if match:
                        hostname = match.group(1).rstrip('.')
                        port = int(match.group(2))

                if 'priority=' in line:
                    parts = line.split('priority=')
                    if len(parts) > 1:
                        priority_str = parts[1].split()[0]
                        try:
                            priority = int(priority_str)
                        except ValueError:
                            pass

            if hostname and port:
                try:
                    ip_address = socket.gethostbyname(hostname)
                except socket.gaierror:
                    ip_address = hostname

                return SaturnService(
                    name=service_name,
                    address=ip_address,
                    port=port,
                    priority=priority
                )

            return None

        except (subprocess.TimeoutExpired, ValueError, IndexError):
            return None


class Pipe:
    class Valves(BaseModel):
        NAME_PREFIX: str = Field(
            default="SATURN/",
            description="Prefix to be added before model names.",
        )
        DISCOVERY_TIMEOUT: float = Field(
            default=2.0,
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
            default=120,
            description="Timeout in seconds for requests to Saturn services.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.discovery = SaturnDiscovery()
        self.last_discovery_time = 0
        self.cached_services: Dict[str, SaturnService] = {}
        self.model_service_map: Dict[str, List[SaturnService]] = {}
        self.lock = threading.Lock()

    def _get_services(self) -> Dict[str, SaturnService]:
        current_time = time.time()

        with self.lock:
            if current_time - self.last_discovery_time < self.valves.CACHE_TTL and self.cached_services:
                return self.cached_services.copy()

        self.discovery.discovery_timeout = self.valves.DISCOVERY_TIMEOUT
        services = self.discovery.discover()

        with self.lock:
            self.cached_services = services
            self.last_discovery_time = current_time

        return services

    def _fetch_models_from_service(self, service: SaturnService) -> List[Dict]:
        try:
            r = requests.get(
                f"{service.base_url}/v1/models",
                timeout=5
            )
            r.raise_for_status()
            models_data = r.json()

            models_list = models_data.get('data') or models_data.get('models', [])

            return [
                {
                    "id": f"{service.name}:{model['id']}",
                    "name": f"{self.valves.NAME_PREFIX}{service.name}:{model.get('name', model['id'])}",
                    "service_name": service.name,
                    "model_id": model['id'],
                    "base_url": service.base_url,
                    "priority": service.priority
                }
                for model in models_list
                if isinstance(model, dict) and 'id' in model
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
                        "name": "No Saturn services discovered. Ensure Saturn servers are running and dns-sd is available.",
                    }
                ]

            all_models = []
            model_to_services: Dict[str, List[Dict]] = {}

            for service in services.values():
                models = self._fetch_models_from_service(service)
                for model in models:
                    all_models.append(model)
                    model_id = model['model_id']
                    if model_id not in model_to_services:
                        model_to_services[model_id] = []
                    model_to_services[model_id].append(model)

            with self.lock:
                self.model_service_map = {
                    mid: sorted(svc_list, key=lambda x: x['priority'])
                    for mid, svc_list in model_to_services.items()
                }

            if not all_models:
                return [
                    {
                        "id": "no-models",
                        "name": f"Found {len(services)} Saturn service(s) but no models available.",
                    }
                ]

            all_models.sort(key=lambda m: (m['priority'], m['service_name']))

            return [
                {
                    "id": model['id'],
                    "name": model['name']
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

        if '.' in model_string and ':' in model_string:
            dot_idx = model_string.find('.')
            remainder = model_string[dot_idx + 1:]
            if ':' in remainder:
                service_name, model_id = remainder.split(':', 1)
                return service_name, model_id

        if ':' in model_string:
            service_name, model_id = model_string.split(':', 1)
            return service_name, model_id

        return None, model_string

    def _get_service_by_name(self, service_name: str) -> Optional[SaturnService]:
        services = self._get_services()
        return services.get(service_name)

    def _get_fallback_services(self, model_id: str, exclude_service: str) -> List[SaturnService]:
        with self.lock:
            service_list = self.model_service_map.get(model_id, [])

        services = self._get_services()
        fallbacks = []

        for svc_info in service_list:
            if svc_info['service_name'] != exclude_service:
                service = services.get(svc_info['service_name'])
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
                    decoded = line.decode('utf-8')
                    if decoded.startswith('data: '):
                        yield decoded + '\n\n'
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
        last_error = None

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