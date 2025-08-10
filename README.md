## Stock Prediction System (FastAPI backend + Streamlit frontend + Upstox + OpenAI)

This system provides:
- Upstox OAuth (handled in backend) to fetch historical OHLC and stream realtime LTP
- Streamlit UI with instrument selector, date dragger, interval
- Technical indicators and OpenAI structured-output pipeline for entry/exit suggestions

### Environment
Create `.env` at project root:
```
# Backend
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKEND_URL=http://127.0.0.1:8000

# Upstox
UPSTOX_CLIENT_ID=...
UPSTOX_CLIENT_SECRET=...
UPSTOX_REDIRECT_URI=http://127.0.0.1:8000/auth/callback

# OpenAI
OPENAI_API_KEY=...
```
Set the Upstox app redirect to `http://127.0.0.1:8000/auth/callback`.

### Install
```
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
pip install fastapi uvicorn anyio
```

### Run backend
```
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Run frontend
In another terminal:
```
streamlit run app.py
```

### Usage
1) Open Streamlit, click Login with Upstox (redirect to Upstox, then backend callback sets token).
2) Return to Streamlit, select segment/symbol, drag date range, pick interval.
3) See charts, AI signal. For realtime LTP, connect a WS client to:
```
ws://127.0.0.1:8000/ws/ltp?instrument_key=<KEY>
```

Notes:
- Historical candles use Upstox v3 per docs. Intraday depth subject to Upstox limits.
- Instruments are fetched from the BOD JSON.
- OpenAI uses structured outputs to ensure valid JSON for signals.