import { ModelMetadata } from '../types';

interface CurrentModelInfoProps {
  model: ModelMetadata | null;
}

export default function CurrentModelInfo({ model }: CurrentModelInfoProps) {
  if (!model) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Current Model</h3>
        <p className="text-sm text-gray-500">No model deployed</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Currently Deployed Model</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Model Name</p>
            <p className="text-lg font-medium text-gray-900 mt-1">{model.model_name}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Type</p>
            <p className="text-lg font-medium text-gray-900 mt-1">{model.model_type}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Version</p>
            <p className="text-lg font-medium text-gray-900 mt-1">v{model.version}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Environment</p>
            <p className="text-lg font-medium text-gray-900 mt-1">{model.deployment_environment}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
