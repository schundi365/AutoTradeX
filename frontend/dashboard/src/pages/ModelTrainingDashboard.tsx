import { useState, useEffect } from 'react';
import {
  PlayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  RocketLaunchIcon,
} from '@heroicons/react/24/outline';
import { apiClient } from '../api/client';
import DataCollectionPanel from '../components/DataCollectionPanel';

interface TrainingJob {
  job_id: string;
  model_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  started_at: string;
  completed_at?: string;
  metrics?: {
    accuracy?: number;
    precision?: number;
    recall?: number;
    f1_score?: number;
    roc_auc?: number;
  };
  error?: string;
}

interface ModelDeployment {
  model_id: string;
  model_name: string;
  version: string;
  status: 'training' | 'testing' | 'production' | 'retired';
  environment: 'paper' | 'live';
  deployed_at?: string;
}

export default function ModelTrainingDashboard() {
  const [trainingJobs, setTrainingJobs] = useState<TrainingJob[]>([]);
  const [deployments, setDeployments] = useState<ModelDeployment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModelType, setSelectedModelType] = useState('XGBOOST');
  const [trainingParams, setTrainingParams] = useState({
    lookback_months: 6,
    validation_split: 0.2,
    hyperparameter_tuning: true,
  });

  const MODEL_TYPES = ['XGBOOST', 'LIGHTGBM', 'RANDOM_FOREST', 'PPO_RL'];

  const fetchTrainingJobs = async () => {
    try {
      const response = await apiClient.get('/training/jobs');
      setTrainingJobs(response.data.jobs || []);
    } catch (error) {
      console.error('Failed to fetch training jobs:', error);
    }
  };

  const fetchDeployments = async () => {
    try {
      const response = await apiClient.get('/training/deployments');
      setDeployments(response.data.deployments || []);
    } catch (error) {
      console.error('Failed to fetch deployments:', error);
    }
  };

  useEffect(() => {
    fetchTrainingJobs();
    fetchDeployments();
    const interval = setInterval(() => {
      fetchTrainingJobs();
      fetchDeployments();
    }, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const handleStartTraining = async () => {
    setIsLoading(true);
    try {
      await apiClient.post('/training/start', {
        model_type: selectedModelType,
        ...trainingParams,
      });
      await fetchTrainingJobs();
    } catch (error) {
      console.error('Failed to start training:', error);
      alert('Failed to start training. Check logs for details.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeployModel = async (modelId: string, environment: 'paper' | 'live') => {
    if (
      environment === 'live' &&
      !confirm('Are you sure you want to deploy to LIVE trading? This will affect real money.')
    ) {
      return;
    }

    try {
      await apiClient.post(`/training/deploy/${modelId}`, { environment });
      await fetchDeployments();
      alert(`Model deployed to ${environment.toUpperCase()} successfully`);
    } catch (error) {
      console.error('Failed to deploy model:', error);
      alert('Failed to deploy model. Check logs for details.');
    }
  };

  const handleRetireModel = async (modelId: string) => {
    if (!confirm('Are you sure you want to retire this model?')) {
      return;
    }

    try {
      await apiClient.post(`/training/retire/${modelId}`);
      await fetchDeployments();
    } catch (error) {
      console.error('Failed to retire model:', error);
      alert('Failed to retire model. Check logs for details.');
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 text-blue-500 animate-spin" />;
      default:
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      training: 'bg-blue-100 text-blue-800',
      testing: 'bg-yellow-100 text-yellow-800',
      production: 'bg-green-100 text-green-800',
      retired: 'bg-gray-100 text-gray-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Model Training & Deployment</h1>
        <p className="mt-1 text-sm text-gray-500">
          Train new ML models and manage deployments
        </p>
      </div>

      {/* Data Collection Panel */}
      <DataCollectionPanel />

      {/* Training Configuration */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Start New Training</h2>
        </div>
        <div className="px-4 py-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Model Type
              </label>
              <select
                value={selectedModelType}
                onChange={(e) => setSelectedModelType(e.target.value)}
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              >
                {MODEL_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Lookback Period (months)
              </label>
              <input
                type="number"
                min="1"
                max="24"
                value={trainingParams.lookback_months}
                onChange={(e) =>
                  setTrainingParams({ ...trainingParams, lookback_months: parseInt(e.target.value) })
                }
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Validation Split
              </label>
              <input
                type="number"
                min="0.1"
                max="0.5"
                step="0.05"
                value={trainingParams.validation_split}
                onChange={(e) =>
                  setTrainingParams({ ...trainingParams, validation_split: parseFloat(e.target.value) })
                }
                className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
            <div className="flex items-center">
              <input
                id="hyperparameter-tuning"
                type="checkbox"
                checked={trainingParams.hyperparameter_tuning}
                onChange={(e) =>
                  setTrainingParams({ ...trainingParams, hyperparameter_tuning: e.target.checked })
                }
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <label htmlFor="hyperparameter-tuning" className="ml-2 block text-sm text-gray-700">
                Enable Hyperparameter Tuning
              </label>
            </div>
          </div>
          <div className="mt-4">
            <button
              onClick={handleStartTraining}
              disabled={isLoading}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
            >
              <PlayIcon className="h-5 w-5 mr-2" />
              Start Training
            </button>
          </div>
        </div>
      </div>

      {/* Training Jobs */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Training Jobs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Job ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Model Type
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
                  Metrics
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {trainingJobs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-4 text-center text-sm text-gray-500">
                    No training jobs found. Start a new training above.
                  </td>
                </tr>
              ) : (
                trainingJobs.map((job) => (
                  <tr key={job.job_id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                      {job.job_id.substring(0, 8)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {job.model_type}
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
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {job.metrics ? (
                        <div className="space-y-1">
                          {job.metrics.accuracy && (
                            <div>Acc: {(job.metrics.accuracy * 100).toFixed(2)}%</div>
                          )}
                          {job.metrics.f1_score && (
                            <div>F1: {job.metrics.f1_score.toFixed(3)}</div>
                          )}
                        </div>
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

      {/* Model Deployments */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Model Deployments</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Model
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Version
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Environment
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Deployed
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {deployments.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-4 text-center text-sm text-gray-500">
                    No deployed models found.
                  </td>
                </tr>
              ) : (
                deployments.map((deployment) => (
                  <tr key={deployment.model_id}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {deployment.model_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      v{deployment.version}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(
                          deployment.status
                        )}`}
                      >
                        {deployment.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          deployment.environment === 'live'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-yellow-100 text-yellow-800'
                        }`}
                      >
                        {deployment.environment.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {deployment.deployed_at
                        ? new Date(deployment.deployed_at).toLocaleString()
                        : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                      {deployment.status !== 'production' && (
                        <>
                          <button
                            onClick={() => handleDeployModel(deployment.model_id, 'paper')}
                            className="text-yellow-600 hover:text-yellow-900"
                          >
                            Deploy to Paper
                          </button>
                          <button
                            onClick={() => handleDeployModel(deployment.model_id, 'live')}
                            className="text-red-600 hover:text-red-900"
                          >
                            Deploy to Live
                          </button>
                        </>
                      )}
                      {deployment.status === 'production' && (
                        <button
                          onClick={() => handleRetireModel(deployment.model_id)}
                          className="text-gray-600 hover:text-gray-900"
                        >
                          Retire
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <RocketLaunchIcon className="h-5 w-5 text-blue-400" />
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-blue-800">Training & Deployment Guide</h3>
            <div className="mt-2 text-sm text-blue-700">
              <ol className="list-decimal list-inside space-y-1">
                <li>Configure training parameters and select model type</li>
                <li>Click "Start Training" to begin model training (takes 10-30 minutes)</li>
                <li>Monitor training progress in the "Training Jobs" table</li>
                <li>Once completed, review metrics (accuracy should be &gt; 52%)</li>
                <li>Deploy to "Paper" environment first for testing</li>
                <li>After validation, deploy to "Live" for real trading</li>
                <li>Monitor model performance in the "Model Performance" dashboard</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
