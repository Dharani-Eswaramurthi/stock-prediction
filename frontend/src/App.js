import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, 
  ComposedChart, Candlestick, ReferenceLine 
} from 'recharts';
import { 
  Search, TrendingUp, TrendingDown, Activity, BarChart3, 
  Play, Pause, RefreshCw, Calendar, Clock, DollarSign, Zap, 
  Target, AlertCircle, CheckCircle, XCircle, ChevronUp, 
  ChevronDown, Volume2, VolumeX, Brain, Filter, Sparkles 
} from 'lucide-react';

const BACKEND_URL = "http://localhost:8000";

// Enhanced TradingChart component for professional OHLC display
const TradingChart = ({ historicalData, realTimeData, isStreaming, darkMode }) => {
  const formatVolume = (volume) => {
    if (volume >= 1000000) return `${(volume / 1000000).toFixed(1)}M`;
    if (volume >= 1000) return `${(volume / 1000).toFixed(1)}K`;
    return volume?.toString() || '0';
  };

  const combinedData = React.useMemo(() => {
    if (!historicalData.length) return [];
    
    const historical = [...historicalData];
    
    if (isStreaming && realTimeData.length > 0) {
      // Convert real-time data to candle format
      const realTimeCandles = realTimeData.map((point, index) => {
        // For the first real-time point, use the last historical close as open
        const open = index === 0 
          ? (historical[historical.length - 1]?.close || point.ltp)
          : (realTimeData[index - 1].ltp);
        
        return {
          time: point.time,
          timeLabel: point.time || (point.timestamp ? new Date(point.timestamp).toLocaleTimeString() : ''),
          timestamp: point.timestamp,
          open: open,
          high: Math.max(open, point.ltp),
          low: Math.min(open, point.ltp),
          close: point.ltp,
          volume: point.volume || 0,
          isLive: true
        };
      });
      
      return [...historical, ...realTimeCandles];
    }
    
    return historical;
  }, [historicalData, realTimeData, isStreaming]);

  const renderTooltip = (props) => {
    const { active, payload, label } = props;
    
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const isLive = data.isLive;
      const labelText = data?.timeLabel || data?.time || (data?.timestamp ? new Date(data.timestamp).toLocaleString() : label);
      
      return (
        <div className={`p-3 rounded-lg shadow-lg border ${
          darkMode 
            ? 'bg-gray-900 border-gray-700 text-white' 
            : 'bg-white border-gray-200 text-gray-900'
        }`}>
          <p className="font-bold mb-2">{labelText}</p>
          
          {isLive ? (
            <div className="space-y-1">
              <div className="flex justify-between gap-4">
                <span className="text-amber-500">Live Price:</span>
                <span className="font-bold">₹{data.close?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Change:</span>
                <span className={data.close >= data.open ? 'text-green-500' : 'text-red-500'}>
                  {data.close >= data.open ? '+' : ''}₹{(data.close - data.open).toFixed(2)}
                </span>
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="flex justify-between gap-4">
                <span>Open:</span>
                <span>₹{data.open?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>High:</span>
                <span className="text-green-500">₹{data.high?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Low:</span>
                <span className="text-red-500">₹{data.low?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Close:</span>
                <span className={data.close >= data.open ? 'text-green-500' : 'text-red-500'}>
                  ₹{data.close?.toFixed(2)}
                </span>
              </div>
              {data.volume > 0 && (
                <div className="flex justify-between gap-4">
                  <span>Volume:</span>
                  <span>{formatVolume(data.volume)}</span>
                </div>
              )}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  // Calculate SMA for last 20 periods and attach as field
  const chartData = React.useMemo(() => {
    const period = 20;
    let sum = 0;
    const smaVals = [];
    for (let i = 0; i < combinedData.length; i++) {
      sum += combinedData[i].close;
      if (i >= period) sum -= combinedData[i - period].close;
      smaVals.push(i >= period - 1 ? sum / period : null);
    }
    return combinedData.map((d, i) => ({ ...d, sma20: smaVals[i] }));
  }, [combinedData]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart
        data={chartData}
        margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
      >
        <CartesianGrid 
          strokeDasharray="3 3" 
          stroke={darkMode ? '#374151' : '#E5E7EB'} 
          opacity={0.5}
        />
        <XAxis 
          dataKey="timeLabel" 
          stroke={darkMode ? '#9CA3AF' : '#6B7280'}
          fontSize={12}
          tick={{ fill: darkMode ? '#9CA3AF' : '#6B7280' }}
        />
        <YAxis 
          stroke={darkMode ? '#9CA3AF' : '#6B7280'}
          fontSize={12}
          domain={['dataMin - 5', 'dataMax + 5']}
          tick={{ fill: darkMode ? '#9CA3AF' : '#6B7280' }}
          tickFormatter={(value) => `₹${value.toFixed(0)}`}
        />
        
        <Tooltip content={renderTooltip} />
        {/* Price close line */}
        <Line
          type="monotone"
          dataKey="close"
          stroke={darkMode ? '#60A5FA' : '#2563EB'}
          strokeWidth={1.8}
          dot={false}
          name="Close"
        />

        {/* SMA 20 overlay */}
        <Line
          type="monotone"
          dataKey="sma20"
          stroke="#8884d8"
          strokeWidth={1.2}
          dot={false}
          name="SMA 20"
        />

        {/* Live price indicator line */}
        {isStreaming && (
          <Line
            type="monotone"
            dataKey="close"
            stroke="#F59E0B"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            data={chartData.filter(d => d.isLive)}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
};

const TradingDashboard = () => {
  const [authenticated, setAuthenticated] = useState(false);
  const [authUrl, setAuthUrl] = useState('');
  const [instruments, setInstruments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedInstrument, setSelectedInstrument] = useState(null);
  const [historicalData, setHistoricalData] = useState([]);
  const [realTimeData, setRealTimeData] = useState([]);
  const [currentPrice, setCurrentPrice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dataStatus, setDataStatus] = useState('idle'); // idle | loading | ready | error
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState('disconnected');
  const [timeFrame, setTimeFrame] = useState('1W');
  const [interval, setInterval] = useState('1minute');
  const [darkMode, setDarkMode] = useState(true);
  const [marketStats, setMarketStats] = useState({
    high: 0, low: 0, open: 0, volume: 0, change: 0, changePercent: 0
  });
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    return d.toISOString().split('T')[0];
  });
  const [toDate, setToDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [predictionHorizon, setPredictionHorizon] = useState('next 30min');
  
  // New state for AI recommendations
  const [aiRecommendation, setAiRecommendation] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [analysisDays, setAnalysisDays] = useState(7);

  const wsRef = useRef(null);

  useEffect(() => {
    checkAuthStatus();
  }, []);

  // Listen for Upstox auth completion from popup
  useEffect(() => {
    const onMsg = (e) => {
      if (e?.data?.type === 'UPSTOX_AUTH' && e?.data?.status === 'ok') {
        checkAuthStatus();
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const checkAuthStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/auth/status`);
      const data = await response.json();
      if (data.authenticated) {
        setAuthenticated(true);
      } else {
        const authResponse = await fetch(`${BACKEND_URL}/auth/start`);
        const authData = await authResponse.json();
        setAuthUrl(authData.url);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
    }
  };

  const searchInstruments = useCallback(async (query) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const response = await fetch(`${BACKEND_URL}/instruments?q=${query}&limit=50`);
      const data = await response.json();
      setInstruments(data);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistoricalData = async (instrumentKey, intervalParam, timeFrameParam, fromOverride = null, toOverride = null) => {
    setLoading(true);
    setDataStatus('loading');
    try {
      const endDate = toOverride ? new Date(toOverride) : new Date();
      const startDate = fromOverride ? new Date(fromOverride) : new Date();
      
      switch(timeFrameParam) {
        case '1D': 
          startDate.setDate(endDate.getDate() - 1); 
          break;
        case '1W': 
          startDate.setDate(endDate.getDate() - 7); 
          break;
        case '1M': 
          startDate.setMonth(endDate.getMonth() - 1); 
          break;
        case '3M': 
          startDate.setMonth(endDate.getMonth() - 3); 
          break;
        case '1Y': 
          startDate.setFullYear(endDate.getFullYear() - 1); 
          break;
        default: 
          // CUSTOM range or fallback to last 7 days
          if (!fromOverride) startDate.setDate(endDate.getDate() - 7);
      }

      const response = await fetch(`${BACKEND_URL}/candles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument_key: instrumentKey,
          interval: intervalParam,
          from_date: startDate.toISOString().split('T')[0],
          to_date: endDate.toISOString().split('T')[0]
        })
      });
      
      const data = await response.json();
      const candles = data.candles || [];
      
      const processedData = candles.map((candle) => {
        const t = new Date(candle.time);
        return {
          ...candle,
          time: t.toISOString(),
          timeLabel: t.toLocaleString(),
          timestamp: t.getTime(),
          volume_formatted: formatVolume(candle.volume || 0)
        };
      });

      setHistoricalData(processedData);
      
      if (candles.length > 0) {
        const latest = candles[candles.length - 1];
        const first = candles[0];
        const prices = candles.map(c => c.close);
        const denom = first.close || first.open || 1;
        setMarketStats({
          high: Math.max(...prices),
          low: Math.min(...prices),
          open: first.open,
          volume: candles.reduce((sum, c) => sum + (c.volume || 0), 0),
          change: latest.close - (first.close ?? first.open),
          changePercent: denom ? (((latest.close - denom) / denom) * 100) : 0
        });
      }
      setDataStatus('ready');
      return processedData;
    } catch (error) {
      console.error('Failed to fetch historical data:', error);
      setDataStatus('error');
      return [];
    } finally {
      setLoading(false);
    }
  };

  const startStreaming = async () => {
    if (!selectedInstrument) return;
    
    try {
      const authResponse = await fetch(`${BACKEND_URL}/auth/status`);
      const authData = await authResponse.json();
      
      if (!authData.access_token) return;

      const wsUrl = `${BACKEND_URL.replace('http', 'ws')}/ws/ltp_v3?instrument_key=${selectedInstrument.instrument_key}&access_token=${authData.access_token}`;
      
      wsRef.current = new WebSocket(wsUrl);
      
      const lastTickRef = { current: Date.now() };
      let stallTimer = null;

      wsRef.current.onopen = () => {
        setStreamingStatus('connected');
        setIsStreaming(true);
        lastTickRef.current = Date.now();
        // Detect no-data after connect
        stallTimer = setInterval(() => {
          if (Date.now() - lastTickRef.current > 15000) {
            setStreamingStatus('stalled');
          }
        }, 5000);
      };
      
      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const feeds = data.feeds || {};
          
          Object.values(feeds).forEach(feed => {
            const ltpc = feed.fullFeed?.indexFF?.ltpc || feed.fullFeed?.marketFF?.ltpc;
            if (ltpc) {
              const newPrice = {
                ltp: ltpc.ltp,
                change: ltpc.cp || 0,
                changePercent: ltpc.chp || 0,
                time: new Date().toLocaleTimeString(),
                timestamp: Date.now(),
                volume: ltpc.volume || 0
              };
              
              setCurrentPrice(newPrice);
              setRealTimeData(prev => [...prev.slice(-200), newPrice]);
              lastTickRef.current = Date.now();
              if (streamingStatus === 'stalled') setStreamingStatus('connected');
            }
          });
        } catch (error) {
          console.error('WebSocket message error:', error);
        }
      };
      
      wsRef.current.onerror = () => {
        setStreamingStatus('error');
      };
      
      wsRef.current.onclose = () => {
        setStreamingStatus('disconnected');
        setIsStreaming(false);
        if (stallTimer) clearInterval(stallTimer);
      };
      
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      setStreamingStatus('error');
    }
  };

  const stopStreaming = () => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsStreaming(false);
    setStreamingStatus('disconnected');
  };

  const formatVolume = (volume) => {
    if (volume >= 1000000) return `${(volume / 1000000).toFixed(1)}M`;
    if (volume >= 1000) return `${(volume / 1000).toFixed(1)}K`;
    return volume.toString();
  };

  const formatPrice = (price) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      minimumFractionDigits: 2
    }).format(price);
  };

  const [aiStatus, setAiStatus] = useState('idle'); // idle | analyzing | ready | error
  const fetchAiRecommendation = async (instrumentKey, candlesData) => {
    if (!instrumentKey || !candlesData.length) return;
    
    setAiLoading(true);
    setAiStatus('analyzing');
    try {
      const response = await fetch(`${BACKEND_URL}/signal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instrument_key: instrumentKey,
          symbol: selectedInstrument.trading_symbol,
          candles: candlesData.map(c => ({
            time: new Date(c.timestamp).toISOString(),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume
          })),
          horizon: predictionHorizon,
          analysis_interval: interval,
          from_date: fromDate,
          to_date: toDate
        })
      });
      
      const data = await response.json();
      setAiRecommendation(data);
      setAiStatus('ready');
    } catch (error) {
      console.error('Failed to fetch AI recommendation:', error);
      setAiStatus('error');
    } finally {
      setAiLoading(false);
    }
  };

  const handleInstrumentSelect = (instrument) => {
    setSelectedInstrument(instrument);
    setRealTimeData([]);
    setCurrentPrice(null);
    setAiRecommendation(null);
    setAiStatus('idle');
    if (isStreaming) stopStreaming();
    fetchHistoricalData(instrument.instrument_key, interval, timeFrame, fromDate, toDate);
  };

  const renderAiRecommendation = () => {
    if (!aiRecommendation) return null;
    
    const { 
      signal, confidence, reasoning, indicators, insights,
      entry_price, stop_loss, take_profit, risk_reward,
      expected_move_pct, stop_distance_pct, take_profit_distance_pct,
      explanation_points, metrics, caveats, key_levels
    } = aiRecommendation;
    
    const getSignalColor = () => {
      switch(signal) {
        case 'BUY': return 'text-green-500';
        case 'SELL': return 'text-red-500';
        default: return 'text-gray-500';
      }
    };
    
    const getSignalIcon = () => {
      switch(signal) {
        case 'BUY': return <CheckCircle size={20} className="text-green-500" />;
        case 'SELL': return <XCircle size={20} className="text-red-500" />;
        default: return <AlertCircle size={20} className="text-gray-500" />;
      }
    };
    
    return (
      <div className={`rounded-xl p-4 border ${
        signal === 'BUY' ? 'bg-green-500/10 border-green-500/30' :
        signal === 'SELL' ? 'bg-red-500/10 border-red-500/30' :
        'bg-gray-500/10 border-gray-500/30'
      }`}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Brain size={20} />
            <h4 className="font-semibold">AI Recommendation</h4>
          </div>
          <div className="flex items-center gap-2">
            {getSignalIcon()}
            <span className={`font-bold ${getSignalColor()}`}>{signal}</span>
          </div>
        </div>
        
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <span className="text-sm text-gray-500">Confidence:</span>
            <div className="font-semibold">{(confidence * 100).toFixed(1)}%</div>
          </div>
          <div>
            <span className="text-sm text-gray-500">Signal Strength:</span>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div 
                className={`h-2.5 rounded-full ${
                signal === 'BUY' ? 'bg-green-500' : 
                signal === 'SELL' ? 'bg-red-500' : 'bg-gray-500'
                }`} 
                style={{ width: `${Math.min(100, Math.max(5, confidence * 100))}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* Trade Plan */}
        <div className="grid grid-cols-3 gap-3 mb-4 text-sm">
          <div className={`${signal === 'BUY' ? 'bg-green-500/10' : signal === 'SELL' ? 'bg-red-500/10' : 'bg-gray-500/10'} rounded-lg p-3 border border-white/10`}>
            <div className="text-gray-500">Entry</div>
            <div className="font-semibold">₹{(entry_price ?? 0).toFixed(2)}</div>
          </div>
          <div className="bg-red-500/10 rounded-lg p-3 border border-white/10">
            <div className="text-gray-500">Stop Loss</div>
            <div className="font-semibold">₹{(stop_loss ?? 0).toFixed(2)}{stop_distance_pct != null ? ` (${stop_distance_pct.toFixed(2)}%)` : ''}</div>
          </div>
          <div className="bg-green-500/10 rounded-lg p-3 border border-white/10">
            <div className="text-gray-500">Take Profit</div>
            <div className="font-semibold">₹{(take_profit ?? 0).toFixed(2)}{take_profit_distance_pct != null ? ` (${take_profit_distance_pct.toFixed(2)}%)` : ''}</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mb-4 text-sm">
          <div className="rounded-lg p-3 border border-white/10">
            <div className="text-gray-500">Risk/Reward</div>
            <div className="font-semibold">{risk_reward != null ? risk_reward.toFixed(2) : '—'}</div>
          </div>
          <div className="rounded-lg p-3 border border-white/10">
            <div className="text-gray-500">Expected Move</div>
            <div className="font-semibold">{expected_move_pct != null ? `${expected_move_pct.toFixed(2)}%` : '—'}</div>
          </div>
          {key_levels && (
            <div className="rounded-lg p-3 border border-white/10">
              <div className="text-gray-500">Key Level</div>
              <div className="font-semibold">
                {(() => {
                  const fmt = (v) => (typeof v === 'number' ? v.toFixed(2) : v);
                  if (key_levels.pivot != null) return `Pivot: ₹${fmt(key_levels.pivot)}`;
                  if (key_levels.support1 != null) return `S1: ₹${fmt(key_levels.support1)}`;
                  if (key_levels.resistance1 != null) return `R1: ₹${fmt(key_levels.resistance1)}`;
                  return '—';
                })()}
              </div>
            </div>
          )}
        </div>
        
        {/* Why this prediction */}
        {(explanation_points?.length || insights || reasoning) && (
          <div className="text-sm mb-3 break-words">
            <div className="text-gray-500 mb-1">Why this prediction</div>
            {explanation_points?.length ? (
              <ul className="list-disc pl-5 space-y-1">
                {explanation_points.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            ) : (
              <div>{insights || reasoning}</div>
            )}
          </div>
        )}
        
        {/* Key numbers */}
        <div className="text-sm">
          <div className="text-gray-500 mb-1">Key Numbers</div>
          {metrics?.length ? (
            <div className="grid grid-cols-2 gap-2">
              {metrics.map((m, idx) => (
                <div key={idx} className="flex justify-between">
                  <span className="capitalize">{m.name}:</span>
                  <span className="font-medium">{typeof m.value === 'number' ? m.value.toFixed(2) : m.value}{m.unit ? ` ${m.unit}` : ''}{m.note ? ` (${m.note})` : ''}</span>
                </div>
              ))}
            </div>
          ) : indicators ? (
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(indicators).map(([key, value]) => (
                <div key={key} className="flex justify-between">
                  <span className="capitalize">{key}:</span>
                  <span className="font-medium">{typeof value === 'number' ? value.toFixed(2) : value}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        {/* Caveats */}
        {caveats?.length ? (
          <div className="text-xs text-amber-500 mt-3">
            <div className="font-semibold mb-1">Caveats</div>
            <ul className="list-disc pl-5 space-y-0.5">
              {caveats.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
        ) : null}
      </div>
    );
  };

  // (Old AI filters removed by request)

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="bg-white/10 backdrop-blur-lg rounded-3xl p-12 max-w-md w-full mx-4 shadow-2xl border border-white/20">
          <div className="text-center">
            <div className="w-20 h-20 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-8">
              <TrendingUp size={40} className="text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white mb-4">Stock Analytics</h1>
            <p className="text-gray-300 mb-8">Connect your Upstox account to access real-time market data and advanced analytics</p>
            <a
              href={authUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white px-8 py-4 rounded-xl font-semibold transition-all duration-200 transform hover:scale-105"
            >
              <CheckCircle size={20} />
              Connect Upstox Account
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`min-h-screen transition-all duration-300 ${darkMode ? 'bg-slate-900 text-white' : 'bg-gray-50 text-gray-900'}`}>
      {/* Global loading overlay for API calls */}
      {loading && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center">
          <div className={`${darkMode ? 'bg-slate-800' : 'bg-white'} p-6 rounded-2xl shadow-xl border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
            <div className="flex items-center gap-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              <div className="text-sm font-medium">Fetching historical data...</div>
            </div>
          </div>
        </div>
      )}
      <header className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} backdrop-blur-lg border-b ${darkMode ? 'border-slate-700' : 'border-gray-200'} sticky top-0 z-50`}>
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-purple-600 rounded-xl flex items-center justify-center">
                <BarChart3 size={24} className="text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Trading Pro</h1>
                <p className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Professional Charts & Analytics</p>
              </div>
            </div>
            
            <div className="flex items-center gap-4">
              <div className="relative">
                <Search size={20} className={`absolute left-3 top-1/2 transform -translate-y-1/2 ${darkMode ? 'text-gray-400' : 'text-gray-500'}`} />
                <input
                  type="text"
                  placeholder="Search stocks..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && searchInstruments(searchQuery)}
                  className={`pl-10 pr-4 py-2 rounded-xl border ${darkMode ? 'bg-slate-700 border-slate-600 text-white placeholder-gray-400' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500 focus:border-transparent w-64`}
                />
              </div>
              
              <button
                onClick={() => setDarkMode(!darkMode)}
                className={`p-2 rounded-xl ${darkMode ? 'bg-slate-700 hover:bg-slate-600' : 'bg-gray-100 hover:bg-gray-200'} transition-colors`}
              >
                {darkMode ? '🌞' : '🌙'}
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Process status chips */}
        <div className="mb-4 flex gap-2 flex-wrap">
          <div className={`px-2 py-1 rounded-full text-xs border ${
            dataStatus === 'loading' ? 'bg-blue-500/10 text-blue-400 border-blue-400/30' :
            dataStatus === 'error' ? 'bg-red-500/10 text-red-400 border-red-400/30' :
            dataStatus === 'ready' ? 'bg-green-500/10 text-green-400 border-green-400/30' : 'bg-gray-500/10 text-gray-400 border-gray-400/30'
          }`}>
            Data: {dataStatus}
          </div>
          <div className={`px-2 py-1 rounded-full text-xs border ${
            aiStatus === 'analyzing' ? 'bg-purple-500/10 text-purple-400 border-purple-400/30' :
            aiStatus === 'error' ? 'bg-red-500/10 text-red-400 border-red-400/30' :
            aiStatus === 'ready' ? 'bg-green-500/10 text-green-400 border-green-400/30' : 'bg-gray-500/10 text-gray-400 border-gray-400/30'
          }`}>
            AI: {aiStatus}
          </div>
          <div className={`px-2 py-1 rounded-full text-xs border ${
            streamingStatus === 'connected' ? 'bg-green-500/10 text-green-400 border-green-400/30' :
            streamingStatus === 'stalled' ? 'bg-yellow-500/10 text-yellow-400 border-yellow-400/30' :
            streamingStatus === 'error' ? 'bg-red-500/10 text-red-400 border-red-400/30' : 'bg-gray-500/10 text-gray-400 border-gray-400/30'
          }`}>
            Live: {streamingStatus}
          </div>
        </div>
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-3">
            <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'} h-fit overflow-hidden`}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Instruments</h3>
                <button
                  onClick={() => searchInstruments(searchQuery)}
                  className={`p-2 rounded-lg ${darkMode ? 'bg-slate-700 hover:bg-slate-600' : 'bg-gray-100 hover:bg-gray-200'} transition-colors`}
                >
                  <RefreshCw size={16} />
                </button>
              </div>
              
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {instruments.map((instrument, index) => (
                  <button
                    key={index}
                    onClick={() => handleInstrumentSelect(instrument)}
                    className={`w-full text-left p-3 rounded-xl transition-all ${
                      selectedInstrument?.instrument_key === instrument.instrument_key
                        ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white shadow-lg'
                        : darkMode ? 'bg-slate-700/50 hover:bg-slate-700' : 'bg-gray-50 hover:bg-gray-100'
                    }`}
                  >
                    <div className="font-medium">{instrument.trading_symbol}</div>
                    <div className={`text-sm ${selectedInstrument?.instrument_key === instrument.instrument_key ? 'text-blue-100' : darkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                      {instrument.name}
                    </div>
                  </button>
                ))}
              </div>

              {/* AI section moved to main column for wider layout */}
            </div>
          </div>

          <div className="col-span-9 space-y-6">
            {selectedInstrument ? (
              <>
                <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h2 className="text-2xl font-bold">{selectedInstrument.trading_symbol}</h2>
                      <p className={`${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>{selectedInstrument.name}</p>
                    </div>
                    
                    <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${
                        streamingStatus === 'connected' ? 'bg-green-500 animate-pulse' : 
                        streamingStatus === 'stalled' ? 'bg-yellow-500' :
                        streamingStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'
                      }`}></div>
                      <span className={`text-sm font-medium ${
                        streamingStatus === 'connected' ? 'text-green-500' : 
                        streamingStatus === 'stalled' ? 'text-yellow-500' :
                        streamingStatus === 'error' ? 'text-red-500' : 'text-gray-400'
                      }`}>
                        {streamingStatus === 'connected' ? 'LIVE' : streamingStatus === 'stalled' ? 'NO LIVE DATA' : streamingStatus === 'error' ? 'ERROR' : 'OFFLINE'}
                      </span>
                    </div>
                      
                      <button
                        onClick={isStreaming ? stopStreaming : startStreaming}
                        className={`flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all transform hover:scale-105 ${
                          isStreaming 
                            ? 'bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white shadow-lg' 
                            : 'bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white shadow-lg'
                        }`}
                      >
                        {isStreaming ? <Pause size={18} /> : <Play size={18} />}
                        {isStreaming ? 'Stop Live Feed' : 'Start Live Feed'}
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-6 gap-6">
                    <div className="col-span-2">
                      <div className="text-4xl font-bold mb-2">
                        {currentPrice ? formatPrice(currentPrice.ltp) : formatPrice(historicalData[historicalData.length - 1]?.close || 0)}
                      </div>
                      <div className={`flex items-center gap-2 text-lg ${
                        (currentPrice?.change || marketStats.change) >= 0 ? 'text-green-500' : 'text-red-500'
                      }`}>
                        {(currentPrice?.change || marketStats.change) >= 0 ? <ChevronUp size={24} /> : <ChevronDown size={24} />}
                        <span className="font-semibold">
                          {formatPrice(Math.abs(currentPrice?.change || marketStats.change))} 
                          ({(currentPrice?.changePercent || marketStats.changePercent).toFixed(2)}%)
                        </span>
                        {isStreaming && <span className="text-xs bg-amber-500 text-white px-2 py-1 rounded-full animate-pulse">LIVE</span>}
                      </div>
                    </div>
                    
                    <div className="space-y-1">
                      <div className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Day High</div>
                      <div className="font-bold text-green-500 text-xl">{formatPrice(marketStats.high)}</div>
                    </div>
                    
                    <div className="space-y-1">
                      <div className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Day Low</div>
                      <div className="font-bold text-red-500 text-xl">{formatPrice(marketStats.low)}</div>
                    </div>
                    
                    <div className="space-y-1">
                      <div className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Open</div>
                      <div className="font-bold text-xl">{formatPrice(marketStats.open)}</div>
                    </div>
                    
                    <div className="space-y-1">
                      <div className={`text-sm ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>Volume</div>
                      <div className="font-bold text-xl">{formatVolume(marketStats.volume)}</div>
                    </div>
                  </div>
                </div>

                <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-4 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {['1D', '1W', '1M', '3M', '1Y'].map((tf) => (
                        <button
                          key={tf}
                          onClick={() => {
                            setTimeFrame(tf);
                            fetchHistoricalData(selectedInstrument.instrument_key, interval, tf);
                          }}
                          className={`px-4 py-2 rounded-lg font-medium transition-all ${
                            timeFrame === tf
                              ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white'
                              : darkMode ? 'bg-slate-700 hover:bg-slate-600' : 'bg-gray-100 hover:bg-gray-200'
                          }`}
                        >
                          {tf}
                        </button>
                      ))}
                    </div>
                    
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-2">
                        <label className="text-sm opacity-70">From</label>
                        <input
                          type="date"
                          value={fromDate}
                          onChange={(e) => {
                            setFromDate(e.target.value);
                            setTimeFrame('CUSTOM');
                            const todayStr = new Date().toISOString().split('T')[0];
                            setToDate(todayStr);
                            if (selectedInstrument) {
                              fetchHistoricalData(selectedInstrument.instrument_key, interval, 'CUSTOM', e.target.value, todayStr);
                            }
                          }}
                          className={`px-2 py-1 rounded-lg border ${darkMode ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300'}`}
                        />
                      </div>
                      <select
                        value={interval}
                        onChange={(e) => {
                          setInterval(e.target.value);
                          const todayStr = new Date().toISOString().split('T')[0];
                          setToDate(todayStr);
                          if (selectedInstrument) {
                            fetchHistoricalData(selectedInstrument.instrument_key, e.target.value, timeFrame, fromDate, todayStr);
                          }
                        }}
                        className={`px-3 py-2 rounded-lg border ${darkMode ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                      >
                        <option value="1minute">1 Minute</option>
                        <option value="30minute">30 Minutes</option>
                        <option value="day">1 Day</option>
                        <option value="week">1 Week</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* Wider AI Analysis panel below chart */}
                <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                  <div className="flex items-center justify-between mb-4 gap-2">
                    <h3 className="font-semibold flex items-center gap-2">
                      <Brain size={18} />
                      AI Analysis
                    </h3>
                    <div className="flex items-center gap-2 flex-wrap justify-end">
                      <select
                        value={predictionHorizon}
                        onChange={(e) => setPredictionHorizon(e.target.value)}
                        className={`px-3 py-2 rounded-lg border ${darkMode ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300'} text-sm`}
                      >
                        <option value="next 30min">Next 30 minutes</option>
                        <option value="next 1h">Next 1 hour</option>
                        <option value="next 1d">Next 1 day</option>
                        <option value="next 1w">Next 1 week</option>
                      </select>
                      <div className="flex items-center gap-2">
                        <label className="text-sm opacity-70">Days to analyze</label>
                        <input
                          type="number"
                          min="1"
                          max="3650"
                          value={analysisDays}
                          onChange={(e) => setAnalysisDays(Number(e.target.value) || 1)}
                          className={`w-24 px-2 py-2 rounded-lg border ${darkMode ? 'bg-slate-700 border-slate-600 text-white' : 'bg-white border-gray-300'} text-sm`}
                        />
                      </div>
                      <button
                        disabled={!selectedInstrument}
                        onClick={async () => {
                          if (!selectedInstrument) return;
                          const end = new Date();
                          const start = new Date();
                          start.setDate(end.getDate() - Math.max(1, analysisDays));
                          const startStr = start.toISOString().split('T')[0];
                          const endStr = end.toISOString().split('T')[0];
                          setFromDate(startStr);
                          setToDate(endStr);
                          const data = await fetchHistoricalData(selectedInstrument.instrument_key, interval, 'CUSTOM', startStr, endStr);
                          if (data && data.length) {
                            await fetchAiRecommendation(selectedInstrument.instrument_key, data);
                          }
                        }}
                        className={`px-3 py-2 rounded-lg ${darkMode ? 'bg-blue-600 hover:bg-blue-500' : 'bg-blue-500 hover:bg-blue-600'} text-white text-sm disabled:opacity-50`}
                      >
                        Reanalyze
                      </button>
                    </div>
                  </div>
                  {aiLoading ? (
                    <div className="text-center py-6">
                      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto"></div>
                      <p className="text-sm text-gray-500 mt-3">Running AI analysis...</p>
                    </div>
                  ) : (
                    renderAiRecommendation()
                  )}
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <div className={`col-span-2 ${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="font-semibold flex items-center gap-2 text-lg">
                        <Activity size={24} />
                        Professional Trading Chart
                        {isStreaming && (
                          <div className="flex items-center gap-2">
                            <span className="text-amber-500 animate-pulse text-sm">● LIVE STREAMING</span>
                            <div className="bg-amber-500/20 text-amber-400 px-2 py-1 rounded-full text-xs font-medium">
                              Real-time Data
                            </div>
                          </div>
                        )}
                      </h3>
                      <div className="flex items-center gap-2">
                        <div className={`px-3 py-1 rounded-full text-xs font-medium ${
                          isStreaming 
                            ? 'bg-green-500/20 text-green-400 border border-green-500/30' 
                            : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                        }`}>
                          {isStreaming ? 'LIVE MODE' : 'HISTORICAL'}
                        </div>
                        <button className={`p-2 rounded-lg ${darkMode ? 'bg-slate-700 hover:bg-slate-600' : 'bg-gray-100 hover:bg-gray-200'} transition-colors`}>
                          <BarChart3 size={16} />
                        </button>
                      </div>
                    </div>
                    
                    <div className="h-96 relative">
                      {streamingStatus === 'stalled' && (
                        <div className="absolute z-10 top-2 left-2 right-2 bg-yellow-500/10 border border-yellow-500/40 text-yellow-600 px-3 py-2 rounded-lg text-sm">
                          No live ticks received. Market may be closed. Resumes next business day at 9:15 AM IST.
                        </div>
                      )}
                      <TradingChart 
                        historicalData={historicalData}
                        realTimeData={realTimeData}
                        isStreaming={isStreaming}
                        darkMode={darkMode}
                      />
                      
                      {/* Live price indicator */}
                      {isStreaming && currentPrice && (
                        <div className="absolute top-4 right-4 bg-amber-500/90 backdrop-blur-sm text-white px-4 py-2 rounded-lg shadow-lg border border-amber-400/50">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
                            <span className="font-medium">₹{currentPrice.ltp.toFixed(2)}</span>
                            <span className={`text-xs ${currentPrice.change >= 0 ? 'text-green-200' : 'text-red-200'}`}>
                              {currentPrice.change >= 0 ? '+' : ''}{currentPrice.change.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <Volume2 size={20} />
                      Volume Analysis
                    </h3>
                    <div className="h-48">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={historicalData}>
                          <CartesianGrid strokeDasharray="3 3" stroke={darkMode ? '#374151' : '#E5E7EB'} />
                          <XAxis 
                            dataKey="timeLabel" 
                            stroke={darkMode ? '#9CA3AF' : '#6B7280'}
                            fontSize={10}
                          />
                          <YAxis 
                            stroke={darkMode ? '#9CA3AF' : '#6B7280'}
                            fontSize={10}
                            tickFormatter={formatVolume}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: darkMode ? '#1F2937' : '#FFFFFF',
                              border: darkMode ? '1px solid #374151' : '1px solid #E5E7EB',
                              borderRadius: '12px'
                            }}
                            formatter={(value) => [formatVolume(value), 'Volume']}
                          />
                          <Bar 
                            dataKey="volume" 
                            fill={darkMode ? '#3B82F6' : '#2563EB'} 
                            opacity={0.7}
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-6 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'}`}>
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                      <Target size={20} />
                      Market Statistics
                    </h3>
                    <div className="space-y-4">
                      <div className="flex justify-between">
                        <span className={darkMode ? 'text-gray-400' : 'text-gray-600'}>Day Range</span>
                        <span className="font-medium">{formatPrice(marketStats.low)} - {formatPrice(marketStats.high)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className={darkMode ? 'text-gray-400' : 'text-gray-600'}>52W High</span>
                        <span className="font-medium text-green-500">{formatPrice(marketStats.high * 1.2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className={darkMode ? 'text-gray-400' : 'text-gray-600'}>52W Low</span>
                        <span className="font-medium text-red-500">{formatPrice(marketStats.low * 0.8)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className={darkMode ? 'text-gray-400' : 'text-gray-600'}>Avg Volume</span>
                        <span className="font-medium">{formatVolume(marketStats.volume / (historicalData.length || 1))}</span>
                      </div>
                    </div>
                  </div>
                </div>

              </>
            ) : (
              <div className={`${darkMode ? 'bg-slate-800/50' : 'bg-white'} rounded-2xl p-12 shadow-lg border ${darkMode ? 'border-slate-700' : 'border-gray-200'} text-center`}>
                <div className="w-16 h-16 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Search size={32} className="text-white" />
                </div>
                <h3 className="text-xl font-semibold mb-2">Select an Instrument</h3>
                <p className={`${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                  Search and select a stock from the sidebar to view detailed analytics and start live streaming
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TradingDashboard;
