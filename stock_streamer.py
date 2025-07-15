import websocket
import threading
import time
import upstox_client
from upstox_client.api import websocket_api
from upstox_client.rest import ApiException
import os
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Replace with your actual access token

ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiIzVUMzWFAiLCJqdGkiOiI2ODRmYTZjZDQyNjRkODMyZmM4NDliZGUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1MDA1MDUwOSwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzUwMTExMjAwfQ.BDESEr4vUwopFLlB0vn5XaU0wiFzUC3GSX2KPSyvnbE"

def on_message(ws, message):
    # Here you should decode the protobuf message as per Upstox documentation
    print("Received message:", message)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed:", close_status_code, close_msg)

def on_open(ws):
    print("WebSocket connection opened.")
    # Example subscribe message (refer to Upstox documentation for correct format)
    subscribe_message = {
        "guid": "unique-guid",
        "method": "sub",
        "data": {
            "mode": "full",
            "instrumentKeys": ["NSE_EQ|RELIANCE", "NSE_EQ|TCS"]
        }
    }
    ws.send(json.dumps(subscribe_message))

def get_websocket_url():
    # Configure API client
    configuration = upstox_client.Configuration()
    configuration.access_token = ACCESS_TOKEN
    api_instance = websocket_api.WebsocketApi(upstox_client.ApiClient(configuration))
    try:
        # Get authorized WebSocket URL for v2.0
        api_version = '2.0'
        response = api_instance.get_market_data_feed_authorize(api_version)
        ws_url = response.data.authorized_redirect_uri
        return ws_url
    except ApiException as e:
        print("Exception when calling WebsocketApi->get_market_data_feed_authorize:", e)
        return None

def run_websocket():
    ws_url = get_websocket_url()
    if not ws_url:
        print("Failed to get WebSocket URL.")
        return

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # Run WebSocket in a thread to allow for reconnection logic
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ws.close()

if __name__ == "__main__":
    run_websocket()
