import { useState, useEffect } from 'react';
import {
  CloudArrowDownIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  InformationCircleIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import axios from 'axios';

interface DataCoverage {
  symbol: string;
  timeframe: string;
  bars: number;
  start_date: string;
  end_date: string;
  days_covered: number;
  years_covered: number;
  sufficient: boolean;
}

interface CollectionJob {
  job_id: string;
  type: string;
  status: 'queued' | 'running' | 'done' | 'error';
  started_at: string;
  bars_collected?: number;
  symbols?: number;
  error?: string;
}

export default function DataCollectionPanel() {
  const [coverage, setCoverage] = useState<DataCoverage[]>([]);
  const [jobs, setJobs] = useState<CollectionJob[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState('XAUUSD');
  const [years, setYears] = useState(2);
  const [timeframe, setTimeframe] = useState('1h');
  const [collectAll, setCollectAll] = useState(false);

  const SYMBOLS = ['XAUUSD', 'XAGUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD', 'ETHUSD'];
  const TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '1d'];

  const fetchCoverage = async () => {
    try {
      const response = await axios.get('/api/training/data/coverage');
      if (response.data.status === 'success') {
        setCoverage(response.data.coverage || []);
      }
    } catch (error) {
      console.error('Failed to fetch data coverage:', error);
    }
  };

  const fetchJobs = async () => {
    try {
      const response = await axios.get('/api/training/status');
      const allJobs = Object.entries(response.data.jobs || {}).map(([id, job]: [string, any]) => ({
        job_id: id,
        ...job,
      }));
      // Filter for collection jobs
      const collectionJobs = allJobs.filter(
        (job: CollectionJob) =>
          job.type === 'collect_extended' || job.type === 'collect_historical'
      );
      setJobs(collectionJobs);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    }
  };

  useEffect(() => {
    fetchCoverage();
    fetchJobs();
    const interval = setInterval(() => {
      fetchCoverage();
      fetchJobs();
    }, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const handleStartCollection = async () => {
    setIsLoading(true);
    try {
      await axios.post('/api/training/collect/extended', {
        symbol: selectedSymbol,
        years,
        timeframe,
        all_symbols: collectAll,
      });
      await fetchJobs();
      alert('Data collection started! Check progress below.');
    } catch (error) {
      console.error('Failed to start collection:', error);
      alert('Failed to start data collection. Check logs for details.');
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'done':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'error':
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 text-blue-500 animate-spin" />;
      default:
        return <CloudArrowDownIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const getExpectedBars = (tf: string, yrs: number): number => {
    const barsPerYear: Record<string, number> = {
      '15m': 35040,
      '30m': 17520,
      '1h': 8760,
      '2h': 4380,
      '4h': 2190,
      '1d': 365,
    };
    return (barsPerYear[tf] || 8760) * yrs;
  };

  return (
    <div className="space-y-6">
      {/* Collection Configuration */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Extended Data Collection</h2>
          <p className="mt-1 text-sm text-gray-500">
            Collect 2+ years of historical data for ML training
          </p>
        </div>
        <div className="px-4 py-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Symbol
              </label>
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                disabled={collectAll}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm disabled:bg-gray-100"
              >
                {SYMBOLS.map((sym) => (
                  <option key={sym} value={sym}>
                    {sym}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Years of History
              </label>
              <input
                type="number"
                min="1"
                max="5"
                value={years}
                onChange={(e) => setYears(parseInt(e.target.value))}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Timeframe
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500">
                Expected: ~{getExpectedBars(timeframe, years).toLocaleString()} bars
              </p>
            </div>
            <div className="flex items-center">
              <input
                id="collect-all"
                type="checkbox"
                checked={collectAll}
                onChange={(e) => setCollectAll(e.target.checked)}
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <label htmlFor="collect-all" className="ml-2 block text-sm text-gray-700">
                Collect all configured symbols
              </label>
            </div>
          </div>
          <div className="mt-4 flex items-center space-x-4">
            <button
              onClick={handleStartCollection}
              disabled={isLoading}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              <CloudArrowDownIcon className="h-5 w-5 mr-2" />
              Start Collection
            </button>
            <button
              onClick={fetchCoverage}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
            >
              <ArrowPathIcon className="h-5 w-5 mr-2" />
              Refresh Coverage
            </button>
          </div>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <InformationCircleIcon className="h-5 w-5 text-blue-400" />
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">Why Extended Collection?</h3>
            <div className="mt-2 text-sm text-blue-700">
              <p>
                Yahoo Finance limits intraday data to 60 days (~3,600 bars). ML models need
                10,000+ bars for effective training. Extended collection solves this by:
              </p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>Fetching daily data for full history (2+ years)</li>
                <li>Resampling to your target timeframe</li>
                <li>Adding recent intraday data for accuracy</li>
                <li>Providing sufficient data for XGBoost, LightGBM, and PPO training</li>
              </ul>
              <p className="mt-2 font-medium">
                Recommended: Use 1h timeframe for best quality (true intraday data)
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Collection Jobs */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Collection Jobs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Job ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Started
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Results
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-4 text-center text-sm text-gray-500">
                    No collection jobs found. Start a collection above.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.job_id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                      {job.job_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        {getStatusIcon(job.status)}
                        <span className="ml-2 text-sm text-gray-900">{job.status}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(job.started_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {job.status === 'done' && job.bars_collected ? (
                        <div>
                          {job.bars_collected.toLocaleString()} bars
                          {job.symbols && ` (${job.symbols} symbols)`}
                        </div>
                      ) : job.status === 'error' ? (
                        <span className="text-red-600">{job.error}</span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Data Coverage */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-medium text-gray-900">Data Coverage</h2>
          <ChartBarIcon className="h-5 w-5 text-gray-400" />
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Symbol
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Timeframe
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Bars
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Coverage
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {coverage.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-4 text-center text-sm text-gray-500">
                    No data found. Collect historical data first.
                  </td>
                </tr>
              ) : (
                coverage.map((item, idx) => (
                  <tr key={idx} className={item.sufficient ? '' : 'bg-yellow-50'}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {item.symbol}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {item.timeframe}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {item.bars.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {item.years_covered} years ({item.days_covered} days)
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {item.sufficient ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          <CheckCircleIcon className="h-4 w-4 mr-1" />
                          Sufficient
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                          <XCircleIcon className="h-4 w-4 mr-1" />
                          Need more data
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {coverage.length > 0 && (
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-200">
            <p className="text-sm text-gray-600">
              <strong>Note:</strong> ML models need 10,000+ bars for effective training.
              Insufficient data is highlighted in yellow.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
