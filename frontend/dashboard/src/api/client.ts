import axios from 'axios';

const API_BASE_URL = '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 seconds for database queries
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for retry logic
apiClient.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers['retry-after'];
      console.warn(`Rate limit exceeded. Retry after ${retryAfter} seconds`);
    }
    return Promise.reject(error);
  }
);

// Market Data API
export const marketApi = {
  getSymbols: () => apiClient.get('/market/symbols'),
  getOHLCV: (symbol: string, params?: any) => 
    apiClient.get(`/market/ohlcv/${symbol}`, { params }),
  getIndicators: (symbol: string) => 
    apiClient.get(`/market/indicators/${symbol}`),
  getOrderBook: (symbol: string) => 
    apiClient.get(`/market/orderbook/${symbol}`),
};

// Performance API
export const performanceApi = {
  getMetrics: () => apiClient.get('/performance/metrics'),
  getEquityCurve: (params?: any) => 
    apiClient.get('/performance/equity-curve', { params }),
  getTrades: (params?: any) => 
    apiClient.get('/performance/trades', { params }),
};

// Trade Journal API
export const journalApi = {
  getDecisions: (params?: any) => 
    apiClient.get('/journal/decisions', { params }),
  getDecisionDetails: (entryId: string) => 
    apiClient.get(`/journal/decisions/${entryId}`),
  exportJournal: (params?: any) => 
    apiClient.get('/journal/export', { params }),
};

// Models API
export const modelsApi = {
  getModels: (params?: any) => 
    apiClient.get('/models', { params }),
  getModelMetadata: (modelId: string) => 
    apiClient.get(`/models/${modelId}`),
  downloadModel: (modelId: string) => 
    apiClient.get(`/models/${modelId}/download`, { responseType: 'blob' }),
  getCurrentModel: (modelType?: string) => 
    apiClient.get('/models/current', { params: { model_type: modelType } }),
};

// Health API
export const healthApi = {
  check: () => apiClient.get('/health'),
};
