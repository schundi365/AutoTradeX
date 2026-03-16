interface NewsSentimentProps {
  symbol: string;
}

interface NewsItem {
  title: string;
  sentiment: number;
  timestamp: string;
  source: string;
}

export default function NewsSentiment({ symbol }: NewsSentimentProps) {
  // Mock news data - integrate with real API
  const news: NewsItem[] = [
    {
      title: 'Gold prices surge on inflation concerns',
      sentiment: 0.8,
      timestamp: new Date().toISOString(),
      source: 'Reuters',
    },
    {
      title: 'Fed signals potential rate cuts',
      sentiment: 0.6,
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      source: 'Bloomberg',
    },
    {
      title: 'Market volatility expected to continue',
      sentiment: -0.3,
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      source: 'CNBC',
    },
  ];

  const getSentimentColor = (sentiment: number) => {
    if (sentiment > 0.5) return 'text-green-600 bg-green-50';
    if (sentiment < -0.5) return 'text-red-600 bg-red-50';
    return 'text-gray-600 bg-gray-50';
  };

  const getSentimentLabel = (sentiment: number) => {
    if (sentiment > 0.5) return 'Positive';
    if (sentiment < -0.5) return 'Negative';
    return 'Neutral';
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Recent News</h3>
        <p className="text-xs text-gray-500 mt-1">{symbol}</p>
      </div>
      <div className="p-6">
        <div className="space-y-4">
          {news.map((item, index) => (
            <div key={index} className="border-b border-gray-100 pb-4 last:border-0 last:pb-0">
              <div className="flex justify-between items-start mb-2">
                <h4 className="text-sm font-medium text-gray-900 flex-1">{item.title}</h4>
                <span
                  className={`ml-2 px-2 py-1 text-xs font-medium rounded ${getSentimentColor(
                    item.sentiment
                  )}`}
                >
                  {getSentimentLabel(item.sentiment)}
                </span>
              </div>
              <div className="flex justify-between items-center text-xs text-gray-500">
                <span>{item.source}</span>
                <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
