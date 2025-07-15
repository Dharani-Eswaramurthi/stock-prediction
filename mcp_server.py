from fastapi import FastAPI, HTTPException
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Union, Tuple, Set
import pandas as pd
import numpy as np
import openai
import os
import io
import matplotlib.pyplot as plt
import mplfinance as mpf
import json
import base64
import upstox_client
import ssl
import websockets
from google.protobuf.json_format import MessageToDict
from dotenv import load_dotenv
from upstox_client.rest import ApiException
from scipy import stats
import yfinance as yf
import time
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
import MarketDataFeed_pb2 as pb
from collections import defaultdict
import plotly.graph_objects as go

app = FastAPI()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = defaultdict(list)
        self.market_data_connection = None
        self.subscribed_symbols = set()
        self.running = False    
    async def connect(self, websocket: WebSocket, symbol: str):
        await websocket.accept()
        self.active_connections[symbol].append(websocket)
        
        # Start market data processing if not running
        if not self.running:
            asyncio.create_task(self.process_market_data())
            
        # Subscribe to symbol if needed
        if symbol not in self.subscribed_symbols:
            try:
                await self.subscribe_symbol(symbol)
            except Exception as e:
                print(f"[ERROR] Failed to subscribe to symbol {symbol}: {str(e)}")
                await websocket.close(code=1011, reason="Failed to subscribe to market data")    
    def disconnect(self, websocket: WebSocket, symbol: str):
        if symbol in self.active_connections:
            self.active_connections[symbol].remove(websocket)
            if not self.active_connections[symbol]:
                self.subscribed_symbols.remove(symbol)
                del self.active_connections[symbol]
                
        # If no more active connections for any symbol, cleanup market data connection
        active_symbols = sum(len(conns) for conns in self.active_connections.values())
        if active_symbols == 0:
            print("[INFO] No active connections remaining, cleaning up market data connection")
            self.running = False
            if self.market_data_connection:
                asyncio.create_task(self.cleanup_market_data_connection())
    async def subscribe_symbol(self, symbol: str):
        if not self.market_data_connection:
            self.market_data_connection = await create_market_data_connection()
        
        # Use correct instrument key format
        instrument_key = f"NSE_INDEX|{symbol}" if "NIFTY" in symbol.upper() else f"NSE_EQ|{symbol}"
        
        subscribe_data = {
            "guid": "stream_" + symbol,
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": [instrument_key]
            }
        }
        print(f"[DEBUG] Subscribing to: {instrument_key}")
        await self.market_data_connection.send(json.dumps(subscribe_data).encode('utf-8'))
        self.subscribed_symbols.add(symbol)

    async def broadcast(self, symbol: str, message: str):
        if symbol in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[symbol]:
                try:
                    await connection.send_text(message)
                except WebSocketDisconnect:
                    dead_connections.append(connection)
            
            # Clean up dead connections
            for dead in dead_connections:
                self.disconnect(dead, symbol)      
    async def process_market_data(self):
        self.running = True
        reconnect_delay = 1  # Start with 1 second delay
        max_reconnect_delay = 30  # Maximum delay between reconnection attempts
        
        while self.running:
            try:
                if not self.market_data_connection:
                    print("[INFO] No market data connection. Attempting to reconnect...")
                    self.market_data_connection = await create_market_data_connection()
                    # Resubscribe to all symbols
                    for symbol in self.subscribed_symbols:
                        await self.subscribe_symbol(symbol)
                    reconnect_delay = 1  # Reset delay after successful connection
                
                message = await self.market_data_connection.recv()
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)
                print(f"[DEBUG] Received data: {json.dumps(data_dict)}")  # Debug print
                
                # Process feeds data
                feeds = data_dict.get('feeds', {})
                for symbol_key, feed_data in feeds.items():
                    # Extract symbol from instrument key
                    symbol = symbol_key.split('|')[1]
                    if symbol in self.subscribed_symbols:
                        try:
                            # Extract data from feeds structure
                            ff = feed_data.get('ff', {}).get('indexFF', {})
                            ltpc = ff.get('ltp', {})
                            ohlc = ff.get('marketOHLC', {}).get('ohlc', [{}])[0]
                            
                            formatted_data = {
                                'timestamp': data_dict.get('currentTs', ''),
                                'close': ltpc.get('ltp', 0),
                                'volume': feed_data.get('volumeTraded', 0),
                                'high': ohlc.get('high', 0),
                                'low': ohlc.get('low', 0),
                                'open': ohlc.get('open', 0),
                            }
                            
                            # Generate prediction
                            try:
                                formatted_data['prediction'] = await generate_realtime_prediction(formatted_data)
                            except Exception as e:
                                print(f"[ERROR] Failed to generate prediction: {str(e)}")
                                formatted_data['prediction'] = {
                                    'signal': 'HOLD',
                                    'confidence': 0.5,
                                    'price_trend': 0.0,
                                    'volume_ratio': 1.0
                                }
                            
                            print(f"[DEBUG] Broadcasting for {symbol}: {formatted_data}")
                            await self.broadcast(symbol, json.dumps(formatted_data))
                            
                        except Exception as e:
                            print(f"[ERROR] Failed to process feed for {symbol}: {str(e)}")
            except websockets.ConnectionClosed as e:
                print(f"[INFO] WebSocket connection closed: {str(e)}")
                self.market_data_connection = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff
                
            except Exception as e:
                print(f"[ERROR] Market data processing failed: {str(e)}")
                self.market_data_connection = None
                await asyncio.sleep(reconnect_delay)  # Prevent tight loop on error
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

manager = ConnectionManager()

# Load environment variables from .env file
load_dotenv()

# Load environment variables
openai.api_key = os.getenv("OPENAI_API_KEY")
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

# Initialize Upstox client
api_instance = upstox_client.HistoryApi()
API_VERSION = '2.0'

def get_access_token():
    """Refresh access token if needed (implement token refresh logic here)"""
    return UPSTOX_ACCESS_TOKEN

def get_market_data_feed_authorize(api_version, configuration):
    """Get authorization for market data feed."""
    api_instance = upstox_client.WebsocketApi(
        upstox_client.ApiClient(configuration))
    api_response = api_instance.get_market_data_feed_authorize(api_version)
    return api_response

def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

async def create_market_data_connection():
    """Create and return a WebSocket connection for market data."""
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        configuration = upstox_client.Configuration()
        configuration.access_token = get_access_token()
        
        response = get_market_data_feed_authorize(API_VERSION, configuration)
        if not response or not response.data or not response.data.authorized_redirect_uri:
            raise Exception("Failed to get market data feed authorization")
            
        websocket = await websockets.connect(
            response.data.authorized_redirect_uri,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10
        )
        
        await asyncio.sleep(1)  # Wait for connection to establish
        print("[INFO] Market data WebSocket connection established")
        return websocket
        
    except Exception as e:
        print(f"[ERROR] Failed to create market data connection: {str(e)}")
        raise

def get_historical_data(symbol: str, interval: str = 'day', duration: int = 30) -> pd.DataFrame:
    """Fetch historical candle data from Upstox API using upstox-client"""
    try:
        print(f"[DEBUG] Fetching historical data for symbol: {symbol}, interval: {interval}, duration: {duration}")
        
        # Calculate date range
        to_date = datetime.now().date()
        from_date = (to_date - timedelta(days=duration))
        print(f"[DEBUG] Date range: {from_date.isoformat()} to {to_date.isoformat()}")
        
        # Get instrument key from local CSV
        print(f"[DEBUG] Looking up instrument key for {symbol} in local CSV")
        try:
            instruments_df = pd.read_csv('complete.csv')
            instrument_data = instruments_df[instruments_df['tradingsymbol'] == symbol]
            
            if instrument_data.empty:
                print(f"[ERROR] Instrument {symbol} not found in CSV")
                raise ValueError(f"Instrument {symbol} not found")
            
            instrument_key = instrument_data.iloc[0]['instrument_key']
            print(f"[DEBUG] Found instrument key in CSV: {instrument_key}")
            
        except Exception as e:
            print(f"[ERROR] Failed to read instrument data from CSV: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to read instrument data: {str(e)}")
        
        # Get historical data using upstox-client
        print(f"[DEBUG] Requesting historical candle data")
        try:
            api_response = api_instance.get_historical_candle_data1(
                instrument_key, 
                interval, 
                to_date.isoformat(), 
                from_date.isoformat(), 
                API_VERSION
            )
            print("[DEBUG] Successfully retrieved historical data")
            
            if not api_response.data or not api_response.data.candles:
                print(f"[ERROR] No historical data found in response")
                raise ValueError("No historical data found")
              # Process candles
            candles = api_response.data.candles
            print(f"[DEBUG] Retrieved {len(candles)} candles")
            df = pd.DataFrame(candles, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'
            ])
            # Convert timestamps to UTC and make them timezone-naive
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
            return df.set_index('timestamp')
            
        except ApiException as e:
            print(f"[ERROR] Upstox API Exception: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Upstox API error: {str(e)}")
            
    except Exception as e:
        print(f"[ERROR] Failed to fetch historical data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching historical data: {str(e)}")

def generate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to dataframe"""
    print(f"[DEBUG] Generating technical indicators for {len(df)} data points")
    
    # Existing indicators
    print("[DEBUG] Calculating moving averages")
    df['SMA_20'] = df['close'].rolling(window=20).mean()
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    
    print("[DEBUG] Calculating RSI")
    df['RSI'] = compute_rsi(df['close'])
    
    print("[DEBUG] Calculating MACD")
    df['MACD'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    
    # Additional indicators
    print("[DEBUG] Calculating additional indicators")
    df['EMA_12'] = df['close'].ewm(span=12).mean()
    df['EMA_26'] = df['close'].ewm(span=26).mean()
    df['Bollinger_Upper'] = df['SMA_20'] + (2 * df['close'].rolling(window=20).std())
    df['Bollinger_Lower'] = df['SMA_20'] - (2 * df['close'].rolling(window=20).std())
    
    df_cleaned = df.dropna()
    print(f"[DEBUG] Generated indicators. Final dataframe shape: {df_cleaned.shape}")
    return df_cleaned

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def generate_gpt_recommendation(df: pd.DataFrame, symbol: str, duration: int) -> dict:
    """Get trading recommendation from GPT model with enhanced analysis"""
    print(f"[DEBUG] Generating enhanced GPT recommendation for {symbol}")
    latest = df.iloc[-1]
    current_time = datetime.now()
      # Get advanced analysis with pattern learning
    pattern_stats = analyze_pattern_success_rate(df)
    strategy = calculate_optimal_strategy(df)
    market_regime = identify_market_regime(df)
    
    # Get current patterns and their predicted success
    current_patterns = identify_candlestick_patterns(df)
    pattern_predictions = predict_pattern_success(pattern_stats, market_regime)
    
    summary = f"""
    Comprehensive Technical Analysis for {symbol} 
    Analysis Date/Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    Historical Data Period: Last {duration} days
    
    MARKET REGIME ANALYSIS:
    - Market Type: {market_regime['type'].title()}
    - Volatility State: {market_regime['volatility_state'].title()}
    - Volume Profile: {market_regime['volume_profile'].title()}
    - Trend Strength: {market_regime['trend_strength']:.2f}

    CURRENT MARKET STATUS:
    - Current Price: ₹{latest['close']:.2f}
    - Trend Phase: {strategy['trend_phase']}
    - Trend Strength (ADX): {strategy['trend_strength']:.2f} ({'Strong' if strategy['trend_strength'] > 25 else 'Weak'} trend)
    - Market Volatility (ATR): {strategy['volatility']:.2f}
    
    TECHNICAL INDICATORS:
    - 20-Day SMA: ₹{latest['SMA_20']:.2f} ({'Above' if latest['close'] > latest['SMA_20'] else 'Below'} price)
    - 50-Day SMA: ₹{latest['SMA_50']:.2f} ({'Bullish' if latest['SMA_20'] > latest['SMA_50'] else 'Bearish'} crossover)
    - RSI: {latest['RSI']:.2f} ({'Overbought' if latest['RSI'] > 70 else 'Oversold' if latest['RSI'] < 30 else 'Neutral'})
    - MACD: {latest['MACD']:.4f} ({'Bullish' if latest['MACD'] > latest['Signal'] else 'Bearish'} divergence)
    - Volume: {latest['volume']:,} ({'Increasing' if df['volume'][-1] > df['volume'][-5:-1].mean() else 'Decreasing'})
    - Bollinger Bands: Price is {'above upper band' if latest['close'] > latest['Bollinger_Upper'] 
                              else 'below lower band' if latest['close'] < latest['Bollinger_Lower'] 
                              else 'within bands'}
      PATTERN ANALYSIS AND PREDICTIONS:
    Current Patterns:
    {chr(10).join([f"- {k.replace('_', ' ').title()}: Found on {v['date'].strftime('%Y-%m-%d')}" for k, v in current_patterns.items()])}
    
    Historical Pattern Performance:
    {chr(10).join([f"- {k.replace('_', ' ').title()}: Success Rate: {v['base_success_rate']*100:.1f}%, Risk/Reward: {v['historical_risk_reward']:.2f}" 
                   for k, v in pattern_predictions.items() if v])}
    
    Pattern Success Predictions:
    {chr(10).join([f"- {k.replace('_', ' ').title()}: {v['adjusted_probability']*100:.1f}% probability (Confidence: {v['confidence']:.2f})" 
                   for k, v in pattern_predictions.items() if v])}
    
    OPTIMAL TRADING LEVELS:
    - Recommended Entry Zone: ₹{strategy['optimal_entry']:.2f}
    - Target Exit Zone: ₹{strategy['optimal_exit']:.2f}
    - Risk/Reward Ratio: {strategy['risk_reward_ratio']:.2f}
    """
    print("[DEBUG] Generated technical summary")
    
    prompt = f"""
    As a senior quantitative analyst with CFA certification and expertise in algorithmic trading, provide a comprehensive trading recommendation based on:
    {summary}
    
    Consider all provided metrics including:
    1. Current market phase and strength
    2. Pattern formations and their significance
    3. Optimal entry/exit points
    4. Risk-reward metrics
    5. Market volatility conditions
    6. Volume analysis
    7. Technical indicator convergence/divergence
    
    Provide a detailed structured response with:
    - **Primary Recommendation**: BUY/SELL/HOLD with specific timing (e.g., "BUY at market open" or "SELL within 2 trading days")
    - **Trade Type**: Day Trade/Swing Trade/Position Trade
    - **Confidence Level**: High/Medium/Low with probability percentage
    - **Time Horizon**: Specific dates or time periods for entry and exit
    - **Entry Strategy**:
      * Ideal entry price range
      * Alternative entry points
      * Market conditions that must be met
    - **Exit Strategy**:
      * Primary price target
      * Secondary price target
      * Stop loss with trailing adjustment strategy
    - **Risk Management**:
      * Position size recommendation
      * Risk per trade percentage
      * Volatility-based stop loss
    - **Technical Rationale**: 
      * Pattern-based analysis
      * Indicator convergence/divergence
      * Volume analysis
      * Trend strength assessment
    - **Market Context**:
      * Current market phase
      * Volatility condition
      * Related market impacts
    """
    
    try:
        print("[DEBUG] Sending request to GPT model")
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are an expert quantitative analyst. Provide precise, technical recommendations with clear risk management guidance."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=350
        )
        print("[DEBUG] Received GPT response successfully")
        return {
            "recommendation": response.choices[0].message.content,
            "technical_summary": summary
        }
    except Exception as e:
        print(f"[ERROR] GPT API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"GPT API error: {str(e)}")

def plot_candlestick(df: pd.DataFrame, symbol: str):
    """Generate candlestick chart with technical indicators"""
    print(f"[DEBUG] Generating candlestick chart for {symbol}")
    try:
        # Create plot
        plt.figure(figsize=(12, 8))
        print("[DEBUG] Setting up plot indicators")
        apds = [
            mpf.make_addplot(df['SMA_20'], color='blue'),
            mpf.make_addplot(df['SMA_50'], color='orange'),
            mpf.make_addplot(df['Bollinger_Upper'], color='gray', linestyle='--'),
            mpf.make_addplot(df['Bollinger_Lower'], color='gray', linestyle='--'),
            mpf.make_addplot(df['RSI'], panel=1, color='purple', ylabel='RSI'),
            mpf.make_addplot([70]*len(df), panel=1, color='red', linestyle='--', alpha=0.3),
            mpf.make_addplot([30]*len(df), panel=1, color='green', linestyle='--', alpha=0.3),
            mpf.make_addplot(df[['MACD', 'Signal']], panel=2, ylabel='MACD')
        ]
        
        print("[DEBUG] Creating chart")
        # Plot configuration
        style = mpf.make_marketcolors(
            up='#2E7D32',
            down='#D32F2F',
            wick={'up':'#2E7D32', 'down':'#D32F2F'},
            edge={'up':'#2E7D32', 'down':'#D32F2F'},
            volume='in'
        )
        
        mpf_style = mpf.make_mpf_style(
            marketcolors=style,
            gridstyle=':',
            y_on_right=False
        )
        
        fig, axes = mpf.plot(
            df,
            type='candle',
            style=mpf_style,
            title=f'\n{symbol} Technical Analysis',
            addplot=apds,
            volume=True,
            figratio=(12,8),
            panel_ratios=(6,2,2),
            returnfig=True
        )
        
        print("[DEBUG] Converting chart to base64")
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        print("[DEBUG] Chart generation complete")
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"[ERROR] Failed to generate chart: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chart generation error: {str(e)}")

def plot_candlestick_interactive(df: pd.DataFrame, symbol: str):
    """Generate interactive candlestick chart with technical indicators using Plotly"""
    try:
        fig = go.Figure()
        
        # Candlestick chart
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Candlestick'
        ))
        
        # Moving averages
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['SMA_20'],
            mode='lines',
            name='SMA 20',
            line=dict(color='blue', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['SMA_50'],
            mode='lines',
            name='SMA 50',
            line=dict(color='orange', width=2)
        ))
        
        # Bollinger Bands
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['Bollinger_Upper'],
            mode='lines',
            name='Bollinger Upper',
            line=dict(color='gray', width=1, dash='dash')
        ))
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['Bollinger_Lower'],
            mode='lines',
            name='Bollinger Lower',
            line=dict(color='gray', width=1, dash='dash')
        ))
        
        # RSI
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['RSI'],
            mode='lines',
            name='RSI',
            line=dict(color='purple', width=2)
        ))
        fig.add_hline(y=70, line_color='red', line_dash="dash", annotation_text="Overbought", annotation_position="bottom right")
        fig.add_hline(y=30, line_color='green', line_dash="dash", annotation_text="Oversold", annotation_position="top right")
        
        # MACD
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['MACD'],
            mode='lines',
            name='MACD',
            line=dict(color='green', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df['Signal'],
            mode='lines',
            name='Signal',
            line=dict(color='red', width=2)
        ))
        
        # Layout adjustments
        fig.update_layout(
            title=f"{symbol} Technical Analysis",
            xaxis_title="Date",
            yaxis_title="Price",
            legend_title="Indicators",
            template="plotly_dark",
            height=800
        )
        
        return fig.to_json()
    except Exception as e:
        print(f"[ERROR] Failed to generate interactive chart: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chart generation error: {str(e)}")

def identify_candlestick_patterns(df: pd.DataFrame) -> dict:
    """Identify candlestick patterns in the data"""
    patterns = {}
    
    try:
        # Calculate candlestick body and shadows
        df = df.copy()  # Create a copy to avoid modifying original
        df['body'] = df['close'] - df['open']
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        
        # Doji pattern (body is very small relative to shadows)
        doji_mask = (abs(df['body']) <= 0.1 * (df['high'] - df['low']))
        if doji_mask.any():
            last_doji = df.index[doji_mask][-1]
            patterns['doji'] = {
                'date': last_doji,
                'significance': 'Indecision in market',
                'mask': doji_mask
            }
        
        # Hammer pattern (long lower shadow, small upper shadow)
        hammer_mask = (df['lower_shadow'] > 2 * abs(df['body'])) & (df['upper_shadow'] < abs(df['body']))
        if hammer_mask.any():
            last_hammer = df.index[hammer_mask][-1]
            patterns['hammer'] = {
                'date': last_hammer,
                'significance': 'Potential reversal from downtrend',
                'mask': hammer_mask
            }
        
        # Engulfing patterns
        for i in range(1, len(df)):
            curr, prev = df.iloc[i], df.iloc[i-1]
            # Bullish engulfing
            if (curr['body'] > 0 and prev['body'] < 0 and 
                curr['close'] > prev['open'] and curr['open'] < prev['close']):
                patterns['bullish_engulfing'] = {
                    'date': df.index[i],
                    'significance': 'Strong bullish reversal signal',
                    'mask': df.index == df.index[i]
                }
            # Bearish engulfing
            elif (curr['body'] < 0 and prev['body'] > 0 and 
                  curr['close'] < prev['open'] and curr['open'] > prev['close']):
                patterns['bearish_engulfing'] = {
                    'date': df.index[i],
                    'significance': 'Strong bearish reversal signal',
                    'mask': df.index == df.index[i]
                }
        
        return patterns
        
    except Exception as e:
        print(f"[ERROR] Failed to identify candlestick patterns: {str(e)}")
        return {}

def calculate_optimal_strategy(df: pd.DataFrame) -> dict:
    """Calculate optimal entry/exit points based on technical indicators"""
    strategy = {}
    
    # Calculate trend strength
    df['ADX'] = calculate_adx(df)
    latest_adx = df['ADX'].iloc[-1]
    
    # Calculate volatility
    df['ATR'] = calculate_atr(df)
    current_atr = df['ATR'].iloc[-1]
    
    # Calculate support and resistance
    support, resistance = calculate_support_resistance(df)
    
    # Determine trend phase
    if df['SMA_20'].iloc[-1] > df['SMA_50'].iloc[-1]:
        trend = 'Uptrend'
        entry_zone = support
        exit_zone = resistance
    else:
        trend = 'Downtrend'
        entry_zone = resistance
        exit_zone = support
    
    # Calculate risk metrics
    risk_reward = abs(exit_zone - df['close'].iloc[-1]) / abs(df['close'].iloc[-1] - entry_zone)
    
    strategy.update({
        'trend_strength': latest_adx,
        'volatility': current_atr,
        'optimal_entry': entry_zone,
        'optimal_exit': exit_zone,
        'risk_reward_ratio': risk_reward,
        'trend_phase': trend
    })
    
    return strategy

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate the Average Directional Index (ADX) for trend strength measurement
    """
    # Calculate True Range (TR)
    df['TR'] = np.maximum(
        np.maximum(
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift(1))
        ),
        abs(df['low'] - df['close'].shift(1))
    )
    
    # Calculate Directional Movement
    df['DMplus'] = np.where(
        (df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
        np.maximum(df['high'] - df['high'].shift(1), 0),
        0
    )
    df['DMminus'] = np.where(
        (df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
        np.maximum(df['low'].shift(1) - df['low'], 0),
        0
    )
    
    # Calculate Smoothed Averages
    df['TR_smoothed'] = df['TR'].rolling(period).mean()
    df['DMplus_smoothed'] = df['DMplus'].rolling(period).mean()
    df['DMminus_smoothed'] = df['DMminus'].rolling(period).mean()
    
    # Calculate DI
    df['DIplus'] = 100 * df['DMplus_smoothed'] / df['TR_smoothed']
    df['DIminus'] = 100 * df['DMminus_smoothed'] / df['TR_smoothed']
    
    # Calculate DX and ADX
    df['DX'] = 100 * abs(df['DIplus'] - df['DIminus']) / (df['DIplus'] + df['DIminus'])
    adx = df['DX'].rolling(period).mean()
    
    # Clean up intermediate columns
    df.drop(['TR', 'DMplus', 'DMminus', 'TR_smoothed', 'DMplus_smoothed',
             'DMminus_smoothed', 'DIplus', 'DIminus', 'DX'], axis=1, inplace=True)
    
    return adx

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)"""
    tr = pd.DataFrame({
        'high_low': df['high'] - df['low'],
        'high_close': abs(df['high'] - df['close'].shift()),
        'low_close': abs(df['low'] - df['close'].shift())
    }).max(axis=1)
    
    return tr.rolling(window=period).mean()

def calculate_support_resistance(df: pd.DataFrame) -> tuple:
    """Calculate support and resistance levels using pivot points"""
    pivot = (df['high'].iloc[-1] + df['low'].iloc[-1] + df['close'].iloc[-1]) / 3
    support = 2 * pivot - df['high'].iloc[-1]
    resistance = 2 * pivot - df['low'].iloc[-1]
    
    return support, resistance

@app.get("/stock-recommendation")
async def get_stock_recommendation(
    symbol: str,
    duration: Optional[int] = 90,
    interval: str = 'day'
):
    """Endpoint for stock analysis and recommendations"""
    print(f"[DEBUG] Received request for {symbol}, duration={duration}, interval={interval}")
    try:
        # Fetch and process data
        print("[DEBUG] Fetching historical data")
        df = get_historical_data(symbol, interval, duration)
        df = generate_technical_indicators(df)
        recommendation = generate_gpt_recommendation(df, symbol, duration)
        # Use interactive chart
        chart_data = plot_candlestick_interactive(df, symbol)
        chart_start = df.index[0].strftime("%Y-%m-%d")
        chart_end = df.index[-1].strftime("%Y-%m-%d")
        print("[DEBUG] Request completed successfully")
        return {
            "symbol": symbol,
            "duration_days": duration,
            "technical_summary": recommendation['technical_summary'],
            "gpt_recommendation": recommendation['recommendation'],
            "chart_data": chart_data,
            "chart_start": chart_start,
            "chart_end": chart_end
        }
    except Exception as e:
        print(f"[ERROR] Request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def analyze_pattern_success_rate(df: pd.DataFrame, pattern_window: int = 20, future_windows: list = [1, 3, 5, 10]) -> dict:
    """Analyze historical price patterns and their predictive power using advanced pattern detection"""
    if df is None or df.empty or len(df) < pattern_window:
        print("[DEBUG] Insufficient data for pattern analysis")
        return {}
        
    pattern_stats = {}
    
    try:
        # Create a copy to avoid modifying the original dataframe
        analysis_df = df.copy()
        
        # Calculate advanced price action features
        analysis_df['body'] = analysis_df['close'] - analysis_df['open']
        analysis_df['high_low_range'] = analysis_df['high'] - analysis_df['low']
        
        # Handle zero ranges to avoid division by zero
        analysis_df.loc[analysis_df['high_low_range'] == 0, 'high_low_range'] = np.nan
        
        # Calculate shadows
        analysis_df['max_price'] = analysis_df[['open', 'close']].max(axis=1)
        analysis_df['min_price'] = analysis_df[['open', 'close']].min(axis=1)
        analysis_df['upper_shadow'] = analysis_df['high'] - analysis_df['max_price']
        analysis_df['lower_shadow'] = analysis_df['min_price'] - analysis_df['low']
        
        # Calculate ratios with safe divisions
        analysis_df['body_ratio'] = analysis_df['body'].div(analysis_df['high_low_range']).fillna(0)
        analysis_df['upper_shadow_ratio'] = analysis_df['upper_shadow'].div(analysis_df['high_low_range']).fillna(0)
        analysis_df['lower_shadow_ratio'] = analysis_df['lower_shadow'].div(analysis_df['high_low_range']).fillna(0)
        
        # Price velocity and acceleration metrics
        analysis_df['price_velocity'] = analysis_df['close'].diff()
        analysis_df['prev_close'] = analysis_df['close'].shift(1)
        analysis_df['range_ratio'] = analysis_df['high_low_range'].div(analysis_df['prev_close']).fillna(0)
        analysis_df['volume_trend'] = analysis_df['volume'].diff()
        analysis_df['volume_price_trend'] = analysis_df['volume_trend'] * analysis_df['price_velocity']
        
        # Fill NaN values for computed columns
        columns_to_fill = [
            'body_ratio', 'upper_shadow_ratio', 'lower_shadow_ratio',
            'price_velocity', 'range_ratio', 'volume_trend', 'volume_price_trend'
        ]
        analysis_df[columns_to_fill] = analysis_df[columns_to_fill].fillna(0)
        
        # Calculate future returns for each window
        for window in future_windows:
            try:
                future_close = analysis_df['close'].shift(-window)
                current_close = analysis_df['close']
                future_returns = (future_close / current_close - 1)
                analysis_df[f'future_return_{window}d'] = future_returns.ffill().fillna(0)
            except Exception as e:
                print(f"[WARNING] Failed to calculate {window}-day future returns: {str(e)}")
                analysis_df[f'future_return_{window}d'] = 0
        
        # Trend indicator using EMA crossover
        ema_20 = analysis_df['close'].ewm(span=20, adjust=False).mean()
        analysis_df['trend'] = np.where(analysis_df['close'] > ema_20, 1, -1)
        
        # Volatility calculation
        analysis_df['volatility'] = analysis_df['close'].rolling(
            window=20, min_periods=5
        ).std().bfill().fillna(0)
        
        # Generate pattern statistics
        pattern_stats = {
            'data_points': len(analysis_df),
            'avg_volatility': float(analysis_df['volatility'].mean()),
            'trend_direction': 'upward' if analysis_df['trend'].mean() > 0 else 'downward',
            'avg_range_ratio': float(analysis_df['range_ratio'].mean()),
            'success_rates': {}
        }
        
        # Calculate success rates for different time windows
        for window in future_windows:
            returns = analysis_df[f'future_return_{window}d'].dropna()
            if len(returns) > 0:
                pattern_stats['success_rates'][f'{window}d'] = {
                    'positive_return_rate': float((returns > 0).mean()),
                    'avg_return': float(returns.mean()),
                    'sample_size': len(returns)
                }
        
        return pattern_stats
        
    except Exception as e:
        print(f"[ERROR] Pattern analysis failed: {str(e)}")
        return {}

def detect_dynamic_patterns(df: pd.DataFrame, window: int = 20) -> dict:
    """Detect price patterns dynamically using statistical analysis"""
    patterns = {}
    
    if len(df) < window:
        return patterns  # Return empty if not enough data
    
    try:
        # Price action clustering for pattern detection
        features = pd.DataFrame({
            'body_ratio': df['body_ratio'],
            'upper_shadow_ratio': df['upper_shadow_ratio'],
            'lower_shadow_ratio': df['lower_shadow_ratio'],
            'range_ratio': df['range_ratio'],
            'volume_trend': df['volume_trend'],
            'price_velocity': df['price_velocity']
        })
        
        # Normalize features
        features = features.fillna(0)  # Handle NaN values
        features = (features - features.mean()) / features.std().replace(0, 1)  # Avoid division by zero
        
        # Rolling window pattern detection
        for i in range(window, len(df)):
            window_data = features.iloc[i-window:i]
            
            # Detect basic patterns
            patterns.update(detect_basic_patterns(df.iloc[i-window:i]))
            
            # Detect trend reversals
            reversal_score = detect_reversal_pattern(window_data)
            if abs(reversal_score) > 0.7:  # Strong reversal signal
                pattern_date = df.index[i]
                pattern_type = 'bullish_reversal' if reversal_score > 0 else 'bearish_reversal'
                patterns[pattern_type] = {
                    'date': pattern_date,
                    'score': abs(reversal_score),
                    'significance': f"{'Bullish' if reversal_score > 0 else 'Bearish'} reversal pattern",
                    'mask': df.index == pattern_date
                }
        
        return patterns
        
    except Exception as e:
        print(f"[ERROR] Pattern detection failed: {str(e)}")
        return {}

def detect_reversal_pattern(window_data: pd.DataFrame) -> float:
    """Detect trend reversal patterns using statistical analysis"""
    try:
        # Calculate trend metrics
        price_momentum = window_data['price_velocity'].mean()
        volume_momentum = window_data['volume_trend'].mean()
        
        # Combine signals into a reversal score
        reversal_score = -np.sign(price_momentum) * (
            abs(window_data['body_ratio'].mean()) * 0.3 +
            abs(volume_momentum / volume_momentum.std()) * 0.3 +
            window_data['price_velocity'].autocorr() * -0.4
        )
        
        return float(reversal_score)
        
    except Exception as e:
        print(f"[ERROR] Reversal detection failed: {str(e)}")
        return 0.0

def detect_basic_patterns(df: pd.DataFrame) -> dict:
    """Detect basic candlestick patterns"""
    patterns = {}
    
    try:
        latest_idx = df.index[-1]
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None
        
        # Doji pattern
        if abs(latest['body_ratio']) < 0.1:
            patterns['doji'] = {
                'date': latest_idx,
                'score': 1.0 - abs(latest['body_ratio']),
                'significance': 'Market indecision',
                'mask': df.index == latest_idx
            }
            
        if prev is not None:
            # Engulfing patterns
            if (latest['body'] > 0 and prev['body'] < 0 and 
                latest['close'] > prev['open'] and latest['open'] < prev['close']):
                patterns['bullish_engulfing'] = {
                    'date': latest_idx,
                    'score': abs(latest['body']) / (prev['high'] - prev['low']),
                    'significance': 'Strong bullish reversal',
                    'mask': df.index == latest_idx
                }
            elif (latest['body'] < 0 and prev['body'] > 0 and 
                  latest['close'] < prev['open'] and latest['open'] > prev['close']):
                patterns['bearish_engulfing'] = {
                    'date': latest_idx,
                    'score': abs(latest['body']) / (prev['high'] - prev['low']),
                    'significance': 'Strong bearish reversal',
                    'mask': df.index == latest_idx
                }
        
        return patterns
        
    except Exception as e:
        print(f"[ERROR] Basic pattern detection failed: {str(e)}")
        return {}

def identify_market_regime(df: pd.DataFrame) -> dict:
    """Identify the current market regime based on price action and volatility"""
    try:
        # Calculate key metrics
        returns = df['close'].pct_change()
        volatility = returns.rolling(window=20).std() * np.sqrt(252)  # Annualized volatility
        volume_sma = df['volume'].rolling(window=20).mean()
        
        # Get latest values
        current_volatility = volatility.iloc[-1]
        avg_volatility = volatility.mean()
        current_volume = df['volume'].iloc[-1]
        avg_volume = volume_sma.iloc[-1]
        
        # Determine market type based on moving averages
        sma_20 = df['close'].rolling(window=20).mean()
        sma_50 = df['close'].rolling(window=50).mean()
        
        if sma_20.iloc[-1] > sma_50.iloc[-1]:
            market_type = 'bullish'
        elif sma_20.iloc[-1] < sma_50.iloc[-1]:
            market_type = 'bearish'
        else:
            market_type = 'sideways'
            
        # Determine volatility state
        if current_volatility > avg_volatility * 1.5:
            volatility_state = 'high'
        elif current_volatility < avg_volatility * 0.5:
            volatility_state = 'low'
        else:
            volatility_state = 'normal'
            
        # Determine volume profile
        if current_volume > avg_volume * 1.2:
            volume_profile = 'high'
        elif current_volume < avg_volume * 0.8:
            volume_profile = 'low'
        else:
            volume_profile = 'normal'
            
        # Calculate trend strength
        price_range = df['high'].rolling(window=20).max() - df['low'].rolling(window=20).min()
        price_change = abs(df['close'].diff(20))
        trend_strength = (price_change / price_range).iloc[-1]
        
        return {
            'type': market_type,
            'volatility_state': volatility_state,
            'volume_profile': volume_profile,
            'trend_strength': float(trend_strength)
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to identify market regime: {str(e)}")
        return {
            'type': 'unknown',
            'volatility_state': 'unknown',
            'volume_profile': 'unknown',
            'trend_strength': 0.0
        }

def predict_pattern_success(pattern_stats: dict, market_regime: dict) -> dict:
    """Predict pattern success probabilities based on market conditions"""
    try:
        predictions = {}
        
        # Base success rates from pattern_stats
        if 'success_rates' not in pattern_stats:
            return predictions
            
        for timeframe, stats in pattern_stats['success_rates'].items():
            base_success_rate = stats.get('positive_return_rate', 0.5)
            avg_return = stats.get('avg_return', 0.0)
            
            # Adjust probabilities based on market regime
            regime_multiplier = 1.0
            
            # Adjust for trend alignment
            if market_regime['type'] == 'bullish' and avg_return > 0:
                regime_multiplier *= 1.2
            elif market_regime['type'] == 'bearish' and avg_return < 0:
                regime_multiplier *= 1.2
                
            # Adjust for volatility
            if market_regime['volatility_state'] == 'high':
                regime_multiplier *= 0.8  # Less reliable in high volatility
            elif market_regime['volatility_state'] == 'low':
                regime_multiplier *= 1.1  # More reliable in low volatility
                
            # Adjust for volume
            if market_regime['volume_profile'] == 'high':
                regime_multiplier *= 1.1  # More reliable with high volume
            elif market_regime['volume_profile'] == 'low':
                regime_multiplier *= 0.9  # Less reliable with low volume
                
            # Calculate adjusted probability
            adjusted_probability = min(base_success_rate * regime_multiplier, 1.0)
            
            # Calculate confidence based on sample size and market conditions
            confidence = (min(stats.get('sample_size', 0) / 100, 1.0) * 
                        (market_regime['trend_strength'] if market_regime['trend_strength'] > 0 else 0.5))
            
            # Calculate historical risk/reward
            historical_risk_reward = abs(avg_return) / (pattern_stats.get('avg_volatility', 0.01) or 0.01)
            
            predictions[timeframe] = {
                'base_success_rate': base_success_rate,
                'adjusted_probability': adjusted_probability,
                'confidence': confidence,
                'historical_risk_reward': historical_risk_reward,
                'regime_multiplier': regime_multiplier
            }
            
        return predictions
        
    except Exception as e:
        print(f"[ERROR] Failed to predict pattern success: {str(e)}")
        return {}

async def generate_realtime_prediction(feed_data: dict) -> dict:
    """Generate real-time trading prediction based on market data feed."""
    try:
        # Extract metrics from feed data
        current_price = float(feed_data.get('close', 0))
        day_high = float(feed_data.get('high', 0))
        day_low = float(feed_data.get('low', 0))
        day_open = float(feed_data.get('open', 0))
        volume = float(feed_data.get('volume', 0))
        
        # Skip prediction if we don't have valid price data
        if current_price == 0 or day_high == 0 or day_low == 0:
            return {
                "signal": "HOLD",
                "confidence": 0.5,
                "price_trend": 0.0,
                "volume_ratio": 1.0
            }
        
        # Calculate basic technical indicators
        price_range = day_high - day_low
        if price_range == 0:
            price_range = 0.01  # Prevent division by zero
            
        # Position within day's range (0-1)
        range_position = (current_price - day_low) / price_range
        
        # Calculate price momentum
        price_change = ((current_price - day_open) / day_open) * 100
        
        # Determine signal and confidence
        signal = "HOLD"
        confidence = 0.5
        
        # Strong uptrend conditions
        if price_change > 1.5 and range_position > 0.8:
            signal = "BUY"
            confidence = min(0.9, 0.6 + (price_change / 10))
        
        # Strong downtrend conditions
        elif price_change < -1.5 and range_position < 0.2:
            signal = "SELL"
            confidence = min(0.9, 0.6 + (abs(price_change) / 10))
        
        # Potential reversal at extremes with high volume
        elif volume > 0 and range_position > 0.95:
            signal = "SELL"  # Potential top
            confidence = 0.7
        elif volume > 0 and range_position < 0.05:
            signal = "BUY"   # Potential bottom
            confidence = 0.7
            
        return {
            "signal": signal,
            "confidence": round(confidence, 2),
            "price_trend": round(price_change, 2),
            "range_position": round(range_position, 2),
            "price_change_percent": round(price_change, 2)
        }
            
    except Exception as e:
        print(f"[ERROR] Real-time prediction failed: {str(e)}")
        return {
            "signal": "HOLD",
            "confidence": 0.5,
            "price_trend": 0.0,
            "range_position": 0.5,
            "price_change_percent": 0.0
        }

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    """WebSocket endpoint for real-time market data streaming."""
    try:
        # Reset market data connection if it was stopped
        if not manager.running:
            manager.market_data_connection = None
            
        await manager.connect(websocket, symbol)
        
        try:
            while True:
                # Keep connection alive and handle client messages
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                    # Check market data connection health
                    if not manager.market_data_connection:
                        print("[WARN] Market data connection lost, reconnecting...")
                        await manager.subscribe_symbol(symbol)
        except WebSocketDisconnect:
            print(f"[INFO] Client disconnected from symbol {symbol}")
            manager.disconnect(websocket, symbol)
        except Exception as e:
            print(f"[ERROR] WebSocket error: {str(e)}")
            manager.disconnect(websocket, symbol)
            
    except Exception as e:
        print(f"[ERROR] WebSocket connection failed: {str(e)}")
        try:
            await websocket.close()
        except:
            pass

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on server shutdown."""
    manager.running = False
    if manager.market_data_connection:
        await manager.market_data_connection.close()

async def cleanup_market_data_connection(self):
        """Clean up market data connection when no more clients are connected."""
        try:
            if self.market_data_connection:
                print("[INFO] Closing market data connection")
                await self.market_data_connection.close()
                self.market_data_connection = None
                self.subscribed_symbols.clear()
                print("[INFO] Market data connection closed successfully")
        except Exception as e:
            print(f"[ERROR] Failed to close market data connection: {str(e)}")
        finally:
            self.market_data_connection = None
            self.running = False
