export default function AlertHistory() {
  // Mock alert history
  const alerts = [
    {
      timestamp: new Date().toISOString(),
      type: 'Data Quality',
      message: 'Price spike detected on XAUUSD',
      severity: 'warning',
    },
    {
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      type: 'Performance',
      message: 'Processing latency exceeded 500ms',
      severity: 'warning',
    },
    {
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      type: 'System',
      message: 'High memory usage detected',
      severity: 'info',
    },
  ];

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800';
      case 'error':
        return 'bg-red-50 text-red-700';
      case 'warning':
        return 'bg-yellow-50 text-yellow-700';
      default:
        return 'bg-blue-50 text-blue-700';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Alert History (Last 7 Days)</h3>
      </div>
      <div className="p-6">
        <div className="space-y-3">
          {alerts.map((alert, index) => (
            <div
              key={index}
              className={`p-4 rounded-lg border ${getSeverityColor(alert.severity)}`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <p className="text-xs font-medium uppercase tracking-wide mb-1">{alert.type}</p>
                  <p className="text-sm">{alert.message}</p>
                </div>
                <span className="text-xs opacity-75">
                  {new Date(alert.timestamp).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
