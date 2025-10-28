from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
import socket
import time
import requests

class SimpleListener(ServiceListener):
    def __init__(self):
        self.service_url = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if self.service_url is not None:
            return  # Already found a service

        info = zc.get_service_info(type_, name)
        if info:
            address = socket.inet_ntoa(info.addresses[0])
            port = info.port
            self.service_url = f"http://{address}:{port}"


def main():
    zc = Zeroconf()
    listener = SimpleListener()
    browser = ServiceBrowser(zc, "_zeroconfai._tcp.local.", listener)

    print("Searching for ZeroconfAI services...")
    timeout = 10.0  # seconds
    start_time = time.time()
    while listener.service_url is None and (time.time() - start_time) < timeout:
        time.sleep(0.1)
    if listener.service_url is None:
        print("No ZeroconfAI services found.")

    print(f"Connected to service at {listener.service_url}")
    models_response = requests.get(f"{listener.service_url}/v1/models")
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
        response = requests.post(f"{listener.service_url}/v1/chat/completions", json=payload)
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