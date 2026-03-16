import { useState } from 'react';
import { BellIcon } from '@heroicons/react/24/outline';
import { useWebSocket } from '../hooks/useWebSocket';
import { Alert } from '../types';

export default function AlertNotifications() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useWebSocket('ws://localhost:8000/ws/dashboard', {
    onMessage: (message) => {
      if (message.type === 'alert') {
        const alert: Alert = {
          type: message.type,
          alert_type: message.alert_type,
          message: message.message,
          severity: message.severity || 'info',
          timestamp: message.timestamp,
        };
        setAlerts((prev) => [alert, ...prev].slice(0, 50)); // Keep last 50 alerts
        setUnreadCount((prev) => prev + 1);
      }
    },
    onConnect: () => {
      console.log('Alert notifications WebSocket connected');
    },
    onDisconnect: () => {
      console.log('Alert notifications WebSocket disconnected');
    },
  });

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'error':
        return 'bg-red-50 text-red-700 border-red-100';
      case 'warning':
        return 'bg-yellow-50 text-yellow-700 border-yellow-100';
      default:
        return 'bg-blue-50 text-blue-700 border-blue-100';
    }
  };

  const handleDropdownToggle = () => {
    setShowDropdown(!showDropdown);
    if (!showDropdown) {
      setUnreadCount(0);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleDropdownToggle}
        className="relative p-2 text-gray-400 hover:text-gray-500 focus:outline-none"
      >
        <BellIcon className="h-6 w-6" />
        {unreadCount > 0 && (
          <span className="absolute top-0 right-0 block h-5 w-5 rounded-full bg-red-500 text-xs text-white flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {showDropdown && (
        <div className="absolute right-0 mt-2 w-96 bg-white rounded-lg shadow-lg border border-gray-200 z-50">
          <div className="px-4 py-3 border-b border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {alerts.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-500">
                No alerts
              </div>
            ) : (
              alerts.map((alert, index) => (
                <div
                  key={index}
                  className={`px-4 py-3 border-b border-gray-100 ${getSeverityColor(
                    alert.severity
                  )}`}
                >
                  <div className="flex items-start">
                    <div className="flex-1">
                      <p className="text-xs font-medium uppercase tracking-wide mb-1">
                        {alert.alert_type}
                      </p>
                      <p className="text-sm">{alert.message}</p>
                      <p className="text-xs mt-1 opacity-75">
                        {new Date(alert.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          {alerts.length > 0 && (
            <div className="px-4 py-2 border-t border-gray-200">
              <button
                onClick={() => setAlerts([])}
                className="text-xs text-primary-600 hover:text-primary-700 font-medium"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
