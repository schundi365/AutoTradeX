import { Decision } from '../types';
import { XMarkIcon } from '@heroicons/react/24/outline';

interface DecisionDetailsModalProps {
  decision: Decision;
  onClose: () => void;
}

export default function DecisionDetailsModal({ decision, onClose }: DecisionDetailsModalProps) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4">
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75" onClick={onClose} />
        <div className="relative bg-white rounded-lg max-w-2xl w-full p-6">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-medium text-gray-900">Decision Details</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-500">
              <XMarkIcon className="h-6 w-6" />
            </button>
          </div>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-500">Timestamp</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(decision.timestamp).toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Symbol</p>
                <p className="text-sm font-medium text-gray-900">{decision.symbol}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Direction</p>
                <p className="text-sm font-medium text-gray-900">{decision.direction}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Decision</p>
                <p className="text-sm font-medium text-gray-900">{decision.decision}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Confidence</p>
                <p className="text-sm font-medium text-gray-900">
                  {(decision.confidence * 100).toFixed(0)}%
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Signal Score</p>
                <p className="text-sm font-medium text-gray-900">
                  {decision.signal_score.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Decision Maker</p>
                <p className="text-sm font-medium text-gray-900">{decision.decision_maker}</p>
              </div>
              {decision.pnl !== undefined && (
                <div>
                  <p className="text-sm text-gray-500">P&L</p>
                  <p
                    className={`text-sm font-medium ${
                      decision.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    ${decision.pnl.toFixed(2)}
                  </p>
                </div>
              )}
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-2">Reasoning</p>
              <p className="text-sm text-gray-900 bg-gray-50 p-3 rounded">{decision.reasoning}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
