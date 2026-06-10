import React, { useState, useEffect, useRef } from 'react';
import { 
  TrendingUp, TrendingDown, AlertTriangle, ShieldAlert, Play, Pause, 
  RefreshCw, Layers, ShieldCheck, Activity, Award, Flame 
} from 'lucide-react';
import { createChart } from 'lightweight-charts';

// Endpoint kết nối API Backend
const API_BASE = `http://${window.location.hostname}:8000/api`;

const formatVietnamTime = (dateStr) => {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' });
  } catch (e) {
    return dateStr;
  }
};

export default function App() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [panicLoading, setPanicLoading] = useState(false);
  const [retrainLoading, setRetrainLoading] = useState(false);
  
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);

  // 1. Fetch dữ liệu realtime từ FastAPI
  const fetchData = async () => {
    try {
      const response = await fetch(`${API_BASE}/dashboard`);
      if (response.ok) {
        const json = await response.json();
        setData(json);
        setAiEnabled(json.ai_settings.enabled);
        setError(false);
      } else {
        setError(true);
      }
    } catch (err) {
      setError(true);
      setupMockData(); // Tự động fallback sang Mock dữ liệu trên UI nếu chưa chạy Backend
    } finally {
      setLoading(false);
    }
  };

  // 2. Thiết lập dữ liệu Mock trực quan nếu không kết nối được Backend
  const setupMockData = () => {
    setData((prev) => {
      if (prev && !prev.isMock) return prev;
      return {
        isMock: true,
        account: {
          balance: 10240.50,
          equity: 10325.20,
          profit: 84.70,
          margin: 400.0,
          margin_free: 9925.20,
          currency: "USD",
          name: "XAU/USD Demo Account"
        },
        open_positions: [
          { ticket: 1084201, symbol: "XAUUSD", type: "BUY", volume: 0.1, open_price: 2345.50, sl: 2335.00, tp: 2365.00, pnl: 45.20, time: "2026-06-09T14:30:00" },
          { ticket: 1084205, symbol: "XAUUSD", type: "BUY", volume: 0.05, open_price: 2348.00, sl: 2338.00, tp: 2368.00, pnl: 39.50, time: "2026-06-09T14:45:00" }
        ],
        daily_risk: {
          drawdown_percent: 0.85,
          max_drawdown_limit: 5.0,
          is_blocked: false
        },
        ai_settings: {
          enabled: aiEnabled,
          loss_prob_threshold: 0.60,
          half_size_threshold: 0.45,
          status: "READY",
          feature_importance: {
            "mins_to_news": 0.38,
            "rsi": 0.22,
            "spread": 0.16,
            "dist_ema200": 0.14,
            "atr": 0.10
          }
        },
        strategies: [
          { id: 1, name: "RSI_EMA_Cross", description: "Chiến lược giao cắt RSI quá mua quá bán kết hợp EMA20", is_active: true, risk_percent: 1.0 },
          { id: 2, name: "TradingView_Webhook", description: "Nhận tín hiệu từ Webhook TradingView bên ngoài", is_active: true, risk_percent: 1.0 },
          { id: 3, name: "Scalping_Gold", description: "Chiến lược Scalping nhanh khung M1", is_active: false, risk_percent: 0.5 }
        ],
        recent_trades: [
          { id: 101, ticket: 1084205, strategy_name: "RSI_EMA_Cross", symbol: "XAUUSD", action: "BUY", actual_volume: 0.05, entry_price: 2348.00, stop_loss: 2338.00, take_profit: 2368.00, ai_decision: "HALF_SIZE", ai_loss_probability: 0.52, status: "FILLED", pnl: 39.50, open_time: "2026-06-09T14:45:00" },
          { id: 100, ticket: null, strategy_name: "Scalping_Gold", symbol: "XAUUSD", action: "BUY", actual_volume: 0.0, entry_price: 2355.00, stop_loss: 2352.00, take_profit: 2360.00, ai_decision: "BLOCKED", ai_loss_probability: 0.78, status: "BLOCKED_BY_AI", pnl: 0.0, reject_reason: "AI dự đoán xác suất thua cao (78.0%)", open_time: "2026-06-09T14:20:00" },
          { id: 99, ticket: 1084190, strategy_name: "RSI_EMA_Cross", symbol: "XAUUSD", action: "SELL", actual_volume: 0.1, entry_price: 2362.00, stop_loss: 2372.00, take_profit: 2342.00, ai_decision: "ALLOWED", ai_loss_probability: 0.28, status: "CLOSED", pnl: 150.00, open_time: "2026-06-09T12:00:00" }
        ],
        recent_signals: [
          { id: 50, strategy_name: "RSI_EMA_Cross", symbol: "XAUUSD", action: "BUY", price: 2348.00, stop_loss: 2338.00, take_profit: 2368.00, created_at: "2026-06-09T14:45:00" },
          { id: 49, strategy_name: "Scalping_Gold", symbol: "XAUUSD", action: "BUY", price: 2355.00, stop_loss: 2352.00, take_profit: 2360.00, created_at: "2026-06-09T14:20:00" }
        ]
      };
    });
  };

  // Chạy Polling cập nhật dữ liệu mỗi 2 giây
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [aiEnabled]);

  // 3. Khởi tạo Biểu đồ TradingView
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Thiết lập biểu đồ
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0f111a' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Sinh dữ liệu nến mô phỏng để vẽ chart
    const generateChartData = () => {
      const dataPoints = [];
      let basePrice = 2330.00;
      let currTime = new Date();
      currTime.setHours(currTime.getHours() - 10);
      
      for (let i = 0; i < 120; i++) {
        const open = basePrice + (Math.random() - 0.5) * 4;
        const close = open + (Math.random() - 0.5) * 4;
        const high = Math.max(open, close) + Math.random() * 2;
        const low = Math.min(open, close) - Math.random() * 2;
        
        dataPoints.push({
          time: Math.floor(currTime.getTime() / 1000),
          open, high, low, close
        });
        
        basePrice = close;
        currTime = new Date(currTime.getTime() + 5 * 60 * 1000); // Tăng 5 phút
      }
      candleSeries.setData(dataPoints);
    };

    generateChartData();

    // Auto-fit màn hình biểu đồ
    const handleResize = () => {
      chart.applyOptions({
        width: chartContainerRef.current.clientWidth,
        height: 380
      });
    };
    
    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data == null]);

  // 4. API Actions
  const toggleAi = async () => {
    const nextState = !aiEnabled;
    setAiEnabled(nextState);
    if (data?.isMock) return;

    try {
      await fetch(`${API_BASE}/settings/ai-toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextState })
      });
    } catch (e) {
      console.error(e);
    }
  };

  const toggleStrategy = async (id, currentStatus) => {
    if (data?.isMock) {
      setData(prev => ({
        ...prev,
        strategies: prev.strategies.map(s => s.id === id ? { ...s, is_active: !s.is_active } : s)
      }));
      return;
    }

    try {
      await fetch(`${API_BASE}/strategies/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !currentStatus, risk_percent: 1.0 })
      });
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const triggerPanicButton = async () => {
    if (window.confirm("🚨 BẠN CÓ CHẮC CHẮN MUỐN ĐÓNG TOÀN BỘ LỆNH GIAO DỊCH NGAY LẬP TỨC KHÔNG?")) {
      setPanicLoading(true);
      if (data?.isMock) {
        setTimeout(() => {
          setData(prev => ({
            ...prev,
            open_positions: [],
            account: { ...prev.account, profit: 0, equity: prev.account.balance }
          }));
          setPanicLoading(false);
        }, 1000);
        return;
      }

      try {
        await fetch(`${API_BASE}/panic`, { method: "POST" });
        fetchData();
      } catch (e) {
        console.error(e);
      } finally {
        setPanicLoading(false);
      }
    }
  };

  const handleRetrain = async () => {
    if (window.confirm("🤖 Huấn luyện lại AI dựa trên Backtest mới sẽ mất khoảng vài giây. Tiến hành?")) {
      setRetrainLoading(true);
      if (data?.isMock) {
        setTimeout(() => {
          setRetrainLoading(false);
          alert("Huấn luyện AI thành công! Accuracy: 76.5% | Precision: 82.1%");
        }, 2000);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/ai/train`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ days: 180 })
        });
        if (response.ok) {
          const res = await response.json();
          alert(`Huấn luyện AI thành công! \nAccuracy: ${(res.metrics.test_accuracy*100).toFixed(1)}% \nPrecision: ${(res.metrics.test_precision*100).toFixed(1)}%`);
          fetchData();
        }
      } catch (e) {
        console.error(e);
      } finally {
        setRetrainLoading(false);
      }
    }
  };

  const handleClosePosition = async (ticket) => {
    if (data?.isMock) {
      setData(prev => ({
        ...prev,
        open_positions: prev.open_positions.filter(p => p.ticket !== ticket)
      }));
      return;
    }

    try {
      await fetch(`${API_BASE}/webhook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategy_name: "RSI_EMA_Cross",
          symbol: "XAUUSD",
          action: "CLOSE_ALL",
          price: 0.0,
          token: "super_secret_botxau_token"
        })
      });
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen bg-dark-900 text-gray-100 flex flex-col p-4 md:p-6 lg:p-8 space-y-6">
      
      {/* 1. Header Area */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center p-4 rounded-xl glass border-l-4 border-gold-500 gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center">
              <Layers className="text-gold-500 mr-2 h-7 w-7" /> BotXau <span className="text-gold-500 ml-1.5 font-light text-sm bg-gold-500/10 px-2 py-0.5 rounded border border-gold-500/20">BETA</span>
            </h1>
            {error ? (
              <span className="text-xs bg-yellow-500/10 border border-yellow-500/30 text-yellow-500 px-2 py-0.5 rounded flex items-center">
                <AlertTriangle className="h-3.5 w-3.5 mr-1" /> Mocking Mode
              </span>
            ) : (
              <span className="text-xs bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 px-2 py-0.5 rounded flex items-center">
                <Activity className="h-3.5 w-3.5 mr-1 animate-pulse" /> Live MT5 Connected
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1">Giám sát giao dịch tự động & Lọc lệnh lỗi thông qua Trí tuệ Nhân tạo (Meta-Labeling)</p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          {/* Panic Button */}
          <button
            onClick={triggerPanicButton}
            disabled={panicLoading}
            className={`w-full md:w-auto bg-red-600 hover:bg-red-700 disabled:bg-red-800 text-white font-bold px-6 py-3 rounded-lg flex items-center justify-center space-x-2 transition shadow-lg shadow-red-950 active-glow`}
          >
            <Flame className="h-5 w-5 animate-bounce" />
            <span>{panicLoading ? "PANIC CLOSING..." : "PANIC BUTTON"}</span>
          </button>
        </div>
      </header>

      {/* 2. Stat Cards Grid */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Balance Card */}
        <div className="p-5 rounded-xl glass flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-400 tracking-wider">BALANCE</span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className="text-2xl font-bold text-white">${data?.account?.balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) || "0.00"}</span>
            <span className="text-xs text-gray-500">{data?.account?.currency || "USD"}</span>
          </div>
          <div className="h-1 bg-gray-800 rounded-full mt-4 overflow-hidden">
            <div className="h-full bg-blue-500" style={{ width: '100%' }}></div>
          </div>
        </div>

        {/* Equity Card */}
        <div className="p-5 rounded-xl glass flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-400 tracking-wider">EQUITY</span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className="text-2xl font-bold text-white">${data?.account?.equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) || "0.00"}</span>
            <span className="text-xs text-gray-500">{data?.account?.currency || "USD"}</span>
          </div>
          <div className="h-1 bg-gray-800 rounded-full mt-4 overflow-hidden">
            <div 
              className={`h-full ${data?.account?.equity >= data?.account?.balance ? 'bg-emerald-500' : 'bg-red-500'}`} 
              style={{ width: `${Math.min(100, (data?.account?.equity / data?.account?.balance) * 100)}%` }}
            ></div>
          </div>
        </div>

        {/* Daily Profit Card */}
        <div className="p-5 rounded-xl glass flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-400 tracking-wider">OPEN PROFIT (PnL)</span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className={`text-2xl font-bold ${data?.account?.profit >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {data?.account?.profit >= 0 ? "+" : ""}${data?.account?.profit.toFixed(2) || "0.00"}
            </span>
          </div>
          <span className="text-[10px] text-gray-400 mt-4 flex items-center">
            {data?.account?.profit >= 0 ? (
              <TrendingUp className="h-3 w-3 text-emerald-400 mr-1" />
            ) : (
              <TrendingDown className="h-3 w-3 text-red-400 mr-1" />
            )}
            PnL thả nổi của {data?.open_positions?.length || 0} vị thế mở
          </span>
        </div>

        {/* Drawdown Risk Card */}
        <div className="p-5 rounded-xl glass flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-400 tracking-wider">DAILY DRAWDOWN LIMIT</span>
          <div className="flex justify-between items-baseline mt-2">
            <span className={`text-2xl font-bold ${data?.daily_risk?.is_blocked ? "text-red-500 animate-pulse" : "text-yellow-400"}`}>
              {data?.daily_risk?.drawdown_percent.toFixed(2)}%
            </span>
            <span className="text-xs text-gray-500">Max: {data?.daily_risk?.max_drawdown_limit}%</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full mt-3 overflow-hidden">
            <div 
              className={`h-full ${data?.daily_risk?.is_blocked ? 'bg-red-600' : drawdownColor(data?.daily_risk?.drawdown_percent)}`} 
              style={{ width: `${Math.min(100, (data?.daily_risk?.drawdown_percent / data?.daily_risk?.max_drawdown_limit) * 100)}%` }}
            ></div>
          </div>
        </div>
      </section>

      {/* 3. Main Chart & Settings Section */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Side: Candle Chart */}
        <div className="lg:col-span-2 p-4 rounded-xl glass flex flex-col justify-between">
          <div className="flex justify-between items-center mb-4">
            <span className="text-sm font-semibold text-white tracking-wide flex items-center">
              <Activity className="text-gold-500 mr-2 h-4.5 w-4.5 animate-pulse" /> XAU/USD (Vàng) - Khung 5 Phút (M5)
            </span>
            <span className="text-[10px] text-gray-400">TradingView Candle Simulator</span>
          </div>
          <div ref={chartContainerRef} className="w-full rounded-lg overflow-hidden border border-gray-800" style={{ height: '380px' }}></div>
        </div>

        {/* Right Side: AI Filter & Strategies Settings */}
        <div className="space-y-6">
          
          {/* AI Settings Box */}
          <div className="p-5 rounded-xl glass flex flex-col space-y-4">
            <div className="flex justify-between items-center border-b border-gray-800 pb-3">
              <h3 className="font-semibold text-white flex items-center">
                <ShieldCheck className="text-gold-500 mr-2 h-5 w-5" /> AI Loss-Filtering (Bộ lọc)
              </h3>
              {/* Toggle Switch */}
              <button 
                onClick={toggleAi}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${aiEnabled ? 'bg-gold-500' : 'bg-gray-700'}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${aiEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="bg-dark-800 p-3 rounded-lg border border-gray-800">
                <span className="text-gray-400 block mb-1">Xác suất Chặn (Block)</span>
                <span className="text-sm font-bold text-red-400">&ge; {(data?.ai_settings?.loss_prob_threshold * 100) || 60}%</span>
              </div>
              <div className="bg-dark-800 p-3 rounded-lg border border-gray-800">
                <span className="text-gray-400 block mb-1">Giảm 1/2 Khối lượng</span>
                <span className="text-sm font-bold text-yellow-400">&ge; {(data?.ai_settings?.half_size_threshold * 100) || 45}%</span>
              </div>
            </div>

            {/* Feature Importance visualizer */}
            {aiEnabled && (
              <div className="space-y-2 pt-2">
                <span className="text-xs text-gray-400 font-semibold block">ĐẶC TRƯNG AI QUAN TÂM NHẤT</span>
                <div className="space-y-2 max-h-32 overflow-y-auto">
                  {data?.ai_settings?.feature_importance && Object.entries(data.ai_settings.feature_importance)
                    .sort((a, b) => b[1] - a[1])
                    .map(([key, val]) => (
                      <div key={key} className="space-y-1">
                        <div className="flex justify-between text-[10px]">
                          <span className="text-gray-300 font-mono">{key}</span>
                          <span className="text-gold-400">{(val * 100).toFixed(0)}%</span>
                        </div>
                        <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
                          <div className="h-full bg-gold-500" style={{ width: `${val * 100}%` }}></div>
                        </div>
                      </div>
                    ))
                  }
                </div>
              </div>
            )}

            {/* Retrain AI Model */}
            <button
              onClick={handleRetrain}
              disabled={retrainLoading}
              className="w-full bg-dark-600 hover:bg-dark-500 border border-gray-700 text-white font-medium text-xs py-2 rounded transition flex items-center justify-center space-x-1"
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${retrainLoading ? "animate-spin" : ""}`} />
              <span>{retrainLoading ? "HUẤN LUYỆN LẠI AI..." : "CHẠY BACKTEST & HUẤN LUYỆN LẠI AI"}</span>
            </button>
          </div>

          {/* Strategy Manager */}
          <div className="p-5 rounded-xl glass flex flex-col space-y-4">
            <h3 className="font-semibold text-white flex items-center border-b border-gray-800 pb-3">
              <Layers className="text-gold-500 mr-2 h-5 w-5" /> Quản lý Chiến lược
            </h3>
            <div className="space-y-3">
              {data?.strategies?.map((strat) => (
                <div key={strat.id} className="flex justify-between items-center bg-dark-800 p-3 rounded-lg border border-gray-800">
                  <div>
                    <span className="text-xs font-bold text-white block">{strat.name}</span>
                    <span className="text-[10px] text-gray-400 block line-clamp-1 mt-0.5">{strat.description}</span>
                  </div>
                  <button
                    onClick={() => toggleStrategy(strat.id, strat.is_active)}
                    className={`text-xs px-2.5 py-1 rounded font-bold transition flex items-center space-x-1 ${
                      strat.is_active 
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20" 
                        : "bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20"
                    }`}
                  >
                    {strat.is_active ? <Play className="h-2.5 w-2.5" /> : <Pause className="h-2.5 w-2.5" />}
                    <span>{strat.is_active ? "RUNNING" : "PAUSED"}</span>
                  </button>
                </div>
              ))}
            </div>
          </div>

        </div>

      </section>

      {/* 4. Active Positions Section */}
      <section className="p-5 rounded-xl glass flex flex-col space-y-4">
        <h3 className="font-semibold text-white flex items-center border-b border-gray-800 pb-3">
          <Activity className="text-gold-500 mr-2 h-5 w-5" /> Vị thế giao dịch đang mở ({data?.open_positions?.length || 0})
        </h3>
        
        {data?.open_positions?.length === 0 ? (
          <div className="text-center py-6 text-gray-500 text-xs">Không có vị thế mở nào vào lúc này.</div>
        ) : (
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="py-2.5">Ticket</th>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Volume</th>
                  <th>Entry Price</th>
                  <th>Stop Loss</th>
                  <th>Take Profit</th>
                  <th>PnL</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {data?.open_positions?.map((pos) => (
                  <tr key={pos.ticket} className="border-b border-gray-800 hover:bg-dark-800 transition">
                    <td className="py-3 font-mono text-gray-300">#{pos.ticket}</td>
                    <td className="font-bold text-white">{pos.symbol}</td>
                    <td>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${pos.type === "BUY" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
                        {pos.type}
                      </span>
                    </td>
                    <td className="font-mono">{pos.volume} lot</td>
                    <td className="font-mono">${pos.open_price.toFixed(2)}</td>
                    <td className="font-mono text-red-400">${pos.sl?.toFixed(2) || "-"}</td>
                    <td className="font-mono text-emerald-400">${pos.tp?.toFixed(2) || "-"}</td>
                    <td className={`font-mono font-bold ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toFixed(2)}
                    </td>
                    <td className="text-right">
                      <button 
                        onClick={() => handleClosePosition(pos.ticket)}
                        className="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 px-2.5 py-1 rounded transition"
                      >
                        Close
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 5. AI Block log & Webhooks history */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* AI Block & Trade Log */}
        <div className="p-5 rounded-xl glass flex flex-col space-y-4">
          <h3 className="font-semibold text-white flex items-center border-b border-gray-800 pb-3">
            <ShieldAlert className="text-red-400 mr-2 h-5 w-5" /> Nhật ký Xử lý của AI & Lịch sử Lệnh
          </h3>
          <div className="space-y-3 overflow-y-auto max-h-80 pr-1">
            {data?.recent_trades?.length === 0 ? (
              <div className="text-center py-6 text-gray-500 text-xs">Chưa có lịch sử lệnh nào ghi nhận.</div>
            ) : (
              data?.recent_trades?.map((trade) => (
                <div key={trade.id} className="flex justify-between items-start bg-dark-800 p-3 rounded-lg border border-gray-800 text-xs">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${trade.action === "BUY" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>{trade.action}</span>
                      <span className="font-bold text-white">{trade.symbol}</span>
                      <span className="text-[10px] text-gray-400 font-mono">({trade.strategy_name})</span>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-1 space-x-2">
                      <span>Price: <strong className="text-white">${trade.entry_price.toFixed(2)}</strong></span>
                      <span>Volume: <strong className="text-white">{trade.actual_volume || trade.requested_volume} lot</strong></span>
                      {trade.ai_loss_probability && (
                        <span>Loss Prob: <strong className="text-red-400">{(trade.ai_loss_probability*100).toFixed(0)}%</strong></span>
                      )}
                    </div>
                    {trade.reject_reason && (
                      <span className="text-[10px] text-red-400 block mt-1 bg-red-950/20 px-2 py-0.5 rounded border border-red-500/10">Reason: {trade.reject_reason}</span>
                    )}
                  </div>
                  
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold block ${tradeStatusColor(trade.status)}`}>
                      {trade.status}
                    </span>
                    <span className="text-[9px] text-gray-500 mt-1 block">{formatVietnamTime(trade.open_time)}</span>
                    
                    {/* Render PnL for closed trades */}
                    {trade.status === "CLOSED" && (
                      <span className={`text-[10px] font-bold block mt-1 ${trade.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Webhook Signal History */}
        <div className="p-5 rounded-xl glass flex flex-col space-y-4">
          <h3 className="font-semibold text-white flex items-center border-b border-gray-800 pb-3">
            <TrendingUp className="text-gold-500 mr-2 h-5 w-5" /> Tín hiệu Webhook từ TradingView
          </h3>
          <div className="space-y-3 overflow-y-auto max-h-80 pr-1">
            {data?.recent_signals?.length === 0 ? (
              <div className="text-center py-6 text-gray-500 text-xs">Chưa nhận được tín hiệu webhook nào.</div>
            ) : (
              data?.recent_signals?.map((sig) => (
                <div key={sig.id} className="flex justify-between items-center bg-dark-800 p-3 rounded-lg border border-gray-800 text-xs">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${sig.action === "BUY" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>{sig.action}</span>
                      <span className="font-bold text-white">{sig.symbol}</span>
                      <span className="text-[10px] text-gray-400">({sig.strategy_name})</span>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-1 space-x-2">
                      <span>Signal Price: <strong>${sig.price.toFixed(2)}</strong></span>
                      <span>SL: <strong className="text-red-400">${sig.stop_loss?.toFixed(2) || "-"}</strong></span>
                      <span>TP: <strong className="text-emerald-400">${sig.take_profit?.toFixed(2) || "-"}</strong></span>
                    </div>
                  </div>
                  <span className="text-[9px] text-gray-500">{formatVietnamTime(sig.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </div>

      </section>

      {/* Footer */}
      <footer className="text-center text-[10px] text-gray-500 pt-4 border-t border-gray-800">
        BotXau Dashboard &copy; 2026. Thiết kế realtime tối ưu hóa dữ liệu tài chính.
      </footer>

    </div>
  );
}

// Helpers
function drawdownColor(val) {
  if (val < 1.5) return 'bg-emerald-500';
  if (val < 3.5) return 'bg-yellow-500';
  return 'bg-red-500';
}

function tradeStatusColor(status) {
  switch (status) {
    case "FILLED": return "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
    case "CLOSED": return "bg-blue-500/10 text-blue-400 border border-blue-500/20";
    case "BLOCKED_BY_AI": return "bg-red-500/10 text-red-400 border border-red-500/20";
    case "REJECTED": return "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20";
    default: return "bg-gray-500/10 text-gray-400 border border-gray-500/20";
  }
}
