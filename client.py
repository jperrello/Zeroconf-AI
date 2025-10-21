import time
import threading
import requests
import socket
from enum import Enum
from zeroconf import ServiceListener, ServiceBrowser, Zeroconf
from typing import Callable, Optional

 
class ServiceEvent(Enum):
    ADDED = "added"
    REMOVED = "removed"
    UPDATED = "updated"

class ServiceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.services = {}
            print("Joey successfully initialized the service manager")
            self.zc = Zeroconf()
            self.ai_listener = ZeroconfAIListener(service_manager=self)
            self.browser = ServiceBrowser(self.zc, "_zeroconfai._tcp.local.", self.ai_listener)
            self._event_callbacks = []
            self._start_health_monitor()

    def add_service_to_manager(self, name: str, url: str):
        if url in self.services and self.services[url]== name:
            print(f"The service: {name} is already registered at {url}")
            return
        self.services[url] = name
        self._notify_event(ServiceEvent.ADDED, name, url)

    def remove_service_from_manager(self, name: str, url: str):
        if url in self.services and self.services[url] == name:
            del self.services[url]
            self._notify_event(ServiceEvent.REMOVED, name, url)
        else:
            print(f"Tried to remove unknown service: {name}")

    def is_service_available(self, url: str) -> bool:
        return url in self.services
        
    def on_service_event(self, callback: Callable[[ServiceEvent, str, str], None]) -> None:
        self._event_callbacks.append(callback)

    def _notify_event(self, event: ServiceEvent, name: str, url: str) -> None:
        for callback in self._event_callbacks:
            try:
                callback(event, name, url)
            except Exception as e:
                print(f"Error in event callback: {e}")        
    

    def _start_health_monitor(self, interval: float = 5.0) -> None:
        def monitor():
            while True:
                time.sleep(interval)
                for url, name in list(self.services.items()):
                    if not verify_service_health(url):
                        print(f"Service {name} at {url} is no longer healthy. Removing from manager.")
                        self.remove_service_from_manager(name, url)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    
    def __iter__(self):
        return iter(self.services)
    
    def __len__(self):
        return len(self.services)
    
    def __contains__(self, name: str) -> bool:
        return name in self.services
    
    def items(self):
        return self.services.items()
    


class ZeroconfAIListener(ServiceListener):
    def __init__(self, service_manager):
        self.service_manager = service_manager

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)

        if info:
            address=socket.inet_ntoa(info.addresses[0])
            port=info.port
            url = f"http://{address}:{port}"
            self.service_manager.add_service_to_manager(name, url)
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)

        if info:
            address=socket.inet_ntoa(info.addresses[0])
            port=info.port
            url = f"http://{address}:{port}"
            self.service_manager.remove_service_from_manager(name, url)
        else:
            for stored_url, stored_name in self.service_manager.items():
                if stored_name == name:
                    self.service_manager.remove_service_from_manager(name, stored_url)
                    break

  
class ZeroconfAIClient:
    def __init__(self, service_manager: ServiceManager, url: str = None):
        self.service_manager = service_manager
        self._active_url = url
        self._active_name = None
        self.chat_history = []
        self.service_available = True

        self.service_manager.on_service_event(self._handle_service_event)

        if url:
            self._validate_and_set_service(url)
        
    def _validate_and_set_service(self, url: str):
        if self.service_manager.is_service_available(url):
            self._active_url = url
            self._active_name = self.service_manager.services[url]
            self.service_available = True
        else:
            self.service_available = False
            raise Exception(f"Service at {url} is not available.")
        
    def _handle_service_event(self, event: ServiceEvent, name: str, url: str):
        if url == self._active_url:
            if event == ServiceEvent.REMOVED:
                print(f"Active service {name} at {url} has been removed.")
                self.service_available = False
            elif event == ServiceEvent.ADDED:
                print(f"Active service {name} at {url} has been added back.")
                self.service_available = True

    def set_active_service(self, url: str):
        self._validate_and_set_service(url)

    @property
    def is_connected(self) -> bool:
        return (self._active_url is not None and self.service_available and self.service_manager.is_service_available(self._active_url))
    
    def chat(self, user_message: str, model: str = "google/gemini-2.5-flash-lite-preview-09-2025", max_history: int = 10) -> str:
        
        if not self.is_connected:
            raise RuntimeError(f"No active service with URL {self._active_url} is connected.")
        if not self._active_url:
            raise RuntimeError("No active service URL is set. Call set_active_service(url) first.")


        # Trim history naively
        if len(self.chat_history) > max_history * 2:  # *2 because each exchange is 2 messages
            self.chat_history = self.chat_history[2:]  # Remove oldest exchange
        
        current_message = self.chat_history + [{"role": "user", "content": user_message}]
        
        payload = {
            "model": model,
            "messages": current_message,
        }

        try:
            response = requests.post(f"{self._active_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            assistant_message = data['choices'][0]['message']['content']
            self.chat_history.append({"role": "user", "content": user_message})
            self.chat_history.append({"role": "assistant", "content": assistant_message})
            return assistant_message
        except requests.RequestException as e:
            self.service_available = False
            raise RuntimeError(f"Error communicating with the AI service at {self._active_url}: {e}")
        
    def clear_history(self):
        self.chat_history = []

    def get_active_service_info(self) -> Optional[tuple[str, str]]:
        if self._active_url and self._active_name:
            return (self._active_name, self._active_url)
        return None
    

def verify_service_health(url: str, timeout: float = 2.0) -> bool:
    try:
        response = requests.get(f"{url}/v1/health", timeout=timeout)
        return response.status_code == 200
    except:
        return False # if it isnt 200 the site is down for some reason, i can make more specific exceptions but this is fine for now
#====================================
def main():
    #this is just a demo, the actual magic is above ^^^
    timeout = 10.0 
    print("Searching for AI services on your network...")

    service_manager = ServiceManager()

    start = time.time()
    print("Waiting for services...") 
    while len(service_manager) == 0 and (time.time() - start) < timeout:
        time.sleep(0.5)
    
    if len(service_manager) == 0:
        raise Exception("No AI Services were found before timeout. Please try again or make sure services are running.")
    
    client = ZeroconfAIClient(service_manager)
    
    try:
        while True:
            services_list = list(service_manager.items())
            for i, (url, name) in enumerate(services_list, 1):
        
                print(f"{i}. {name} ({url})")
            
            choice = input("\nSelect service (0 to quit): ").strip()
            if choice == "0":
                break

            try:
                choice_idx = int(choice) - 1
                if choice_idx < 0 or choice_idx >= len(services_list):
                    print("Invalid selection. Try again.")
                    continue
                    
                selected_url, selected_name = services_list[choice_idx]
                # VALIDATE ServiceManager's registry before connecting
                if not service_manager.is_service_available(selected_url):
                    print(f"\nService {selected_name} is no longer available. Please select again.")
                    continue

                # validate health beforeconnecting
                if not verify_service_health(selected_url):
                    print(f"\nService {selected_name} at {selected_url} is not healthy. Please select again.")
                    service_manager.remove_service_from_manager(selected_name, selected_url)
                    continue

                client.set_active_service(selected_url)
                print(f"\n Connected to: {selected_name} {selected_url}\n")
                print("Type 'back' to change services, 'clear' to reset chat, or 'quit' to exit\n")
                
                while True:
                    if not client.is_connected:
                        print(f"\nService went offline. Returning to service selection...")
                        break
                    
                    user_input = input("You: ").strip()
                    
                    if user_input.lower() in ['quit', 'exit']:
                        print("Goodbye!")
                        return
                    
                    if user_input.lower() == 'back':
                        print("\nReturning to service selection...")
                        break
                    
                    if user_input.lower() == 'clear':
                        client.clear_history()
                        print("Chat history cleared.\n")
                        continue
                    
                    if not user_input:
                        continue
                    
                    try:
                        response = client.chat(user_input)
                        print(f"Assistant: {response}\n")
                        
                    except RuntimeError as e:
                        print(f"\nError: {e}")
                        
                        # Check if we should return to menu in case of disconnection
                        if not client.is_connected:
                            if len(service_manager) > 1:
                                print("Other services are available. Returning to selection...")
                                break
                            else:
                                print("No other services available. Exiting...")
                                return
                    
                    except Exception as e:
                        print(f"\n Unexpected error: {e}")
                        print("Returning to service selection...")
                        break
                        
            except (ValueError, IndexError):
                print("Invalid input. Please enter a number.")
                continue
                
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    finally:
        print("Closing connections and cleaning up...")
        service_manager.browser.cancel()
        service_manager.zc.close()


if __name__ == "__main__":
    main()

        

        


