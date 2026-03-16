# APEX Trading Dashboard

Modern React-based dashboard for monitoring the APEX autonomous trading bot.

## Features

### 1. Market State Dashboard
- Real-time market regime indicator
- Symbol watchlist with prices, spreads, and volumes
- Technical indicators with color coding
- Order book depth visualization (heatmap)
- Recent news with sentiment scores
- Economic calendar
- WebSocket updates every 5 seconds

### 2. Performance Analytics Dashboard
- Equity curve with drawdown overlay
- Performance metrics table
- Trade distribution histograms
- Performance breakdown by symbol, time, and regime
- Rolling performance metrics (1-day, 1-week, 1-month)
- Updates every 1 minute

### 3. Trade Journal Dashboard
- Searchable/filterable trade table
- Decision details modal
- Trade outcome visualization
- Decision maker breakdown (fast path vs LLM)
- Win/loss analysis by decision type
- CSV/JSON export support

### 4. Model Performance Dashboard
- Currently deployed model information
- Model performance metrics over time
- Feature importance visualization (SHAP)
- Prediction accuracy tracking
- Model retraining history
- A/B test results comparison
- Updates every 5 minutes

### 5. System Health Dashboard
- Data pipeline metrics (latency, queue depth, throughput)
- Data quality alerts
- System health indicators (CPU, memory, disk)
- Connection status (MT5, databases, APIs)
- Alert history log (last 7 days)
- Performance warnings
- Updates every 5 seconds

### 6. Alert Notifications
- Real-time alert notifications
- Data quality warnings
- Large drawdown alerts (>5% from peak)
- High-confidence opportunity notifications
- System health error alerts

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **TailwindCSS** - Styling
- **Recharts** - Data visualization
- **React Router** - Navigation
- **Axios** - HTTP client
- **WebSocket** - Real-time updates

## Prerequisites

- Node.js 18+ and npm
- APEX Dashboard Backend running on port 8001

## Installation

```bash
cd frontend/dashboard
npm install
```

## Development

Start the development server:

```bash
npm run dev
```

The dashboard will be available at `http://localhost:3000`

## Build for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

## Preview Production Build

```bash
npm run preview
```

## Project Structure

```
frontend/dashboard/
├── src/
│   ├── api/              # API client and endpoints
│   ├── components/       # Reusable UI components
│   ├── hooks/            # Custom React hooks (WebSocket, etc.)
│   ├── pages/            # Dashboard pages
│   ├── types/            # TypeScript type definitions
│   ├── App.tsx           # Main app component with routing
│   ├── main.tsx          # Entry point
│   └── index.css         # Global styles
├── public/               # Static assets
├── index.html            # HTML template
├── package.json          # Dependencies
├── tsconfig.json         # TypeScript config
├── vite.config.ts        # Vite config
└── tailwind.config.js    # TailwindCSS config
```

## API Integration

The dashboard connects to the APEX Dashboard Backend API:

- **Base URL**: `http://localhost:8001/api/v1`
- **WebSocket**: `ws://localhost:8001/ws/dashboard`

### REST API Endpoints

- `/market/symbols` - List trading symbols
- `/market/ohlcv/{symbol}` - Historical OHLCV data
- `/market/indicators/{symbol}` - Technical indicators
- `/market/orderbook/{symbol}` - Order book data
- `/performance/metrics` - Performance metrics
- `/performance/equity-curve` - Equity curve data
- `/performance/trades` - Trade history
- `/journal/decisions` - Decision history
- `/journal/decisions/{id}` - Decision details
- `/journal/export` - Export journal
- `/models` - List models
- `/models/{id}` - Model metadata
- `/models/current` - Current production model
- `/health` - Health check

### WebSocket Messages

- `market_update` - Market data and indicators
- `trade_update` - Trade opened/closed
- `decision_update` - Trading decision made
- `alert` - System alert or warning
- `performance_update` - Performance metrics
- `model_update` - Model prediction or retraining

## Configuration

The dashboard is configured to proxy API requests to the backend:

```typescript
// vite.config.ts
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:8001',
      changeOrigin: true,
    },
    '/ws': {
      target: 'ws://localhost:8001',
      ws: true,
    },
  },
}
```

## Customization

### Colors

Edit `tailwind.config.js` to customize the color scheme:

```javascript
theme: {
  extend: {
    colors: {
      primary: {
        // Your custom colors
      },
    },
  },
}
```

### Update Frequencies

Update frequencies are defined in each dashboard page:

- Market State: 5 seconds
- Performance: 1 minute
- Models: 5 minutes
- System Health: 5 seconds

## Troubleshooting

### WebSocket Connection Issues

If the WebSocket connection fails:

1. Ensure the backend is running on port 8001
2. Check browser console for connection errors
3. Verify CORS settings in the backend

### API Rate Limiting

The API has rate limiting (100 requests/minute). If you hit the limit:

- Wait for the `Retry-After` period
- Reduce polling frequencies
- Use WebSocket for real-time updates instead

### Build Errors

If you encounter build errors:

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf node_modules/.vite
```

## License

Part of the APEX Trading Bot project.
