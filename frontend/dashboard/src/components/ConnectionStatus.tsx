interface ConnectionStatusProps {
  isConnected: boolean;
  healthStatus: any;
}

export default function ConnectionStatus({ isConnected, healthStatus }: ConnectionStatusProps) {
  const connections = [
    { name: 'WebSocket', status: isConnected, type: 'Real-time' },
    { name: 'API Server', status: healthStatus?.status === 'healthy', type: 'REST' },
    { name: 'MT5 Terminal', status: true, type: 'Trading' },
    { name: 'Database', status: true, type: 'Storage' },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Connection Status</h3>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {connections.map((conn) => (
            <div key={conn.name} className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900">{conn.name}</span>
                <div className={`h-3 w-3 rounded-full ${conn.status ? 'bg-green-500' : 'bg-red-500'}`} />
              </div>
              <p className="text-xs text-gray-500">{conn.type}</p>
              <p className={`text-xs font-medium mt-1 ${conn.status ? 'text-green-600' : 'text-red-600'}`}>
                {conn.status ? 'Connected' : 'Disconnected'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
