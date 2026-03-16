import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import BotControlDashboard from './pages/BotControlDashboard';
import DecisionTraceDashboard from './pages/DecisionTraceDashboard';
import MarketStateDashboard from './pages/MarketStateDashboard';
import PerformanceAnalyticsDashboard from './pages/PerformanceAnalyticsDashboard';
import TradeJournalDashboard from './pages/TradeJournalDashboard';
import ModelPerformanceDashboard from './pages/ModelPerformanceDashboard';
import ModelTrainingDashboard from './pages/ModelTrainingDashboard';
import SystemHealthDashboard from './pages/SystemHealthDashboard';
import LogsViewerDashboard from './pages/LogsViewerDashboard';
import BotConfigurationDashboard from './pages/BotConfigurationDashboard';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/control" replace />} />
          <Route path="/control" element={<BotControlDashboard />} />
          <Route path="/trace" element={<DecisionTraceDashboard />} />
          <Route path="/market" element={<MarketStateDashboard />} />
          <Route path="/performance" element={<PerformanceAnalyticsDashboard />} />
          <Route path="/journal" element={<TradeJournalDashboard />} />
          <Route path="/models" element={<ModelPerformanceDashboard />} />
          <Route path="/training" element={<ModelTrainingDashboard />} />
          <Route path="/health" element={<SystemHealthDashboard />} />
          <Route path="/logs" element={<LogsViewerDashboard />} />
          <Route path="/config" element={<BotConfigurationDashboard />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
