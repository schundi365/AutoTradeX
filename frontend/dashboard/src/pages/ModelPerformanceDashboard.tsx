import { useState, useEffect } from 'react';
import { modelsApi } from '../api/client';
import { ModelMetadata } from '../types';
import { useWebSocket } from '../hooks/useWebSocket';
import CurrentModelInfo from '../components/CurrentModelInfo';
import ModelMetricsChart from '../components/ModelMetricsChart';
import FeatureImportanceChart from '../components/FeatureImportanceChart';
import ModelRetrainingHistory from '../components/ModelRetrainingHistory';

export default function ModelPerformanceDashboard() {
  const [currentModel, setCurrentModel] = useState<ModelMetadata | null>(null);
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const { isConnected } = useWebSocket('ws://localhost:8000/ws/dashboard', {
    onMessage: (message) => {
      if (message.type === 'model_update') {
        setLastUpdate(new Date());
      }
    },
    onConnect: () => {
      console.log('Model Performance WebSocket connected');
    },
    onDisconnect: () => {
      console.log('Model Performance WebSocket disconnected');
    },
  });

  useEffect(() => {
    const loadData = async () => {
      try {
        const [currentRes, modelsRes] = await Promise.all([
          modelsApi.getCurrentModel(),
          modelsApi.getModels({ deployment_status: 'PRODUCTION' }),
        ]);
        if (currentRes.data.model_id) {
          setCurrentModel(currentRes.data as ModelMetadata);
        }
        setModels(modelsRes.data.models);
      } catch (error) {
        console.error('Failed to load model data:', error);
      }
    };
    loadData();
  }, []);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const currentRes = await modelsApi.getCurrentModel();
        if (currentRes.data.model_id) {
          setCurrentModel(currentRes.data as ModelMetadata);
        }
        setLastUpdate(new Date());
      } catch (error) {
        console.error('Failed to refresh model data:', error);
      }
    }, 300000); // 5 minutes

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Model Performance</h1>
          <p className="text-sm text-gray-500 mt-1">ML model monitoring and analysis</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-600">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
          <span className="text-sm text-gray-500">Last update: {lastUpdate.toLocaleTimeString()}</span>
        </div>
      </div>

      <CurrentModelInfo model={currentModel} />
      <ModelMetricsChart model={currentModel} />
      <FeatureImportanceChart model={currentModel} />
      <ModelRetrainingHistory models={models} />
    </div>
  );
}
