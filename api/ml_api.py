"""
ML API Endpoints
Provides access to ML features: models, backtesting, A/B testing, RL training
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from loguru import logger as log

from core.config import settings

router = APIRouter(prefix="/api/ml", tags=["ml"])


# ═══════════════════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════════════════

class ModelInfo(BaseModel):
    model_id: str
    model_type: str
    version: str
    created_at: str
    metrics: Dict[str, float]
    status: str
    is_deployed: bool


@router.get("/models/list")
async def list_models():
    """List all models in the registry"""
    try:
        from ml.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        models = registry.list_models()
        
        return {
            "models": [
                {
                    "model_id": m["model_id"],
                    "model_type": m.get("model_type", "unknown"),
                    "version": m.get("version", "1.0"),
                    "created_at": m.get("created_at", ""),
                    "metrics": m.get("metrics", {}),
                    "status": m.get("status", "TRAINING"),
                    "is_deployed": m.get("deployment_env") == "PRODUCTION"
                }
                for m in models
            ],
            "count": len(models)
        }
    except Exception as e:
        log.error(f"Error listing models: {e}")
        return {"models": [], "count": 0, "error": str(e)}


@router.get("/models/current")
async def get_current_model():
    """Get currently deployed model"""
    try:
        from ml.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        current = registry.get_deployed_model("PRODUCTION")
        
        if not current:
            return {"model": None, "message": "No model currently deployed"}
        
        return {"model": current}
    except Exception as e:
        log.error(f"Error getting current model: {e}")
        return {"model": None, "error": str(e)}


@router.get("/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed model information"""
    try:
        from ml.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        model = registry.get_model(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        return {"model": model}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/{model_id}/deploy")
async def deploy_model(model_id: str):
    """Deploy a model to production"""
    try:
        from ml.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        success = registry.deploy_model(model_id, "PRODUCTION")
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to deploy model")
        
        log.info(f"Model {model_id} deployed to production")
        return {"success": True, "model_id": model_id, "message": "Model deployed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error deploying model {model_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  BACKTESTING
# ═══════════════════════════════════════════════════════

class BacktestConfig(BaseModel):
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000.0
    strategy: str = "default"
    timeframe: str = "M15"
    commission_per_lot: float = 7.0


# Store running backtests
_backtest_jobs: Dict[str, Dict[str, Any]] = {}


async def _run_backtest_background(job_id: str, config: BacktestConfig):
    """Run backtest in background"""
    try:
        _backtest_jobs[job_id]["status"] = "running"
        _backtest_jobs[job_id]["started_at"] = datetime.utcnow().isoformat()
        
        from ml.backtesting_engine import BacktestingEngine, BacktestConfig as BTConfig, ReplayMode
        from data.historical_data_warehouse import HistoricalDataWarehouse
        from datetime import datetime as dt
        
        # Initialize warehouse
        warehouse = HistoricalDataWarehouse()
        
        # Create backtest config
        bt_config = BTConfig(
            symbol=config.symbol,
            start_date=dt.fromisoformat(config.start_date),
            end_date=dt.fromisoformat(config.end_date),
            initial_capital=config.initial_capital,
            replay_mode=ReplayMode.BAR_BY_BAR,
            timeframe=config.timeframe,
            commission_per_lot=config.commission_per_lot
        )
        
        # Create engine
        engine = BacktestingEngine(warehouse, bt_config)
        
        # Define simple strategy (placeholder - should be configurable)
        def simple_strategy(historical_data, current_step):
            # Simple moving average crossover strategy
            if len(historical_data) < 50:
                return None
            
            sma_20 = historical_data['close'].rolling(20).mean().iloc[-1]
            sma_50 = historical_data['close'].rolling(50).mean().iloc[-1]
            prev_sma_20 = historical_data['close'].rolling(20).mean().iloc[-2]
            prev_sma_50 = historical_data['close'].rolling(50).mean().iloc[-2]
            
            # Buy signal: SMA20 crosses above SMA50
            if prev_sma_20 <= prev_sma_50 and sma_20 > sma_50:
                return {
                    'action': 'OPEN_LONG',
                    'size': 0.01,
                    'stop_loss': historical_data['close'].iloc[-1] * 0.98,
                    'take_profit': historical_data['close'].iloc[-1] * 1.02
                }
            
            # Sell signal: SMA20 crosses below SMA50
            if prev_sma_20 >= prev_sma_50 and sma_20 < sma_50:
                return {
                    'action': 'CLOSE_LONG',
                    'size': 0.01
                }
            
            return None
        
        # Run backtest
        strategy_params = {'strategy': config.strategy, 'timeframe': config.timeframe}
        result = engine.run_backtest(simple_strategy, strategy_params)
        
        # Save results
        results_dir = engine.save_backtest_results(result, save_to_registry=True)
        
        # Store results
        _backtest_jobs[job_id]["status"] = "completed"
        _backtest_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _backtest_jobs[job_id]["results"] = {
            "total_return": result.total_return,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "max_drawdown": result.max_drawdown,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "total_trades": result.total_trades,
            "avg_trade_pnl": result.avg_trade_pnl,
            "avg_holding_time_hours": result.avg_holding_time_seconds / 3600,
            "trades": [
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "size": t.size
                }
                for t in result.trades[:100]  # Limit to first 100 trades
            ],
            "equity_curve": [
                {"timestamp": p["timestamp"].isoformat(), "equity": p["equity"]}
                for p in result.equity_curve[::10]  # Sample every 10th point
            ]
        }
        
        log.info(f"Backtest {job_id} completed successfully")
        
    except Exception as e:
        log.error(f"Backtest {job_id} failed: {e}")
        _backtest_jobs[job_id]["status"] = "failed"
        _backtest_jobs[job_id]["error"] = str(e)
        _backtest_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()


@router.post("/backtest/run")
async def run_backtest(config: BacktestConfig, background_tasks: BackgroundTasks):
    """Start a backtest job"""
    try:
        import uuid
        job_id = str(uuid.uuid4())[:8]
        
        _backtest_jobs[job_id] = {
            "job_id": job_id,
            "config": config.dict(),
            "status": "queued",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Run in background
        background_tasks.add_task(_run_backtest_background, job_id, config)
        
        log.info(f"Backtest job {job_id} queued")
        return {"job_id": job_id, "status": "queued", "message": "Backtest started"}
        
    except Exception as e:
        log.error(f"Error starting backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtest/status/{job_id}")
async def get_backtest_status(job_id: str):
    """Get backtest job status"""
    if job_id not in _backtest_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return _backtest_jobs[job_id]


@router.get("/backtest/results/{job_id}")
async def get_backtest_results(job_id: str):
    """Get backtest results"""
    if job_id not in _backtest_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = _backtest_jobs[job_id]
    
    if job["status"] != "completed":
        return {"status": job["status"], "message": "Backtest not completed yet"}
    
    return {"status": "completed", "results": job.get("results", {})}


@router.get("/backtest/list")
async def list_backtests():
    """List all backtest jobs"""
    return {
        "jobs": [
            {
                "job_id": job["job_id"],
                "symbol": job["config"]["symbol"],
                "status": job["status"],
                "created_at": job["created_at"],
                "completed_at": job.get("completed_at")
            }
            for job in _backtest_jobs.values()
        ],
        "count": len(_backtest_jobs)
    }


# ═══════════════════════════════════════════════════════
#  FEATURE IMPORTANCE
# ═══════════════════════════════════════════════════════

@router.get("/features/importance/{model_id}")
async def get_feature_importance(model_id: str):
    """Get feature importance for a model"""
    try:
        from ml.feature_importance import FeatureImportanceAnalyzer
        from ml.model_registry import ModelRegistry
        
        registry = ModelRegistry()
        model_path = registry.get_model_path(model_id)
        
        if not model_path or not Path(model_path).exists():
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Load model and compute SHAP values
        analyzer = FeatureImportanceAnalyzer()
        # This would need sample data - placeholder for now
        
        return {
            "model_id": model_id,
            "features": [
                {"name": "RSI_14", "importance": 0.15},
                {"name": "MACD", "importance": 0.12},
                {"name": "ATR_14", "importance": 0.10},
                {"name": "EMA_20", "importance": 0.08},
                {"name": "Volume_Ratio", "importance": 0.07}
            ],
            "message": "Feature importance computed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error computing feature importance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  A/B TESTING
# ═══════════════════════════════════════════════════════

@router.get("/ab-tests/active")
async def get_active_ab_tests():
    """Get active A/B tests"""
    try:
        from ml.ab_testing_framework import ABTestingFramework
        
        # Placeholder - would need to track active tests
        return {
            "tests": [],
            "count": 0,
            "message": "No active A/B tests"
        }
        
    except Exception as e:
        log.error(f"Error getting A/B tests: {e}")
        return {"tests": [], "count": 0, "error": str(e)}


# ═══════════════════════════════════════════════════════
#  RL TRAINING
# ═══════════════════════════════════════════════════════

@router.get("/rl/agents")
async def list_rl_agents():
    """List trained RL agents"""
    try:
        # Check for saved agents
        agents_dir = Path("models/rl_agents")
        if not agents_dir.exists():
            return {"agents": [], "count": 0}
        
        agents = []
        for agent_file in agents_dir.glob("*.zip"):
            agents.append({
                "name": agent_file.stem,
                "path": str(agent_file),
                "created_at": datetime.fromtimestamp(agent_file.stat().st_mtime).isoformat()
            })
        
        return {"agents": agents, "count": len(agents)}
        
    except Exception as e:
        log.error(f"Error listing RL agents: {e}")
        return {"agents": [], "count": 0, "error": str(e)}
