import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { ModelMetadata } from '../types';

interface FeatureImportanceChartProps {
  model: ModelMetadata | null;
}

export default function FeatureImportanceChart({ model }: FeatureImportanceChartProps) {
  if (!model || !(model as any).feature_names) return null;

  // Mock feature importance data
  const featureNames = (model as any).feature_names as string[];
  const data = featureNames.slice(0, 10).map((name: string) => ({
    name,
    importance: Math.random() * 100,
  })).sort((a: any, b: any) => b.importance - a.importance);

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Feature Importance (SHAP)</h3>
      </div>
      <div className="p-6">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={100} />
            <Tooltip />
            <Bar dataKey="importance" fill="#0ea5e9" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
