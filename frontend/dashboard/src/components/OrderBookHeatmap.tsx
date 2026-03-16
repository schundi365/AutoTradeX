import { OrderBook } from '../types';

interface OrderBookHeatmapProps {
  orderBook: OrderBook | null;
}

export default function OrderBookHeatmap({ orderBook }: OrderBookHeatmapProps) {
  if (!orderBook) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Order Book Depth</h3>
        <p className="text-sm text-gray-500">Loading order book...</p>
      </div>
    );
  }

  const maxVolume = Math.max(
    ...orderBook.bids.map((b) => b.volume),
    ...orderBook.asks.map((a) => a.volume)
  );

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-lg font-medium text-gray-900">Order Book Depth</h3>
            <p className="text-xs text-gray-500 mt-1">{orderBook.symbol}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">Imbalance</p>
            <p className="text-sm font-medium text-gray-900">
              {(orderBook.imbalance * 100).toFixed(1)}%
            </p>
          </div>
        </div>
      </div>
      <div className="p-6">
        <div className="space-y-4">
          {/* Asks */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 mb-2">ASKS</h4>
            <div className="space-y-1">
              {orderBook.asks.slice(0, 5).reverse().map((ask, index) => (
                <div key={index} className="flex items-center space-x-2">
                  <div className="w-20 text-sm text-red-600 font-mono">
                    {ask.price.toFixed(2)}
                  </div>
                  <div className="flex-1 relative h-6 bg-gray-100 rounded">
                    <div
                      className="absolute inset-y-0 left-0 bg-red-200 rounded"
                      style={{ width: `${(ask.volume / maxVolume) * 100}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-2">
                      <span className="text-xs font-medium text-gray-700">
                        {ask.volume.toFixed(0)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Spread */}
          <div className="py-2 border-y border-gray-200">
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">Spread</span>
              <span className="text-sm font-medium text-gray-900">
                {(orderBook.asks[0].price - orderBook.bids[0].price).toFixed(2)}
              </span>
            </div>
          </div>

          {/* Bids */}
          <div>
            <h4 className="text-xs font-medium text-gray-500 mb-2">BIDS</h4>
            <div className="space-y-1">
              {orderBook.bids.slice(0, 5).map((bid, index) => (
                <div key={index} className="flex items-center space-x-2">
                  <div className="w-20 text-sm text-green-600 font-mono">
                    {bid.price.toFixed(2)}
                  </div>
                  <div className="flex-1 relative h-6 bg-gray-100 rounded">
                    <div
                      className="absolute inset-y-0 left-0 bg-green-200 rounded"
                      style={{ width: `${(bid.volume / maxVolume) * 100}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-2">
                      <span className="text-xs font-medium text-gray-700">
                        {bid.volume.toFixed(0)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
