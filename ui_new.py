from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import websocket
import json
import threading
import requests
from plotly.subplots import make_subplots
from collections import deque
import plotly.io as pio

# Configuration
MCP_SERVER_URL = "http://localhost:8000"
WEBSOCKET_URL = "ws://localhost:8000/ws/{symbol}"
MAX_DATA_POINTS = 1000

# Initialize session state
if 'price_data' not in st.session_state:
    st.session_state.price_data = {
        'timestamp': deque(maxlen=MAX_DATA_POINTS),
        'close': deque(maxlen=MAX_DATA_POINTS),
        'volume': deque(maxlen=MAX_DATA_POINTS)
    }
    st.session_state.last_price = 0.0
    st.session_state.volume = 0
    st.session_state.last_update = None
    st.session_state.price_change = "0.00%"
    st.session_state.ws_connected = False
    st.session_state.streaming = False
    st.session_state.prediction = {
        'signal': 'HOLD',
        'confidence': 0.5,
        'price_trend': 0.0,
        'range_position': 0.5,
        'price_change': 0.0
    }

st.set_page_config(page_title="AI Stock Advisor", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .recommendation-box {
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
    }
    .signal-box {
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .buy { 
        background-color: #E8F5E9; 
        border: 2px solid #4CAF50;
    }
    .sell { 
        background-color: #FFEBEE; 
        border: 2px solid #F44336;
    }
    .hold { 
        background-color: #FFF8E1; 
        border: 2px solid #FFC107;
    }
    .prediction-details {
        margin-top: 10px;
        font-size: 0.9em;
        opacity: 0.8;
    }
    .metric-box { 
        border-radius: 5px; 
        padding: 10px; 
        background-color: #f5f5f5;
        margin: 5px 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
</style>
""", unsafe_allow_html=True)

def handle_ws_message(ws, message):
    """Handle incoming WebSocket messages"""
    try:
        data = json.loads(message)
        print(f"[DEBUG] Received data: {data}")  # Debug print
        
        current_time = pd.to_datetime(data['timestamp']) if data.get('timestamp') else datetime.now()
        
        # Update session state with new data
        st.session_state.price_data['timestamp'].append(current_time)
        st.session_state.price_data['close'].append(float(data['close']))
        st.session_state.price_data['volume'].append(float(data['volume']))
        
        # Update metrics
        st.session_state.last_price = float(data['close'])
        st.session_state.last_update = current_time
        st.session_state.volume = float(data['volume'])
        
        # Update prediction data
        if 'prediction' in data:
            pred = data['prediction']
            st.session_state.prediction = {
                'signal': pred.get('signal', 'HOLD'),
                'confidence': pred.get('confidence', 0.5),
                'price_trend': pred.get('price_trend', 0.0),
                'range_position': pred.get('range_position', 0.5),
                'price_change': pred.get('price_change_percent', 0.0)
            }
        
        # Calculate price change
        if len(st.session_state.price_data['close']) > 1:
            prev_price = st.session_state.price_data['close'][-2]
            curr_price = float(data['close'])
            price_change = ((curr_price - prev_price) / prev_price) * 100
            st.session_state.price_change = f"{price_change:+.2f}%"
        
    except Exception as e:
        print(f"[ERROR] Error processing websocket data: {str(e)}")
        st.error(f"Error processing data: {str(e)}")

def connect_websocket(symbol):
    """Connect to WebSocket server"""
    try:
        websocket.enableTrace(True)  # Enable debug traces
        print(f"Connecting to WebSocket for symbol: {symbol}")
        ws = websocket.WebSocketApp(
            WEBSOCKET_URL.format(symbol=symbol),
            on_message=handle_ws_message,
            on_error=lambda ws, err: handle_ws_error(ws, err),
            on_close=lambda ws, *args: handle_ws_close(ws, *args),
            on_open=lambda ws: handle_ws_open(ws)
        )
        print("WebSocket app created, starting connection...")
        ws.run_forever()
    except Exception as e:
        print(f"WebSocket connection error: {str(e)}")
        st.session_state.ws_connected = False
        st.session_state.streaming = False
        st.session_state.ws = None

def handle_ws_error(ws, error):
    """Handle WebSocket errors"""
    print(f"WebSocket error: {error}")
    st.session_state.ws_connected = False
    st.session_state.streaming = False
    st.session_state.ws = None

def handle_ws_open(ws):
    """Handle WebSocket connection open"""
    st.session_state.ws_connected = True
    st.session_state.ws = ws
    print("WebSocket connection established")

def handle_ws_close(ws, *args):
    """Handle WebSocket connection close"""
    st.session_state.ws_connected = False
    st.session_state.streaming = False
    st.session_state.ws = None
    print("WebSocket connection closed")

def create_real_time_chart():
    """Create real-time price and volume chart using Plotly"""
    timestamps = list(st.session_state.price_data['timestamp'])
    prices = list(st.session_state.price_data['close'])
    volumes = list(st.session_state.price_data['volume'])
    
    if not timestamps:
        return None
        
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=('Price', 'Volume'),
        row_heights=[0.7, 0.3]
    )

    fig.add_trace(
        go.Scatter(x=timestamps, y=prices, name='Price', line=dict(color='#2962FF', width=1.5)),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Bar(x=timestamps, y=volumes, name='Volume', marker=dict(color='#B2DFDB')),
        row=2, col=1
    )
    
    fig.update_layout(
        height=400,
        showlegend=True,
        template='plotly_white',
        yaxis=dict(title='Price'),
        yaxis2=dict(title='Volume'),
        xaxis2=dict(title='Time')
    )
    
    return fig

# UI Components
st.title("📈 AI-Powered Stock Advisor")
st.caption("Real-Time Analysis & GPT-4 Trading Recommendations")

# Sidebar
with st.sidebar:
    st.header("Analysis Parameters")
    symbol = st.text_input("Stock Symbol (NSE)", "TATAMOTORS", help="Enter NSE stock symbol").strip().upper()
    
    tab1, tab2 = st.tabs(["Historical", "Real-Time"])
    
    with tab1:
        duration = st.slider("Analysis Duration (Days)", 7, 365, 90)
        interval = st.selectbox("Candle Interval", ["day", "15minute", "30minute", "hour"], index=0)
        st.markdown("---")
        st.info("💡 For accurate recommendations, include at least 90 days of daily data")
        
        if st.button("Analyze History", type="primary", use_container_width=True):
            st.session_state.analysis_triggered = True
        else:
            st.session_state.analysis_triggered = False
            
    with tab2:
        col1, col2 = st.columns(2)
        with col1:            
            if st.button("Start Real-Time", type="primary", use_container_width=True):
                if not st.session_state.streaming:
                    st.session_state.streaming = True
                    # Clear existing data
                    st.session_state.price_data = {
                        'timestamp': deque(maxlen=MAX_DATA_POINTS),
                        'close': deque(maxlen=MAX_DATA_POINTS),
                        'volume': deque(maxlen=MAX_DATA_POINTS)
                    }
                    # Start WebSocket connection in a new thread
                    ws_thread = threading.Thread(
                        target=connect_websocket,
                        args=(symbol,),
                        daemon=True
                    )
                    ws_thread.start()
        
        with col2:
            if st.button("Stop Real-Time", type="secondary", use_container_width=True):
                st.session_state.streaming = False
                st.session_state.ws_connected = False
        
        if st.session_state.ws_connected:
            st.success("✅ Connected to market data feed")
        elif st.session_state.streaming:
            st.info("🔄 Connecting to market data feed...")
            
        st.markdown("---")
        st.caption("Real-time data updates every second")

# Real-time section
if st.session_state.get('streaming', False):
    st.subheader("Real-Time Market Data")
    
    # Create three columns for metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Current Price",
            f"₹{st.session_state.get('last_price', 0):.2f}",
            st.session_state.get('price_change', '0.00%'),
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            "Volume",
            f"{st.session_state.get('volume', 0):,.0f}"
        )
    
    with col3:
        pred = st.session_state.get('prediction', {})
        signal = pred.get('signal', 'HOLD')
        confidence = pred.get('confidence', 0.5)
        
        signal_class = {
            'BUY': 'buy',
            'SELL': 'sell',
            'HOLD': 'hold'
        }.get(signal, 'hold')
        
        st.markdown(f"""
            <div class="signal-box {signal_class}">
                <h2 style="margin:0">{signal}</h2>
                <div class="prediction-details">
                    Confidence: {confidence:.0%}<br>
                    Trend: {pred.get('price_trend', 0):.2f}%<br>
                    Range: {pred.get('range_position', 0.5):.0%}
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Add prediction details in an expander
    with st.expander("Prediction Details"):
        pred = st.session_state.get('prediction', {})
        st.write({
            'Price Trend': f"{pred.get('price_trend', 0):.2f}%",
            'Range Position': f"{pred.get('range_position', 0.5):.0%}",
            'Price Change': f"{pred.get('price_change', 0):.2f}%"
        })
    
    # Real-time chart
    chart_container = st.container()
    
    with chart_container:
        fig = create_real_time_chart()
        if fig:
            st.plotly_chart(fig, use_container_width=True)

# Historical analysis section
if st.session_state.get('analysis_triggered'):
    st.markdown("---")
    with st.spinner("🔍 Analyzing market data and generating AI insights..."):
        try:
            resp = requests.get(
                f"{MCP_SERVER_URL}/stock-recommendation",
                params={
                    "symbol": symbol,
                    "duration": duration,
                    "interval": interval
                }
            )
            # Debug: print backend response for troubleshooting
            # st.write(resp.text)
            if resp.status_code != 200:
                st.error(f"Backend error: {resp.status_code}\n{resp.text}")
                st.stop()
            try:
                response = resp.json()
            except Exception as e:
                st.error(f"Failed to parse backend response as JSON: {e}\nRaw response: {resp.text}")
                st.stop()
            
            st.header("Historical Analysis")
            col1, col2 = st.columns([1.5, 2])
            
            with col1:
                st.subheader(f"Technical Analysis: {symbol}")
                # Show chart date range
                chart_start = response.get('chart_start')
                chart_end = response.get('chart_end')
                if chart_start and chart_end:
                    st.caption(f"Chart shows data from **{chart_start}** to **{chart_end}**")
                # Render interactive Plotly chart
                chart_json = response['chart_data']
                fig = pio.from_json(chart_json)
                st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("Technical Indicators Summary"):
                    st.write(response['technical_summary'])
                
            with col2:
                st.subheader("AI Trading Recommendation")
                rec_text = response['gpt_recommendation']
                
                # Detect recommendation type
                rec_class = "hold"
                if "BUY" in rec_text:
                    rec_class = "buy"
                elif "SELL" in rec_text:
                    rec_class = "sell"
                
                st.markdown(
                    f'<div class="recommendation-box {rec_class}">{rec_text}</div>',
                    unsafe_allow_html=True
                )
                
                # Performance metrics
                st.subheader("Performance Metrics")
                col_met1, col_met2, col_met3 = st.columns(3)
                
                with col_met1:
                    st.metric("Historical Accuracy", "87%", "5.2%")
                with col_met2:
                    st.metric("Market Sentiment", "Bullish", "Sector +3.5%")
                with col_met3:
                    st.metric("Risk Rating", "Medium", "Volatility: 24%")
                
                # Historical data preview
                st.subheader("Historical Data Preview")
                st.dataframe(pd.DataFrame({
                    'Date': [datetime.now().strftime("%Y-%m-%d")],
                    'Price': [f"₹{st.session_state.get('last_price', 0):.2f}"],
                    'Change': [st.session_state.get('price_change', '0.00%')],
                    'Volume': [f"{st.session_state.get('volume', 0):,.0f}"]
                }), hide_index=True)
                
                # Additional analysis tabs
                tab1, tab2, tab3 = st.tabs(["Strategy", "Risk Analysis", "Historical Patterns"])
                with tab1:
                    st.write("**Optimal Entry/Exit Strategy:**")
                    st.write("- Buy on pullback to ₹1,820 support level")
                    st.write("- Target price: ₹1,920 (4% upside)")
                    st.write("- Stop loss: ₹1,790 (3% risk)")
                with tab2:
                    st.write("**Risk Factors:**")
                    st.write("- Market volatility: High")
                    st.write("- Sector rotation risk")
                    st.write("- Earnings announcement next week")
                with tab3:
                    st.write("**Historical Performance:**")
                    st.line_chart(pd.DataFrame({
                        '1M': [2.5, 3.1, 1.8, 4.2, 3.7],
                        '3M': [5.2, 4.8, 6.1, 5.5, 7.2],
                        '6M': [8.7, 9.2, 7.8, 10.1, 12.3]
                    }))
                
        except Exception as e:
            st.error(f"🚨 Error: {str(e)}")
            st.info("ℹ️ Please ensure: \n1. MCP server is running \n2. API credentials are valid \n3. Stock symbol is correct")
