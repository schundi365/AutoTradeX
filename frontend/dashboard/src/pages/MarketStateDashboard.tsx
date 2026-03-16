import { useState, useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { marketApi } from '../api/client';
import { Symbol, Indicators, OrderBook } from '../types';
import MarketRegimeIndicator from '../components/MarketRegimeIndicator';
import SymbolWatchlist from '../components/SymbolWatchlist';
import TechnicalIndicators from '../components/TechnicalIndicators';
import OrderBookHeatmap from '../components/OrderBookHeatmap';
import NewsSentiment from '../components/NewsSentiment';
import EconomicCalendar from '../components/EconomicCalendar';

export default function MarketStateDashboard() {
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('XAUUSD');
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [orderBook, setOrderBook] = useState<OrderBook | null>(null);
  const [marketRegime] = useState<string>('ranging');
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  // WebSocket connection for real-time updates
  const { isConnected } = useWebSocket('ws://localhost:8000/ws/dashboard', {
    onMessage: (message) => {
      if (message.type === 'market_update') {
        if (message.symbol === selectedSymbol) {
          setIndicators((prev) => ({
            ...prev,
            ...message.data,
            symbol: message.symbol,
            timestamp: message.timestamp,
          } as Indicators));
          setLastUpdate(new Date());
        }
      }
    },
    onConnect: () => {
      console.log('Market State WebSocket connected');
    },
    onDisconnect: () => {
      console.log('Market State WebSocket disconnected');
    },
  });

  // Load initial data
  useEffect(() => {
    const loadSymbols = async () => {
      try {
        const response = await marketApi.getSymbols();
        setSymbols(response.data.symbols);
      } catch (error) {
        console.error('Failed to load symbols:', error);
      }
    };
    loadSymbols();
  }, []);

  // Load indicators for selected symbol
  useEffect(() => {
    const loadIndicators = async () => {
      try {
        const response = await marketApi.getIndicators(selectedSymbol);
        setIndicators(response.data);
      } catch (error) {
        console.error('Failed to load indicators:', error);
      }
    };

    const loadOrderBook = async () => {
      try {
        const response = await marketApi.getOrderBook(selectedSymbol);
        setOrderBook(response.data);
      } catch (error) {
        console.error('Failed to load order book:', error);
      }
    };

    if (selectedSymbol) {
      loadIndicators();
      loadOrderBook();
    }
  }, [selectedSymbol]);

  // Refresh data every 5 seconds
  useEffect(() => {
    const interval = setInterval(async () => {
      if (selectedSymbol) {
        try {
          const [indicatorsRes, orderBookRes] = await Promise.all([
            marketApi.getIndicators(selectedSymbol),
            marketApi.getOrderBook(selectedSymbol),
          ]);
          setIndicators(indicatorsRes.data);
          setOrderBook(orderBookRes.data);
          setLastUpdate(new Date());
        } catch (error) {
          console.error('Failed to refresh data:', error);
        }
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [selectedSymbol]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market State</h1>
          <p className="text-sm text-gray-500 mt-1">
            Real-time market conditions and indicators
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <div
              className={`h-2 w-2 rounded-full ${
                isConnected ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-gray-600">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          <span className="text-sm text-gray-500">
            Last update: {lastUpdate.toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* Market Regime */}
      <MarketRegimeIndicator regime={marketRegime} />

      {/* Symbol Watchlist */}
      <SymbolWatchlist
        symbols={symbols}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={setSelectedSymbol}
      />

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Technical Indicators */}
        <TechnicalIndicators indicators={indicators} />

        {/* Order Book Heatmap */}
        <OrderBookHeatmap orderBook={orderBook} />
      </div>

      {/* Bottom Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* News Sentiment */}
        <NewsSentiment symbol={selectedSymbol} />

        {/* Economic Calendar */}
        <EconomicCalendar />
      </div>
    </div>
  );
}
