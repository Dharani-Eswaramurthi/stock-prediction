import websocket
import json
import urllib

# Replace these with your actual values
BACKEND_URL = "http://localhost:8000"  # your FastAPI backend
INSTRUMENT_KEY = "BSE_EQ|INE155A01022"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiIzVUMzWFAiLCJqdGkiOiI2OGFmZmQ1ZjI0NDY4MzViOTU3NzViOWUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1NjM2NDEyNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzU2NDE4NDAwfQ.RJxlOFVG2QETZkLOdh4dOkLB5XlkQRIyqSL_cCUhESI"

# Convert HTTP URL to WS/WSS
params = urllib.parse.urlencode({
    "instrument_key": INSTRUMENT_KEY,
    "access_token": ACCESS_TOKEN
})

ws_url = f"ws://localhost:8000/ws/ltp_v3?{params}"
print(ws_url)

def on_message(ws, message):
    try:
        data = json.loads(message)
        print("Received:", json.dumps(data, indent=2))
    except Exception as e:
        print("Parse error:", e)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket closed. Code: {close_status_code}, Message: {close_msg}")

def on_open(ws):
    print("WebSocket opened")

if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.on_open = on_open
    ws.run_forever()
