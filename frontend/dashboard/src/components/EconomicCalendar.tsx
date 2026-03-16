interface EconomicEvent {
  title: string;
  time: string;
  impact: 'high' | 'medium' | 'low';
  actual?: string;
  forecast?: string;
  previous?: string;
}

export default function EconomicCalendar() {
  // Mock economic events - integrate with real API
  const events: EconomicEvent[] = [
    {
      title: 'US Non-Farm Payrolls',
      time: '14:30',
      impact: 'high',
      forecast: '180K',
      previous: '175K',
    },
    {
      title: 'EUR CPI',
      time: '10:00',
      impact: 'high',
      forecast: '2.5%',
      previous: '2.4%',
    },
    {
      title: 'USD Retail Sales',
      time: '15:30',
      impact: 'medium',
      forecast: '0.3%',
      previous: '0.2%',
    },
  ];

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      case 'low':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Economic Calendar</h3>
        <p className="text-xs text-gray-500 mt-1">Today's events</p>
      </div>
      <div className="p-6">
        <div className="space-y-4">
          {events.map((event, index) => (
            <div key={index} className="border-b border-gray-100 pb-4 last:border-0 last:pb-0">
              <div className="flex justify-between items-start mb-2">
                <div className="flex-1">
                  <h4 className="text-sm font-medium text-gray-900">{event.title}</h4>
                  <p className="text-xs text-gray-500 mt-1">{event.time}</p>
                </div>
                <span
                  className={`ml-2 px-2 py-1 text-xs font-medium rounded uppercase ${getImpactColor(
                    event.impact
                  )}`}
                >
                  {event.impact}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                {event.forecast && (
                  <div>
                    <span className="text-gray-500">Forecast:</span>
                    <span className="ml-1 font-medium">{event.forecast}</span>
                  </div>
                )}
                {event.previous && (
                  <div>
                    <span className="text-gray-500">Previous:</span>
                    <span className="ml-1 font-medium">{event.previous}</span>
                  </div>
                )}
                {event.actual && (
                  <div>
                    <span className="text-gray-500">Actual:</span>
                    <span className="ml-1 font-medium">{event.actual}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
