import { useState, useEffect } from 'react';
import { journalApi } from '../api/client';
import { Decision } from '../types';
import DecisionTable from '../components/DecisionTable';
import DecisionDetailsModal from '../components/DecisionDetailsModal';
import DecisionMakerBreakdown from '../components/DecisionMakerBreakdown';

export default function TradeJournalDashboard() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [filters, setFilters] = useState({
    symbol: '',
    decision: '',
    startDate: '',
    endDate: '',
  });
  const [loading, setLoading] = useState(false);

  // Load decisions
  useEffect(() => {
    const loadDecisions = async () => {
      setLoading(true);
      try {
        const params: any = { limit: 100 };
        if (filters.symbol) params.symbol = filters.symbol;
        if (filters.decision) params.decision = filters.decision;
        if (filters.startDate) params.start = filters.startDate;
        if (filters.endDate) params.end = filters.endDate;

        const response = await journalApi.getDecisions(params);
        setDecisions(response.data.decisions);
      } catch (error) {
        console.error('Failed to load decisions:', error);
      } finally {
        setLoading(false);
      }
    };
    loadDecisions();
  }, [filters]);

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const response = await journalApi.exportJournal({ format });
      const blob = new Blob([format === 'csv' ? response.data.data : JSON.stringify(response.data.data, null, 2)], {
        type: format === 'csv' ? 'text/csv' : 'application/json',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trade_journal.${format}`;
      a.click();
    } catch (error) {
      console.error('Failed to export journal:', error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Trade Journal</h1>
          <p className="text-sm text-gray-500 mt-1">
            Detailed history of all trading decisions
          </p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handleExport('csv')}
            className="px-4 py-2 bg-white border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Export CSV
          </button>
          <button
            onClick={() => handleExport('json')}
            className="px-4 py-2 bg-white border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
            <input
              type="text"
              value={filters.symbol}
              onChange={(e) => setFilters({ ...filters, symbol: e.target.value })}
              placeholder="e.g., XAUUSD"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Decision</label>
            <select
              value={filters.decision}
              onChange={(e) => setFilters({ ...filters, decision: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            >
              <option value="">All</option>
              <option value="GO">GO</option>
              <option value="NOGO">NOGO</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
            <input
              type="date"
              value={filters.startDate}
              onChange={(e) => setFilters({ ...filters, startDate: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
            <input
              type="date"
              value={filters.endDate}
              onChange={(e) => setFilters({ ...filters, endDate: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
        </div>
      </div>

      {/* Decision Maker Breakdown */}
      <DecisionMakerBreakdown decisions={decisions} />

      {/* Decision Table */}
      <DecisionTable
        decisions={decisions}
        loading={loading}
        onSelectDecision={setSelectedDecision}
      />

      {/* Decision Details Modal */}
      {selectedDecision && (
        <DecisionDetailsModal
          decision={selectedDecision}
          onClose={() => setSelectedDecision(null)}
        />
      )}
    </div>
  );
}
