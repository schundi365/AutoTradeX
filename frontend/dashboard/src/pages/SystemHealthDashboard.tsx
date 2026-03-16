import { useState, useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { healthApi } from '../api/client';
import DataPipelineMetrics from '../components/DataPipelineMetrics';
import SystemHealthIndicators from '../components/SystemHealthIndicators';
import ConnectionStatus from '../components/ConnectionStatus';
import AlertHistory from '../components/AlertHistory';

export default function SystemHealthDashboard() {
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const { isConnected } = useWebSocket('ws://localhost:8000/ws/dashboard', {
    onMessage: (message) => {
      if (message.type === 'alert' || message.type === 'performance_update') {
        setLastUpdate(new Date());
      }
    },
  });

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const response = await healthApi.check();
        setHealthStatus(response.data);
      } catch (error) {
        console.error('Failed to load health status:', error);
      }
    };
    loadHealth();
  }, []);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const response = await healthApi.check();
        setHealthStatus(response.data);
        setLastUpdate(new Date());
      } catch (error) {
        console.error('Failed to refresh health status:', error);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Health</h1>
          <p className="text-sm text-gray-500 mt-1">Operational monitoring and alerts</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-600">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
          <span className="text-sm text-gray-500">Last update: {lastUpdate.toLocaleTimeString()}</span>
        </div>
      </div>

      <ConnectionStatus isConnected={isConnected} healthStatus={healthStatus} />
      <SystemHealthIndicators />
      <DataPipelineMetrics />
      <AlertHistory />
    </div>
  );
}
