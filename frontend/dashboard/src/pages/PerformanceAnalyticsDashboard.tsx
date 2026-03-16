import { useState, useEffect } from 'react';
import { performanceApi } from '../api/client';
import { PerformanceMetrics, EquityCurvePoint, Trade } from '../types';
import { useWebSocket } from '../hooks/useWebSocket';
import EquityCurveChart from '../components/EquityCurveChart';
import PerformanceMetricsTable from '../components/PerformanceMetricsTable';
import TradeDistributionCharts from '../components/TradeDistributionCharts';
import PerformanceBreakdown from '../components/PerformanceBreakdown';
import RollingPerformance from '../components/RollingPerformance';

export default function PerformanceAnalyticsDashboard() {
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // WebSocket for real-time updates
  const { isConnected } = useWebSocket('ws://localhost:8000/ws/dashboard', {
    onMessage: (message) => {
      if (message.type === 'performance_update') {
        setMetrics(message.data);
        setLastUpdate(new Date());
      }
    },
  });

  // Load initial data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [metricsRes, equityRes, tradesRes] = await Promise.all([
          performanceApi.getMetrics(),
          performanceApi.getEquityCurve(),
          performanceApi.getTrades({ limit: 100 }),
        ]);
        setMetrics(metricsRes.data);
        setEquityCurve(equityRes.data.data || []);
        setTrades(tradesRes.data.trades || []);
      } catch (error) {
        console.error('Failed to load performance data:', error);
        setError('Failed to load performance data. Please ensure the trading bot is running.');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  // Refresh every 1 minute
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const metricsRes = await performanceApi.getMetrics();
        setMetrics(metricsRes.data);
        setLastUpdate(new Date());
      } catch (error) {
        console.error('Failed to refresh metrics:', error);
      }
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Performance Analytics</h1>
          <p className="text-sm text-gray-500 mt-1">
            Comprehensive performance analysis and metrics
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

      {/* Loading State */}
      {loading && (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading performance data...</p>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="h-5 w-5 text-red-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <p className="text-red-800">{error}</p>
          </div>
        </div>
      )}

      {/* No Data State */}
      {!loading && !error && trades.length === 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-8 text-center">
          <svg className="h-16 w-16 text-blue-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Trading Data Yet</h3>
          <p className="text-gray-600">Start the trading bot to see performance analytics and trade history.</p>
        </div>
      )}

      {/* Performance Metrics */}
      {!loading && !error && trades.length > 0 && (
        <>
          <PerformanceMetricsTable metrics={metrics} />

          {/* Equity Curve */}
          <EquityCurveChart data={equityCurve} />

          {/* Trade Distribution */}
          <TradeDistributionCharts trades={trades} />

          {/* Performance Breakdown */}
          <PerformanceBreakdown trades={trades} />

          {/* Rolling Performance */}
          <RollingPerformance trades={trades} />
        </>
      )}
    </div>
  );
}
