import { useState, useEffect } from 'react';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { apiClient } from '../api/client';

interface AgentLog {
  agent_name: string;
  timestamp: string;
  log_level: string;
  message: string;
  context?: Record<string, any>;
}

interface DecisionStep {
  step_number: number;
  step_name: string;
  agent: string;
  timestamp: string;
  duration_ms: number;
  status: 'passed' | 'failed' | 'skipped';
  input_data?: Record<string, any>;
  output_data?: Record<string, any>;
  reasoning?: string;
  agent_logs: AgentLog[];
}

interface DecisionTrace {
  decision_id: string;
  timestamp: string;
  symbol: string;
  decision_type: 'TRADE_OPENED' | 'TRADE_REJECTED' | 'TRADE_CLOSED' | 'POSITION_ADJUSTED';
  final_decision: string;
  confidence: number;
  total_duration_ms: number;
  steps: DecisionStep[];
  market_state: Record<string, any>;
  rejection_reason?: string;
}

export default function DecisionTraceDashboard() {
  const [traces, setTraces] = useState<DecisionTrace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<DecisionTrace | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDecision, setFilterDecision] = useState('ALL');
  const [filterSymbol, setFilterSymbol] = useState('ALL');
  const [isLoading, setIsLoading] = useState(false);

  const DECISION_TYPES = ['ALL', 'TRADE_OPENED', 'TRADE_REJECTED', 'TRADE_CLOSED', 'POSITION_ADJUSTED'];
  const SYMBOLS = ['ALL', 'XAUUSD', 'EURUSD', 'BTCUSD', 'USOIL'];

  const fetchTraces = async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get('/decisions/traces', {
        params: {
          limit: 50,
          decision_type: filterDecision !== 'ALL' ? filterDecision : undefined,
          symbol: filterSymbol !== 'ALL' ? filterSymbol : undefined,
        },
      });
      setTraces(response.data.traces || []);
    } catch (error) {
      console.error('Failed to fetch decision traces:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTraceDetails = async (decisionId: string) => {
    try {
      const response = await apiClient.get(`/decisions/traces/${decisionId}`);
      setSelectedTrace(response.data);
    } catch (error) {
      console.error('Failed to fetch trace details:', error);
    }
  };

  useEffect(() => {
    fetchTraces();
    const interval = setInterval(fetchTraces, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [filterDecision, filterSymbol]);

  const toggleStep = (stepNumber: number) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(stepNumber)) {
      newExpanded.delete(stepNumber);
    } else {
      newExpanded.add(stepNumber);
    }
    setExpandedSteps(newExpanded);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
        return <CheckCircleIcon className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-500" />;
      case 'skipped':
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
      default:
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'text-green-600 bg-green-100';
      case 'failed':
        return 'text-red-600 bg-red-100';
      case 'skipped':
        return 'text-gray-600 bg-gray-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const getDecisionColor = (decisionType: string) => {
    switch (decisionType) {
      case 'TRADE_OPENED':
        return 'text-green-600 bg-green-100';
      case 'TRADE_REJECTED':
        return 'text-red-600 bg-red-100';
      case 'TRADE_CLOSED':
        return 'text-blue-600 bg-blue-100';
      case 'POSITION_ADJUSTED':
        return 'text-yellow-600 bg-yellow-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const filteredTraces = traces.filter((trace) =>
    searchTerm
      ? trace.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
        trace.decision_id.toLowerCase().includes(searchTerm.toLowerCase())
      : true
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Decision Trace Viewer</h1>
        <p className="mt-1 text-sm text-gray-700">
          Track every decision with complete agent logs and reasoning
        </p>
        <div className="mt-3 text-sm text-gray-600 space-y-1">
          <p><strong>How to use:</strong></p>
          <ul className="list-disc list-inside ml-2 space-y-1">
            <li>Use the <strong>Decision Type</strong> filter to show only specific types (TRADE_OPENED, TRADE_REJECTED, etc.)</li>
            <li>Use the <strong>Symbol</strong> filter to show decisions for a specific trading pair</li>
            <li>Use the <strong>Search</strong> box to find decisions by symbol name or decision ID</li>
            <li>Click on any decision in the left panel to view detailed step-by-step breakdown</li>
            <li>Click on any step to expand and see agent logs, input/output data, and reasoning</li>
          </ul>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white shadow rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="relative">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <div className="relative">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search by symbol or ID..."
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Decision Type</label>
            <select
              value={filterDecision}
              onChange={(e) => setFilterDecision(e.target.value)}
              className="block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
            >
              {DECISION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
            <select
              value={filterSymbol}
              onChange={(e) => setFilterSymbol(e.target.value)}
              className="block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
            >
              {SYMBOLS.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Traces List */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-3 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium text-gray-900">
                Decision Traces ({filteredTraces.length})
              </h2>
              <FunnelIcon className="h-5 w-5 text-gray-400" />
            </div>
          </div>
          <div className="overflow-auto" style={{ maxHeight: '700px' }}>
            <div className="divide-y divide-gray-200">
              {filteredTraces.length === 0 ? (
                <div className="px-4 py-8 text-center text-gray-500">
                  No decision traces found
                </div>
              ) : (
                filteredTraces.map((trace) => (
                  <div
                    key={trace.decision_id}
                    onClick={() => fetchTraceDetails(trace.decision_id)}
                    className={`px-4 py-3 hover:bg-gray-50 cursor-pointer ${
                      selectedTrace?.decision_id === trace.decision_id ? 'bg-primary-50' : ''
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-gray-900">{trace.symbol}</span>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getDecisionColor(
                              trace.decision_type
                            )}`}
                          >
                            {trace.decision_type}
                          </span>
                        </div>
                        <div className="mt-1 text-sm text-gray-500">
                          {new Date(trace.timestamp).toLocaleString()}
                        </div>
                        <div className="mt-1 text-sm text-gray-700">{trace.final_decision}</div>
                        {trace.rejection_reason && (
                          <div className="mt-1 text-xs text-red-600">
                            Rejected: {trace.rejection_reason}
                          </div>
                        )}
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-medium text-gray-900">
                          {trace.confidence}%
                        </div>
                        <div className="text-xs text-gray-500">{trace.total_duration_ms}ms</div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Trace Details */}
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-lg font-medium text-gray-900">Decision Details</h2>
          </div>
          <div className="overflow-auto" style={{ maxHeight: '700px' }}>
            {!selectedTrace ? (
              <div className="px-4 py-8 text-center text-gray-500">
                Select a decision trace to view details
              </div>
            ) : (
              <div className="p-4 space-y-4">
                {/* Summary */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Summary</h3>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-gray-500">Decision ID</dt>
                      <dd className="font-mono text-gray-900">
                        {selectedTrace.decision_id.substring(0, 12)}...
                      </dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">Total Duration</dt>
                      <dd className="text-gray-900">{selectedTrace.total_duration_ms}ms</dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">Steps</dt>
                      <dd className="text-gray-900">{selectedTrace.steps.length}</dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">Confidence</dt>
                      <dd className="text-gray-900">{selectedTrace.confidence}%</dd>
                    </div>
                  </dl>
                </div>

                {/* Market State */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Market State</h3>
                  <pre className="text-xs text-gray-700 overflow-auto">
                    {JSON.stringify(selectedTrace.market_state, null, 2)}
                  </pre>
                </div>

                {/* Decision Steps */}
                <div>
                  <h3 className="text-sm font-medium text-gray-900 mb-2">Decision Steps</h3>
                  <div className="space-y-2">
                    {selectedTrace.steps.map((step) => (
                      <div key={step.step_number} className="border border-gray-200 rounded-lg">
                        <div
                          onClick={() => toggleStep(step.step_number)}
                          className="px-4 py-3 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
                        >
                          <div className="flex items-center space-x-3">
                            {expandedSteps.has(step.step_number) ? (
                              <ChevronDownIcon className="h-5 w-5 text-gray-400" />
                            ) : (
                              <ChevronRightIcon className="h-5 w-5 text-gray-400" />
                            )}
                            {getStatusIcon(step.status)}
                            <div>
                              <div className="text-sm font-medium text-gray-900">
                                {step.step_number}. {step.step_name}
                              </div>
                              <div className="text-xs text-gray-500">
                                {step.agent} • {step.duration_ms}ms
                              </div>
                            </div>
                          </div>
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(
                              step.status
                            )}`}
                          >
                            {step.status}
                          </span>
                        </div>

                        {expandedSteps.has(step.step_number) && (
                          <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 space-y-3">
                            {/* Reasoning */}
                            {step.reasoning && (
                              <div>
                                <h4 className="text-xs font-medium text-gray-700 mb-1">
                                  Reasoning
                                </h4>
                                <p className="text-sm text-gray-900">{step.reasoning}</p>
                              </div>
                            )}

                            {/* Input Data */}
                            {step.input_data && (
                              <div>
                                <h4 className="text-xs font-medium text-gray-700 mb-1">
                                  Input Data
                                </h4>
                                <pre className="text-xs text-gray-700 bg-white p-2 rounded overflow-auto">
                                  {JSON.stringify(step.input_data, null, 2)}
                                </pre>
                              </div>
                            )}

                            {/* Output Data */}
                            {step.output_data && (
                              <div>
                                <h4 className="text-xs font-medium text-gray-700 mb-1">
                                  Output Data
                                </h4>
                                <pre className="text-xs text-gray-700 bg-white p-2 rounded overflow-auto">
                                  {JSON.stringify(step.output_data, null, 2)}
                                </pre>
                              </div>
                            )}

                            {/* Agent Logs */}
                            {step.agent_logs && step.agent_logs.length > 0 && (
                              <div>
                                <h4 className="text-xs font-medium text-gray-700 mb-1">
                                  Agent Logs ({step.agent_logs.length})
                                </h4>
                                <div className="space-y-1 max-h-48 overflow-auto">
                                  {step.agent_logs.map((log, idx) => (
                                    <div
                                      key={idx}
                                      className="text-xs bg-white p-2 rounded font-mono"
                                    >
                                      <div className="flex items-start space-x-2">
                                        <span className="text-gray-500">
                                          {new Date(log.timestamp).toLocaleTimeString()}
                                        </span>
                                        <span
                                          className={`px-1 rounded ${
                                            log.log_level === 'ERROR'
                                              ? 'bg-red-100 text-red-800'
                                              : log.log_level === 'WARNING'
                                              ? 'bg-yellow-100 text-yellow-800'
                                              : 'bg-blue-100 text-blue-800'
                                          }`}
                                        >
                                          {log.log_level}
                                        </span>
                                        <span className="text-gray-700">[{log.agent_name}]</span>
                                      </div>
                                      <div className="mt-1 text-gray-900">{log.message}</div>
                                      {log.context && (
                                        <pre className="mt-1 text-gray-600 overflow-auto">
                                          {JSON.stringify(log.context, null, 2)}
                                        </pre>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
