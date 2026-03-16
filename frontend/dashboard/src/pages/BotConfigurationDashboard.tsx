import { useState, useEffect } from 'react';
import { PencilIcon, CheckIcon, XMarkIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { apiClient } from '../api/client';

interface BotConfig {
  risk: {
    max_risk_per_trade_pct: number;
    max_combined_risk_pct: number;
    max_daily_drawdown_pct: number;
    max_consecutive_losses: number;
    min_equity_pct: number;
    max_open_trades: number;
    max_trades_per_symbol: number;
    max_lot_size: number;
    min_signal_score: number;
  };
  strategy: {
    enabled_strategies: string[];
  };
  assets: {
    metals: string[];
    commodities: string[];
    forex: string[];
    crypto: string[];
    stocks: string[];
  };
  llm: {
    provider: string;
    model: string;
    timeout: number;
  };
  environment: string;
}

export default function BotConfigurationDashboard() {
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [editingSection, setEditingSection] = useState<string | null>(null);
  const [editedValues, setEditedValues] = useState<any>({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchConfig = async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get('/config');
      setConfig(response.data);
    } catch (error) {
      console.error('Failed to fetch configuration:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleEdit = (section: string) => {
    if (!config) return;
    setEditingSection(section);
    setEditedValues({ ...(config as any)[section] });
  };

  const handleCancel = () => {
    setEditingSection(null);
    setEditedValues({});
  };

  const handleSave = async (section: string) => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await apiClient.patch(`/config/${section}`, editedValues);
      setConfig((prev) => (prev ? { ...prev, [section]: editedValues } : null));
      setEditingSection(null);
      setEditedValues({});
      setSaveMessage({ type: 'success', text: 'Configuration saved successfully' });
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (error: any) {
      console.error('Failed to save configuration:', error);
      setSaveMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Failed to save configuration',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleInputChange = (key: string, value: any) => {
    setEditedValues((prev: any) => ({ ...prev, [key]: value }));
  };

  const renderConfigSection = (title: string, section: string, data: any) => {
    const isEditing = editingSection === section;
    const values = isEditing ? editedValues : data;

    return (
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-medium text-gray-900">{title}</h2>
          {!isEditing ? (
            <button
              onClick={() => handleEdit(section)}
              className="inline-flex items-center px-3 py-1.5 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
            >
              <PencilIcon className="h-4 w-4 mr-1" />
              Edit
            </button>
          ) : (
            <div className="flex space-x-2">
              <button
                onClick={() => handleSave(section)}
                disabled={isSaving}
                className="inline-flex items-center px-3 py-1.5 border border-transparent rounded-md text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
              >
                <CheckIcon className="h-4 w-4 mr-1" />
                Save
              </button>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
              >
                <XMarkIcon className="h-4 w-4 mr-1" />
                Cancel
              </button>
            </div>
          )}
        </div>
        <div className="px-4 py-4">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {Object.entries(values).map(([key, value]) => (
              <div key={key}>
                <dt className="text-sm font-medium text-gray-500 mb-1">
                  {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                </dt>
                <dd className="text-sm text-gray-900">
                  {isEditing ? (
                    Array.isArray(value) ? (
                      <input
                        type="text"
                        value={value.join(', ')}
                        onChange={(e) =>
                          handleInputChange(
                            key,
                            e.target.value.split(',').map((v) => v.trim())
                          )
                        }
                        className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                      />
                    ) : typeof value === 'number' ? (
                      <input
                        type="number"
                        step="0.1"
                        value={value}
                        onChange={(e) => handleInputChange(key, parseFloat(e.target.value))}
                        className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                      />
                    ) : typeof value === 'boolean' ? (
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={(e) => handleInputChange(key, e.target.checked)}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                      />
                    ) : (
                      <input
                        type="text"
                        value={String(value)}
                        onChange={(e) => handleInputChange(key, e.target.value)}
                        className="block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                      />
                    )
                  ) : Array.isArray(value) ? (
                    <span className="inline-flex flex-wrap gap-1">
                      {value.map((v, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 text-primary-800"
                        >
                          {v}
                        </span>
                      ))}
                    </span>
                  ) : typeof value === 'boolean' ? (
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        value ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {value ? 'Enabled' : 'Disabled'}
                    </span>
                  ) : (
                    <span className="font-mono">{String(value)}</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    );
  };

  if (isLoading || !config) {
    return (
      <div className="flex items-center justify-center h-64">
        <ArrowPathIcon className="h-8 w-8 text-gray-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bot Configuration</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage trading bot settings and parameters
          </p>
        </div>
        <button
          onClick={fetchConfig}
          className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
        >
          <ArrowPathIcon className="h-5 w-5 mr-2" />
          Refresh
        </button>
      </div>

      {/* Save Message */}
      {saveMessage && (
        <div
          className={`rounded-md p-4 ${
            saveMessage.type === 'success' ? 'bg-green-50' : 'bg-red-50'
          }`}
        >
          <p
            className={`text-sm font-medium ${
              saveMessage.type === 'success' ? 'text-green-800' : 'text-red-800'
            }`}
          >
            {saveMessage.text}
          </p>
        </div>
      )}

      {/* Environment Badge */}
      <div className="bg-white shadow rounded-lg px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">Current Environment:</span>
          <span
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
              config.environment === 'live'
                ? 'bg-red-100 text-red-800'
                : config.environment === 'paper'
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-blue-100 text-blue-800'
            }`}
          >
            {config.environment.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Configuration Sections */}
      <div className="space-y-6">
        {renderConfigSection('Risk Management', 'risk', config.risk)}
        {renderConfigSection('Strategy Settings', 'strategy', config.strategy)}
        {renderConfigSection('Asset Universe', 'assets', config.assets)}
        {renderConfigSection('LLM Configuration', 'llm', config.llm)}
      </div>
    </div>
  );
}
