export default function DataPipelineMetrics() {
  const metrics = [
    { label: 'Processing Latency', value: '45ms', target: '<500ms' },
    { label: 'Queue Depth', value: '12', target: '<1000' },
    { label: 'Throughput', value: '250/s', target: '>100/s' },
    { label: 'Error Rate', value: '0.1%', target: '<1%' },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Data Pipeline Metrics</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          {metrics.map((metric) => (
            <div key={metric.label}>
              <p className="text-xs text-gray-500 uppercase tracking-wide">{metric.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{metric.value}</p>
              <p className="text-xs text-gray-500 mt-1">Target: {metric.target}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
