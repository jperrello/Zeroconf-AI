import time
from zeroconf import ServiceListener, ServiceBrowser, Zeroconf
import requests
import socket
 
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

    def add_service_to_manager(self, name: str, url: str):
        if url in self.services and self.services[url]== name:
            print(f"The service: {name} is already registered at {url}")
            return
        self.services[url] = name
        print(f"added {name} -> {url}")

    def remove_service(self, name: str):
        if name in self.services:
            del self.services[name]
            print(f"Service {name} has been deleted.")
        else:
            print("Service doesn't exist")
    
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
        self.service_manager.remove_service(name)
        
    
#=================================

    
def chat(selected_service: str, user_message: str, chat_history: list) -> tuple:
    if chat_history is None:
        chat_history = []
    elif len(chat_history) > 10:
        chat_history.pop(0)
        

    model: str = 'google/gemini-2.5-flash-lite-preview-09-2025'
    chat_history.append({"role": 'user', "content": user_message})

    payload = {
        "model": model,
        "messages": chat_history,
        "temperature": 0.7,
    }

    response = requests.post(f"{selected_service}/v1/chat/completions", json=payload)

    if response.ok:
        data = response.json()
        assistant_message = data["choices"][0]["message"]["content"]

        chat_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        return assistant_message, chat_history
    else:
        raise Exception(f"AI request failed: {response.status_code} - {response.text}")
    
   

#====================================
def main():
    timeout = 10.0 
    print("Searching for AI on your network...")

    ai_services = ServiceManager() # discovery takes time

    start = time.time()
    print("Waiting for services...") 
    while len(ai_services) == 0 and (time.time() - start) < timeout:
        time.sleep(0.5)
    if len(ai_services) == 0:
        raise Exception("No AI Services were found before  timeout. Please try agian or make sure services are running.")
    
    i = 1
    for url, name in ai_services.items():
        print(f"{i}. Name: {name} URL: {url}")
        i+=1
    choice = int(input("Enter the number of the service you want to connect to: "))
    print("Type 0 to quit")

    try:
        if choice == 0:
            exit()
        else:
            services_list = list(ai_services.items())
            selected_url, selected_name = services_list[(choice) - 1]
            print(f"You have selected {selected_name}")

        chat_history = []

        while True:
            user_input = input('Prompt: ')

            if user_input.lower() in ['quit', 'exit']:
                break

            ai_response = chat(selected_url, user_input, chat_history)

            print(f"Assistant: {ai_response[0]}")
    finally:
        print("Closing connection and cleaning up....")
        ai_services.browser.cancel()
        ai_services.zc.close()

main()

        

        


