import { ModelMetadata } from '../types';

interface ModelMetricsChartProps {
  model: ModelMetadata | null;
}

export default function ModelMetricsChart({ model }: ModelMetricsChartProps) {
  if (!model) return null;

  const metrics = [
    { label: 'Train Accuracy', value: model.train_metrics?.accuracy || 0 },
    { label: 'Val Accuracy', value: model.validation_metrics?.accuracy || 0 },
    { label: 'Test Accuracy', value: model.test_metrics?.accuracy || 0 },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Model Performance Metrics</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-3 gap-6">
          {metrics.map((metric) => (
            <div key={metric.label} className="text-center">
              <p className="text-sm text-gray-500">{metric.label}</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {(metric.value * 100).toFixed(1)}%
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
