import { useState, useEffect } from 'react';
import {
  PlayIcon,
  StopIcon,
  ArrowPathIcon,
  PauseIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { apiClient } from '../api/client';

interface BotStatus {
  status: 'running' | 'stopped' | 'paused' | 'error';
  uptime_seconds: number;
  last_started: string;
  last_stopped?: string;
  active_positions: number;
  pending_orders: number;
  error_message?: string;
}

interface ActivityLog {
  id: string;
  timestamp: string;
  activity_type: string;
  component: string;
  description: string;
  status: 'success' | 'running' | 'failed' | 'pending';
  details?: Record<string, any>;
}

interface ScheduledJob {
  job_id: string;
  job_name: string;
  job_type: 'model_training' | 'data_collection' | 'rebalancing' | 'health_check';
  schedule: string;
  last_run?: string;
  next_run: string;
  status: 'active' | 'paused' | 'failed';
  last_duration_seconds?: number;
}

interface AsyncJob {
  job_id: string;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  started_at: string;
  completed_at?: string;
  result?: any;
  error?: string;
}

export default function BotControlDashboard() {
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [scheduledJobs, setScheduledJobs] = useState<ScheduledJob[]>([]);
  const [asyncJobs, setAsyncJobs] = useState<AsyncJob[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedTab, setSelectedTab] = useState<'activity' | 'scheduled' | 'async'>('activity');

  const fetchBotStatus = async () => {
    try {
      const response = await apiClient.get('/bot/status');
      setBotStatus(response.data);
    } catch (error) {
      console.error('Failed to fetch bot status:', error);
    }
  };

  const fetchActivityLogs = async () => {
    try {
      const response = await apiClient.get('/bot/activity', {
        params: { limit: 100 },
      });
      setActivityLogs(response.data.activities || []);
    } catch (error) {
      console.error('Failed to fetch activity logs:', error);
    }
  };

  const fetchScheduledJobs = async () => {
    try {
      const response = await apiClient.get('/bot/scheduled-jobs');
      setScheduledJobs(response.data.jobs || []);
    } catch (error) {
      console.error('Failed to fetch scheduled jobs:', error);
    }
  };

  const fetchAsyncJobs = async () => {
    try {
      const response = await apiClient.get('/bot/async-jobs');
      setAsyncJobs(response.data.jobs || []);
    } catch (error) {
      console.error('Failed to fetch async jobs:', error);
    }
  };

  useEffect(() => {
    fetchBotStatus();
    fetchActivityLogs();
    fetchScheduledJobs();
    fetchAsyncJobs();

    const interval = setInterval(() => {
      fetchBotStatus();
      fetchActivityLogs();
      fetchScheduledJobs();
      fetchAsyncJobs();
    }, 5000); // Refresh every 5 seconds

    return () => clearInterval(interval);
  }, []);

  const handleStartBot = async () => {
    if (!confirm('Are you sure you want to START the trading bot?')) return;
    setIsLoading(true);
    try {
      await apiClient.post('/bot/start');
      await fetchBotStatus();
      alert('Bot started successfully');
    } catch (error: any) {
      alert(`Failed to start bot: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopBot = async () => {
    if (!confirm('Are you sure you want to STOP the trading bot? This will close all positions.')) return;
    setIsLoading(true);
    try {
      await apiClient.post('/bot/stop');
      await fetchBotStatus();
      alert('Bot stopped successfully');
    } catch (error: any) {
      alert(`Failed to stop bot: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePauseBot = async () => {
    if (!confirm('Are you sure you want to PAUSE the trading bot? Existing positions remain open.')) return;
    setIsLoading(true);
    try {
      await apiClient.post('/bot/pause');
      await fetchBotStatus();
      alert('Bot paused successfully');
    } catch (error: any) {
      alert(`Failed to pause bot: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRestartBot = async () => {
    if (!confirm('Are you sure you want to RESTART the trading bot?')) return;
    setIsLoading(true);
    try {
      await apiClient.post('/bot/restart');
      await fetchBotStatus();
      alert('Bot restarted successfully');
    } catch (error: any) {
      alert(`Failed to restart bot: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePauseJob = async (jobId: string) => {
    try {
      await apiClient.post(`/bot/scheduled-jobs/${jobId}/pause`);
      await fetchScheduledJobs();
    } catch (error) {
      alert('Failed to pause job');
    }
  };

  const handleResumeJob = async (jobId: string) => {
    try {
      await apiClient.post(`/bot/scheduled-jobs/${jobId}/resume`);
      await fetchScheduledJobs();
    } catch (error) {
      alert('Failed to resume job');
    }
  };

  const handleRunJobNow = async (jobId: string) => {
    if (!confirm('Run this job immediately?')) return;
    try {
      await apiClient.post(`/bot/scheduled-jobs/${jobId}/run-now`);
      await fetchScheduledJobs();
      alert('Job triggered successfully');
    } catch (error) {
      alert('Failed to trigger job');
    }
  };

  const handleCancelAsyncJob = async (jobId: string) => {
    if (!confirm('Cancel this job?')) return;
    try {
      await apiClient.post(`/bot/async-jobs/${jobId}/cancel`);
      await fetchAsyncJobs();
    } catch (error) {
      alert('Failed to cancel job');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
      case 'active':
      case 'success':
      case 'completed':
        return 'text-green-600 bg-green-100';
      case 'stopped':
      case 'paused':
      case 'pending':
        return 'text-yellow-600 bg-yellow-100';
      case 'error':
      case 'failed':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
      case 'active':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'success':
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'stopped':
      case 'paused':
        return <PauseIcon className="h-5 w-5 text-yellow-500" />;
      case 'pending':
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
      case 'error':
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
      default:
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hours}h ${minutes}m ${secs}s`;
  };

  if (!botStatus) {
    return (
      <div className="flex items-center justify-center h-64">
        <ArrowPathIcon className="h-8 w-8 text-gray-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Bot Control & Activity Monitor</h1>
        <p className="mt-1 text-sm text-gray-500">
          Monitor all bot activities and control bot lifecycle
        </p>
      </div>

      {/* Bot Status Card */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="flex-shrink-0">
                {getStatusIcon(botStatus.status)}
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Bot Status</h2>
                <div className="flex items-center space-x-2 mt-1">
                  <span
                    className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(
                      botStatus.status
                    )}`}
                  >
                    {botStatus.status.toUpperCase()}
                  </span>
                  {botStatus.status === 'running' && (
                    <span className="text-sm text-gray-500">
                      Uptime: {formatUptime(botStatus.uptime_seconds)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Control Buttons */}
            <div className="flex space-x-2">
              {botStatus.status === 'stopped' && (
                <button
                  onClick={handleStartBot}
                  disabled={isLoading}
                  className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
                >
                  <PlayIcon className="h-5 w-5 mr-2" />
                  Start Bot
                </button>
              )}
              {botStatus.status === 'running' && (
                <>
                  <button
                    onClick={handlePauseBot}
                    disabled={isLoading}
                    className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-yellow-600 hover:bg-yellow-700 disabled:opacity-50"
                  >
                    <PauseIcon className="h-5 w-5 mr-2" />
                    Pause
                  </button>
                  <button
                    onClick={handleStopBot}
                    disabled={isLoading}
                    className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
                  >
                    <StopIcon className="h-5 w-5 mr-2" />
                    Stop
                  </button>
                </>
              )}
              {botStatus.status === 'paused' && (
                <>
                  <button
                    onClick={handleStartBot}
                    disabled={isLoading}
                    className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
                  >
                    <PlayIcon className="h-5 w-5 mr-2" />
                    Resume
                  </button>
                  <button
                    onClick={handleStopBot}
                    disabled={isLoading}
                    className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
                  >
                    <StopIcon className="h-5 w-5 mr-2" />
                    Stop
                  </button>
                </>
              )}
              <button
                onClick={handleRestartBot}
                disabled={isLoading}
                className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
              >
                <ArrowPathIcon className="h-5 w-5 mr-2" />
                Restart
              </button>
            </div>
          </div>

          {/* Status Details */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-sm font-medium text-gray-500">Active Positions</div>
              <div className="mt-1 text-2xl font-semibold text-gray-900">
                {botStatus.active_positions}
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-sm font-medium text-gray-500">Pending Orders</div>
              <div className="mt-1 text-2xl font-semibold text-gray-900">
                {botStatus.pending_orders}
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-sm font-medium text-gray-500">Last Started</div>
              <div className="mt-1 text-sm font-medium text-gray-900">
                {new Date(botStatus.last_started).toLocaleString()}
              </div>
            </div>
            {botStatus.last_stopped && (
              <div className="bg-gray-50 rounded-lg p-3">
                <div className="text-sm font-medium text-gray-500">Last Stopped</div>
                <div className="mt-1 text-sm font-medium text-gray-900">
                  {new Date(botStatus.last_stopped).toLocaleString()}
                </div>
              </div>
            )}
          </div>

          {botStatus.error_message && (
            <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">Error</h3>
                  <div className="mt-1 text-sm text-red-700">{botStatus.error_message}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setSelectedTab('activity')}
            className={`${
              selectedTab === 'activity'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            Activity Log ({activityLogs.length})
          </button>
          <button
            onClick={() => setSelectedTab('scheduled')}
            className={`${
              selectedTab === 'scheduled'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            Scheduled Jobs ({scheduledJobs.length})
          </button>
          <button
            onClick={() => setSelectedTab('async')}
            className={`${
              selectedTab === 'async'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            Async Jobs ({asyncJobs.filter((j) => j.status === 'running' || j.status === 'pending').length})
          </button>
        </nav>
      </div>

      {/* Activity Log Tab */}
      {selectedTab === 'activity' && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Component
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Description
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {activityLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      <span className="capitalize">{log.activity_type.replace(/_/g, ' ')}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {log.component}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      <div>{log.description}</div>
                      {log.details && Object.keys(log.details).length > 0 && (
                        <div className="mt-2 space-y-1">
                          {log.details.symbol && (
                            <div className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 mr-2">
                              {log.details.symbol}
                            </div>
                          )}
                          {log.details.direction && (
                            <div className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mr-2 ${
                              log.details.direction === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                            }`}>
                              {log.details.direction}
                            </div>
                          )}
                          {log.details.score !== undefined && (
                            <div className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 mr-2">
                              Score: {log.details.score}
                            </div>
                          )}
                          {log.details.ticket && (
                            <div className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-gray-100 text-gray-800 mr-2">
                              #{log.details.ticket}
                            </div>
                          )}
                          {log.details.action && (
                            <div className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 mr-2">
                              {log.details.action}
                            </div>
                          )}
                          {log.details.reason && (
                            <div className="mt-1 text-xs text-gray-600 italic">
                              {log.details.reason}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                          log.status
                        )}`}
                      >
                        {log.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Scheduled Jobs Tab */}
      {selectedTab === 'scheduled' && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Job Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Schedule
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Run
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Next Run
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {scheduledJobs.map((job) => (
                  <tr key={job.job_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {job.job_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {job.job_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {job.schedule}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {job.last_run ? new Date(job.last_run).toLocaleString() : 'Never'}
                      {job.last_duration_seconds && (
                        <div className="text-xs text-gray-400">
                          ({job.last_duration_seconds}s)
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(job.next_run).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                          job.status
                        )}`}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                      {job.status === 'active' ? (
                        <button
                          onClick={() => handlePauseJob(job.job_id)}
                          className="text-yellow-600 hover:text-yellow-900"
                        >
                          Pause
                        </button>
                      ) : (
                        <button
                          onClick={() => handleResumeJob(job.job_id)}
                          className="text-green-600 hover:text-green-900"
                        >
                          Resume
                        </button>
                      )}
                      <button
                        onClick={() => handleRunJobNow(job.job_id)}
                        className="text-primary-600 hover:text-primary-900"
                      >
                        Run Now
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Async Jobs Tab */}
      {selectedTab === 'async' && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Job ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Progress
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Started
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {asyncJobs.map((job) => (
                  <tr key={job.job_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                      {job.job_id.substring(0, 8)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {job.job_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        {getStatusIcon(job.status)}
                        <span className="ml-2 text-sm text-gray-900">{job.status}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className="bg-primary-600 h-2 rounded-full"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500">{job.progress}%</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(job.started_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      {(job.status === 'running' || job.status === 'pending') && (
                        <button
                          onClick={() => handleCancelAsyncJob(job.job_id)}
                          className="text-red-600 hover:text-red-900"
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
