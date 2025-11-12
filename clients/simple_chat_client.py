from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
import socket
import time
import requests
import threading 

class SimpleListener(ServiceListener):
    def __init__(self):
        self.best_service_url = None
        self.best_service_priority = float('inf')
        self.lock = threading.Lock()
        self.service_found = threading.Event()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if not info:
            return

        with self.lock:
            if info.priority < self.best_service_priority:
                address = socket.inet_ntoa(info.addresses[0])
                port = info.port
                self.best_service_url = f"http://{address}:{port}"
                self.best_service_priority = info.priority
                self.service_found.set()


def main():
    zc = Zeroconf()
    listener = SimpleListener()
    browser = ServiceBrowser(zc, "_zeroconfai._tcp.local.", listener)
    

    print("Searching for ZeroconfAI services...") 
    time.sleep(1.5)
    if not listener.service_found.wait(timeout=3.0):
        print("No ZeroconfAI services found.")
        browser.cancel()
        zc.close()  
        return

    print(f"Connected to service at {listener.best_service_url} with priority {listener.best_service_priority}")
    models_response = requests.get(f"{listener.best_service_url}/v1/models")
    model = (models_response.json().get('models', []))[0]['id'] if models_response.ok else None

    chat_history = [] # dont even need this if we want it to be simpler, but that kinda defeats the purpose of a chat client

    print("Chat started. Type 'quit' to quit.")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "quit":
            break
        elif user_input.lower() == "clear":
            chat_history = []
            print("Chat history cleared.")
            continue
        if not user_input:
            continue

        current_message = chat_history + [{"role": "user", "content": user_input}]
        payload = {
            "model": model,
            "messages": current_message
        }
        response = requests.post(f"{listener.best_service_url}/v1/chat/completions", json=payload)
        if response.ok:
            data = response.json()
            assistant_message = data['choices'][0]['message']['content']
            print(f"AI: {assistant_message}")
            chat_history.append({"role": "user", "content": user_input})
            chat_history.append({"role": "assistant", "content": assistant_message})
    browser.cancel()
    zc.close()
    

if __name__ == "__main__":
    main()