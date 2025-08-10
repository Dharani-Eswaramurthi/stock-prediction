import os
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://51.20.120.226:8000")

st.set_page_config(page_title="Stock Predictor • Upstox + OpenAI", layout="wide")

st.title("Stock Prediction System")

# Auth status
try:
    status_res = requests.get(f"{BACKEND_URL}/auth/status", timeout=15)
    if not status_res.ok:
        st.error(f"Backend auth status error: {status_res.status_code} {status_res.text}")
        st.stop()
    status = status_res.json()
except Exception as e:
    st.error(f"Failed to contact backend: {e}")
    st.stop()

if not status.get("authenticated"):
    try:
        auth_res = requests.get(f"{BACKEND_URL}/auth/start", timeout=15)
        if not auth_res.ok:
            st.error(f"Backend auth start error: {auth_res.status_code} {auth_res.text}")
            st.stop()
        auth = auth_res.json()
    except Exception as e:
        st.error(f"Failed to get auth URL: {e}")
        st.stop()
    st.write("Connect your Upstox account to fetch instruments and data.")
    st.link_button("Login with Upstox", auth.get("url", ""))
    st.stop()

def _sanitize_symbol(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


# Instruments and user inputs
with st.sidebar:
    st.header("Instrument Search")
    # Defer fetching instruments to explicit user action via the form button
    df = pd.DataFrame(st.session_state.get('instrument_results', []))

    min_date = date.today() - timedelta(days=365 * 5)
    max_date = date.today()
    try:
        default_start = date(max_date.year - 1, max_date.month, max_date.day)
    except ValueError:
        default_start = (max_date - timedelta(days=365))

    with st.form("query_form"):
        symbol_input = st.text_input("Search symbol or name (e.g., TATAMOTORS, RELIANCE, INFOSYS)", value=st.session_state.get('symbol_query', ''))
        st.session_state['symbol_query'] = symbol_input
        # Buttons to control fetching related stocks
        colq1, colq2 = st.columns([1,1])
        with colq1:
            get_related = st.form_submit_button("Get related stocks")
        with colq2:
            clear_related = st.form_submit_button("Clear")
        if get_related:
            try:
                q = _sanitize_symbol(symbol_input)
                resp = requests.get(f"{BACKEND_URL}/instruments", params={"q": q, "limit": 100}, timeout=30)
                if resp.ok:
                    st.session_state['instrument_results'] = resp.json()
                else:
                    st.warning(f"Search failed: {resp.status_code}")
            except Exception as e:
                st.warning(f"Search error: {e}")
            df = pd.DataFrame(st.session_state.get('instrument_results', []))
        if clear_related:
            st.session_state['instrument_results'] = []
            df = pd.DataFrame()

        # Build dropdown from last fetched results
        selection_options = []
        selection_indices = []
        if not df.empty:
            selection_indices = df.index.tolist()
            def _opt(row):
                nm = str(row.get("name", "")).strip()
                ts = str(row.get("trading_symbol", "")).strip()
                ik = str(row.get("instrument_key", "")).strip()
                disp = f"{ts} — {nm}" if nm else ts
                return f"{disp} [{ik}]"
            selection_options = [_opt(row) for _, row in df.iterrows()]
        dropdown_options = ["-- Get related stocks first --"] + selection_options
        st.selectbox("Select instrument", options=dropdown_options, index=0, key="instrument_select")
        col1, col2 = st.columns(2)
        with col1:
            from_date = st.date_input("From date", value=default_start, min_value=min_date, max_value=max_date)
        with col2:
            to_date = st.date_input("To date", value=max_date, min_value=min_date, max_value=max_date)
        interval = st.selectbox("Interval", ["day", "week", "month", "30minute", "1minute"], index=0)
        submitted = st.form_submit_button("Generate")

    st.header("Realtime Stream")
    do_stream = st.toggle("Stream realtime LTP", value=True)

candles = pd.DataFrame()
selected_symbol = None
selected_instr_key = None

if 'last_query' not in st.session_state:
    st.session_state['last_query'] = None
if 'last_candles' not in st.session_state:
    st.session_state['last_candles'] = pd.DataFrame()

if submitted:
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Recompute matches to map the chosen option back to a row
    user_sym = _sanitize_symbol(symbol_input)
    match = None
    selection_options = []
    selection_indices = []
    matches_df = pd.DataFrame()
    if not df.empty:
        if user_sym:
            sanitized_symbols = df["trading_symbol"].astype(str).map(_sanitize_symbol)
            if "name" in df.columns:
                sanitized_names = df["name"].astype(str).map(_sanitize_symbol)
            else:
                sanitized_names = pd.Series([""] * len(df), index=df.index)
            mask = sanitized_symbols.str.contains(user_sym, na=False) | sanitized_names.str.contains(user_sym, na=False)
            matches_df = df[mask].copy()
        if matches_df.empty:
            candidates = df.copy()
            if "trading_symbol" in candidates.columns:
                candidates = candidates.sort_values("trading_symbol")
            matches_df = candidates.head(50)
        selection_indices = matches_df.index.tolist()
        def _opt(row):
            nm = str(row.get("name", "")).strip()
            ts = str(row.get("trading_symbol", "")).strip()
            ik = str(row.get("instrument_key", "")).strip()
            disp = f"{ts} — {nm}" if nm else ts
            return f"{disp} [{ik}]"
        selection_options = [_opt(row) for _, row in matches_df.iterrows()]

    chosen = st.session_state.get("instrument_select")
    placeholder = "-- Type to search --"
    if not selection_options or chosen == placeholder:
        match = None
    else:
        try:
            pos = selection_options.index(chosen)  # chosen is one of selection_options
            df_idx = selection_indices[pos]
            match = df.loc[df_idx]
        except Exception:
            match = None
    if match is None or (hasattr(match, 'empty') and match.empty):
        st.error("No instrument selected. Type to search and select an option above.")
    else:
        selected_symbol = match["trading_symbol"]
        selected_instr_key = match["instrument_key"]
        selected_name = match.get("name", selected_symbol)
        body = {
            "instrument_key": selected_instr_key,
            "interval": interval,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
        with st.spinner("Fetching historical data..."):
            try:
                candles_http = requests.post(f"{BACKEND_URL}/candles", json=body, timeout=60)
                if not candles_http.ok:
                    st.error(f"Candles error: {candles_http.status_code} {candles_http.text}")
                else:
                    candles_resp = candles_http.json()
                    candles = pd.DataFrame(candles_resp.get("candles", []))
                    st.session_state['last_candles'] = candles
                    st.session_state['last_query'] = {
                        "symbol": selected_symbol,
                        "name": selected_name,
                        "instrument_key": selected_instr_key,
                        "from_date": from_date.isoformat(),
                        "to_date": to_date.isoformat(),
                        "interval": interval,
                    }
            except Exception as e:
                st.error(f"Failed to fetch candles: {e}")

# Display results
candles = st.session_state.get('last_candles', pd.DataFrame())
q = st.session_state.get('last_query')
if candles is None:
    candles = pd.DataFrame()
if not candles.empty and q:
    display_name = q.get('name') or q['symbol']
    st.markdown(f"**Historical analysis: {display_name} ({q['symbol']}) from {q['from_date']} to {q['to_date']} ({q['interval']})**")

# Charts
left, right = st.columns([2, 1])
with left:
    if not candles.empty:
        title = q['symbol'] if q else "Selected"
        st.subheader(f"{title}")
        st.line_chart(candles.set_index("time")["close"], height=350)
with right:
    if not candles.empty:
        st.write("Latest OHLC")
        st.dataframe(candles.tail(5).reset_index(drop=True))

# LLM Signal
signal = None
if not candles.empty and q:
    with st.spinner("Generating AI signal..."):
        sig_body = {
          "instrument_key": q["instrument_key"],
          "symbol": q["symbol"],
          "candles": candles.to_dict(orient="records"),
        }
        try:
            sig_http = requests.post(f"{BACKEND_URL}/signal", json=sig_body, timeout=60)
            if not sig_http.ok:
                st.error(f"Signal error: {sig_http.status_code} {sig_http.text}")
            else:
                signal = sig_http.json()
        except Exception as e:
            st.error(f"Failed to fetch signal: {e}")

if signal:
    st.markdown("**AI Trade Signal**")
    st.json(signal)

# Realtime stream placeholder
if do_stream:
    st.info("Realtime LTP stream is available over backend WebSocket /ws/ltp?instrument_key=... Use a client/browser WS.")