export default function SystemHealthIndicators() {
  const indicators = [
    { label: 'CPU Usage', value: '45%', status: 'good' },
    { label: 'Memory Usage', value: '62%', status: 'good' },
    { label: 'Disk Usage', value: '78%', status: 'warning' },
    { label: 'Network Latency', value: '12ms', status: 'good' },
  ];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'good':
        return 'text-green-600';
      case 'warning':
        return 'text-yellow-600';
      case 'error':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">System Health Indicators</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {indicators.map((indicator) => (
            <div key={indicator.label} className="text-center">
              <p className="text-sm text-gray-500">{indicator.label}</p>
              <p className={`text-3xl font-bold mt-2 ${getStatusColor(indicator.status)}`}>
                {indicator.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
