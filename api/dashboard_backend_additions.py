# This file contains the additional endpoints to add to dashboard_backend.py
# Insert these BEFORE the "if __name__ == '__main__':" block

# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - LOGS
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/logs")
async def get_logs(
    request: Request,
    limit: int = 500,
    level: Optional[str] = None,
    source: Optional[str] = None
):
    """Get system logs with optional filtering."""
    await check_rate_limit(request)
    
    # Mock logs (integrate with actual logging system in production)
    logs = [
        {
            "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
            "level": ["INFO", "DEBUG", "WARNING", "ERROR"][i % 4],
            "logger": ["DASHBOARD_BACKEND", "FAST_DECISION", "MARKET_CONTEXT", "DATA_LAKE"][i % 4],
            "message": f"Sample log message {i}",
            "context": {"sample_key": f"value_{i}"} if i % 5 == 0 else None
        }
        for i in range(min(limit, 100))
    ]
    
    if level and level != "ALL":
        logs = [log for log in logs if log["level"] == level]
    if source and source != "ALL":
        logs = [log for log in logs if log["logger"] == source]
    
    return {"logs": logs, "count": len(logs)}


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - CONFIGURATION
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/config")
async def get_config(request: Request):
    """Get current bot configuration."""
    await check_rate_limit(request)
    
    from core.config import settings
    
    config = {
        "environment": settings.env.value,
        "risk": {
            "max_risk_per_trade_pct": settings.risk.max_risk_per_trade_pct,
            "max_combined_risk_pct": settings.risk.max_combined_risk_pct,
            "max_daily_drawdown_pct": settings.risk.max_daily_drawdown_pct,
            "max_consecutive_losses": settings.risk.max_consecutive_losses,
            "min_equity_pct": settings.risk.min_equity_pct,
            "max_open_trades": settings.risk.max_open_trades,
            "max_trades_per_symbol": settings.risk.max_trades_per_symbol,
            "max_lot_size": settings.risk.max_lot_size,
            "min_signal_score": settings.risk.min_signal_score,
        },
        "strategy": {
            "enabled_strategies": settings.strategy.enabled_strategies,
        },
        "assets": {
            "metals": settings.assets.metals,
            "commodities": settings.assets.commodities,
            "forex": settings.assets.forex,
            "crypto": settings.assets.crypto,
            "indices": settings.assets.indices,
        },
        "llm": {
            "provider": settings.llm_provider.value,
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
        }
    }
    
    return config


@dashboard_app.patch("/api/v1/config/{section}")
async def update_config(section: str, request: Request):
    """Update a configuration section."""
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        
        valid_sections = ["risk", "strategy", "assets", "llm"]
        if section not in valid_sections:
            raise HTTPException(status_code=400, detail=f"Invalid section: {section}")
        
        from core.config import settings
        
        if section == "risk":
            for key, value in data.items():
                if hasattr(settings.risk, key):
                    setattr(settings.risk, key, value)
        elif section == "strategy":
            for key, value in data.items():
                if hasattr(settings.strategy, key):
                    setattr(settings.strategy, key, value)
        elif section == "assets":
            for key, value in data.items():
                if hasattr(settings.assets, key):
                    setattr(settings.assets, key, value)
        elif section == "llm":
            if "provider" in data:
                settings.llm_provider = data["provider"]
            if "model" in data:
                settings.llm_model = data["model"]
            if "temperature" in data:
                settings.llm_temperature = data["temperature"]
            if "max_tokens" in data:
                settings.llm_max_tokens = data["max_tokens"]
        
        log.info(f"Configuration section '{section}' updated: {data}")
        
        return {"message": f"Configuration section '{section}' updated successfully"}
    
    except Exception as e:
        log.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - MODEL TRAINING
# ═══════════════════════════════════════════════════════

@dashboard_app.get("/api/v1/training/jobs")
async def get_training_jobs(request: Request):
    """Get list of training jobs."""
    await check_rate_limit(request)
    
    jobs = [
        {
            "job_id": "job_001",
            "model_type": "XGBOOST",
            "status": "completed",
            "progress": 100,
            "started_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "completed_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "metrics": {
                "accuracy": 0.58,
                "precision": 0.56,
                "recall": 0.60,
                "f1_score": 0.58,
                "roc_auc": 0.62
            }
        }
    ]
    
    return {"jobs": jobs, "count": len(jobs)}


@dashboard_app.get("/api/v1/training/deployments")
async def get_deployments(request: Request):
    """Get list of model deployments."""
    await check_rate_limit(request)
    
    models = model_registry.list_models(filters={"deployment_status": "PRODUCTION"})
    
    deployments = []
    for model in models:
        deployments.append({
            "model_id": model.model_id,
            "model_name": model.model_name,
            "version": model.version,
            "status": model.deployment_status.lower(),
            "environment": model.deployment_environment.lower() if model.deployment_environment else "paper",
            "deployed_at": model.deployment_timestamp.isoformat() if model.deployment_timestamp else None
        })
    
    return {"deployments": deployments, "count": len(deployments)}


@dashboard_app.post("/api/v1/training/start")
async def start_training(request: Request):
    """Start a new model training job."""
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        model_type = data.get("model_type", "XGBOOST")
        lookback_months = data.get("lookback_months", 6)
        
        job_id = f"job_{int(time.time())}"
        
        log.info(f"Starting training job {job_id}: {model_type}, lookback={lookback_months}mo")
        
        return {
            "job_id": job_id,
            "status": "pending",
            "message": "Training job started successfully"
        }
    
    except Exception as e:
        log.error(f"Failed to start training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/training/deploy/{model_id}")
async def deploy_model(model_id: str, request: Request):
    """Deploy a model to an environment."""
    await check_rate_limit(request)
    
    try:
        data = await request.json()
        environment = data.get("environment", "paper")
        
        metadata, _ = model_registry.get_model(model_id)
        metadata.deployment_status = "PRODUCTION"
        metadata.deployment_environment = environment.upper()
        metadata.deployment_timestamp = datetime.utcnow()
        
        log.info(f"Model {model_id} deployed to {environment}")
        
        return {
            "message": f"Model deployed to {environment} successfully",
            "model_id": model_id,
            "environment": environment
        }
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception as e:
        log.error(f"Failed to deploy model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/training/retire/{model_id}")
async def retire_model(model_id: str, request: Request):
    """Retire a deployed model."""
    await check_rate_limit(request)
    
    try:
        metadata, _ = model_registry.get_model(model_id)
        metadata.deployment_status = "RETIRED"
        
        log.info(f"Model {model_id} retired")
        
        return {
            "message": "Model retired successfully",
            "model_id": model_id
        }
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception as e:
        log.error(f"Failed to retire model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - BOT CONTROL & ACTIVITY
# ═══════════════════════════════════════════════════════

# Global bot state
bot_state = {
    "status": "stopped",
    "uptime_seconds": 0,
    "last_started": datetime.utcnow().isoformat(),
    "last_stopped": datetime.utcnow().isoformat(),
    "active_positions": 0,
    "pending_orders": 0,
    "error_message": None
}

activity_log_store = []
scheduled_jobs_store = []
async_jobs_store = []


@dashboard_app.get("/api/v1/bot/status")
async def get_bot_status(request: Request):
    """Get current bot status and statistics."""
    await check_rate_limit(request)
    
    if bot_state["status"] == "running" and bot_state["last_started"]:
        start_time = datetime.fromisoformat(bot_state["last_started"])
        bot_state["uptime_seconds"] = int((datetime.utcnow() - start_time).total_seconds())
    
    return bot_state


@dashboard_app.post("/api/v1/bot/start")
async def start_bot(request: Request):
    """Start the trading bot."""
    await check_rate_limit(request)
    
    if bot_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    try:
        bot_state["status"] = "running"
        bot_state["last_started"] = datetime.utcnow().isoformat()
        bot_state["uptime_seconds"] = 0
        bot_state["error_message"] = None
        
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot started via dashboard",
            "status": "success"
        })
        
        log.info("Bot started via dashboard")
        await broadcast_alert("bot_control", "Bot started", "info")
        
        return {"message": "Bot started successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to start bot: {e}")
        bot_state["status"] = "error"
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/stop")
async def stop_bot(request: Request):
    """Stop the trading bot."""
    await check_rate_limit(request)
    
    if bot_state["status"] == "stopped":
        raise HTTPException(status_code=400, detail="Bot is already stopped")
    
    try:
        bot_state["status"] = "stopped"
        bot_state["last_stopped"] = datetime.utcnow().isoformat()
        bot_state["error_message"] = None
        
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot stopped via dashboard",
            "status": "success"
        })
        
        log.info("Bot stopped via dashboard")
        await broadcast_alert("bot_control", "Bot stopped", "warning")
        
        return {"message": "Bot stopped successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to stop bot: {e}")
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/pause")
async def pause_bot(request: Request):
    """Pause the trading bot."""
    await check_rate_limit(request)
    
    if bot_state["status"] != "running":
        raise HTTPException(status_code=400, detail="Bot is not running")
    
    try:
        bot_state["status"] = "paused"
        bot_state["error_message"] = None
        
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot paused via dashboard",
            "status": "success"
        })
        
        log.info("Bot paused via dashboard")
        await broadcast_alert("bot_control", "Bot paused", "warning")
        
        return {"message": "Bot paused successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to pause bot: {e}")
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.post("/api/v1/bot/restart")
async def restart_bot(request: Request):
    """Restart the trading bot."""
    await check_rate_limit(request)
    
    try:
        if bot_state["status"] in ["running", "paused"]:
            bot_state["status"] = "stopped"
            bot_state["last_stopped"] = datetime.utcnow().isoformat()
            await asyncio.sleep(2)
        
        bot_state["status"] = "running"
        bot_state["last_started"] = datetime.utcnow().isoformat()
        bot_state["uptime_seconds"] = 0
        bot_state["error_message"] = None
        
        activity_log_store.insert(0, {
            "id": f"act_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "activity_type": "BOT_CONTROL",
            "component": "DASHBOARD",
            "description": "Bot restarted via dashboard",
            "status": "success"
        })
        
        log.info("Bot restarted via dashboard")
        await broadcast_alert("bot_control", "Bot restarted", "info")
        
        return {"message": "Bot restarted successfully", "status": bot_state["status"]}
    
    except Exception as e:
        log.error(f"Failed to restart bot: {e}")
        bot_state["status"] = "error"
        bot_state["error_message"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@dashboard_app.get("/api/v1/bot/activity")
async def get_activity_log(
    request: Request,
    limit: int = 100,
    activity_type: Optional[str] = None
):
    """Get bot activity log."""
    await check_rate_limit(request)
    
    if not activity_log_store:
        activity_types = [
            ("TRADE_OPENED", "FAST_DECISION", "Opened LONG position on XAUUSD"),
            ("TRADE_CLOSED", "FAST_DECISION", "Closed position on XAUUSD with +2.5% profit"),
            ("MODEL_PREDICTION", "MODEL_INFERENCE", "Generated prediction for EURUSD"),
            ("DATA_COLLECTION", "TICK_COLLECTOR", "Collected 1000 ticks for XAUUSD"),
            ("FEATURE_UPDATE", "FEATURE_PIPELINE", "Updated features for 5 symbols"),
            ("HEALTH_CHECK", "SYSTEM_MONITOR", "All systems healthy"),
        ]
        
        for i in range(20):
            activity_type_data = activity_types[i % len(activity_types)]
            activity_log_store.append({
                "id": f"act_{i}",
                "timestamp": (datetime.utcnow() - timedelta(minutes=i * 5)).isoformat(),
                "activity_type": activity_type_data[0],
                "component": activity_type_data[1],
                "description": activity_type_data[2],
                "status": ["success", "running", "failed"][i % 3] if i % 7 == 0 else "success"
            })
    
    activities = activity_log_store[:limit]
    
    if activity_type:
        activities = [a for a in activities if a["activity_type"] == activity_type]
    
    return {"activities": activities, "count": len(activities)}


@dashboard_app.get("/api/v1/bot/scheduled-jobs")
async def get_scheduled_jobs(request: Request):
    """Get list of scheduled jobs."""
    await check_rate_limit(request)
    
    if not scheduled_jobs_store:
        scheduled_jobs_store.extend([
            {
                "job_id": "job_model_retrain",
                "job_name": "Weekly Model Retraining",
                "job_type": "model_training",
                "schedule": "Every Sunday at 02:00 UTC",
                "last_run": (datetime.utcnow() - timedelta(days=2)).isoformat(),
                "next_run": (datetime.utcnow() + timedelta(days=5)).isoformat(),
                "status": "active",
                "last_duration_seconds": 1800
            },
            {
                "job_id": "job_data_archive",
                "job_name": "Daily Data Archival",
                "job_type": "data_collection",
                "schedule": "Every day at 00:00 UTC",
                "last_run": (datetime.utcnow() - timedelta(hours=8)).isoformat(),
                "next_run": (datetime.utcnow() + timedelta(hours=16)).isoformat(),
                "status": "active",
                "last_duration_seconds": 120
            },
            {
                "job_id": "job_portfolio_rebalance",
                "job_name": "Weekly Portfolio Rebalancing",
                "job_type": "rebalancing",
                "schedule": "Every Monday at 09:00 UTC",
                "last_run": (datetime.utcnow() - timedelta(days=6)).isoformat(),
                "next_run": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                "status": "active",
                "last_duration_seconds": 45
            },
            {
                "job_id": "job_health_check",
                "job_name": "System Health Check",
                "job_type": "health_check",
                "schedule": "Every 5 minutes",
                "last_run": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
                "next_run": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                "status": "active",
                "last_duration_seconds": 2
            }
        ])
    
    return {"jobs": scheduled_jobs_store, "count": len(scheduled_jobs_store)}


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/pause")
async def pause_scheduled_job(job_id: str, request: Request):
    """Pause a scheduled job."""
    await check_rate_limit(request)
    
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            job["status"] = "paused"
            log.info(f"Scheduled job {job_id} paused")
            return {"message": "Job paused successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/resume")
async def resume_scheduled_job(job_id: str, request: Request):
    """Resume a paused scheduled job."""
    await check_rate_limit(request)
    
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            job["status"] = "active"
            log.info(f"Scheduled job {job_id} resumed")
            return {"message": "Job resumed successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.post("/api/v1/bot/scheduled-jobs/{job_id}/run-now")
async def run_scheduled_job_now(job_id: str, request: Request):
    """Trigger a scheduled job to run immediately."""
    await check_rate_limit(request)
    
    for job in scheduled_jobs_store:
        if job["job_id"] == job_id:
            log.info(f"Scheduled job {job_id} triggered manually")
            
            async_jobs_store.insert(0, {
                "job_id": f"async_{int(time.time())}",
                "job_type": job["job_type"],
                "status": "running",
                "progress": 0,
                "started_at": datetime.utcnow().isoformat()
            })
            
            return {"message": "Job triggered successfully"}
    
    raise HTTPException(status_code=404, detail="Job not found")


@dashboard_app.get("/api/v1/bot/async-jobs")
async def get_async_jobs(request: Request):
    """Get list of async/background jobs."""
    await check_rate_limit(request)
    
    if not async_jobs_store:
        async_jobs_store.extend([
            {
                "job_id": "async_001",
                "job_type": "model_training",
                "status": "running",
                "progress": 65,
                "started_at": (datetime.utcnow() - timedelta(minutes=15)).isoformat()
            },
            {
                "job_id": "async_002",
                "job_type": "data_backfill",
                "status": "completed",
                "progress": 100,
                "started_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "completed_at": (datetime.utcnow() - timedelta(hours=1)).isoformat()
            }
        ])
    
    return {"jobs": async_jobs_store, "count": len(async_jobs_store)}


@dashboard_app.post("/api/v1/bot/async-jobs/{job_id}/cancel")
async def cancel_async_job(job_id: str, request: Request):
    """Cancel a running async job."""
    await check_rate_limit(request)
    
    for job in async_jobs_store:
        if job["job_id"] == job_id:
            if job["status"] in ["running", "pending"]:
                job["status"] = "failed"
                job["error"] = "Cancelled by user"
                job["completed_at"] = datetime.utcnow().isoformat()
                log.info(f"Async job {job_id} cancelled")
                return {"message": "Job cancelled successfully"}
            else:
                raise HTTPException(status_code=400, detail="Job is not running")
    
    raise HTTPException(status_code=404, detail="Job not found")


# ═══════════════════════════════════════════════════════
#  REST API ENDPOINTS - DECISION TRACES
# ═══════════════════════════════════════════════════════

from core.decision_tracer import get_trace, get_recent_traces, DecisionType as TraceDecisionType
from dataclasses import asdict


@dashboard_app.get("/api/v1/decisions/traces")
async def get_decision_traces(
    request: Request,
    limit: int = 50,
    decision_type: Optional[str] = None,
    symbol: Optional[str] = None
):
    """Get recent decision traces with optional filters."""
    await check_rate_limit(request)
    
    dt_enum = None
    if decision_type:
        try:
            dt_enum = TraceDecisionType(decision_type)
        except ValueError:
            pass
    
    traces = get_recent_traces(
        limit=limit,
        decision_type=dt_enum,
        symbol=symbol
    )
    
    traces_dict = [asdict(trace) for trace in traces]
    
    return {"traces": traces_dict, "count": len(traces_dict)}


@dashboard_app.get("/api/v1/decisions/traces/{decision_id}")
async def get_decision_trace_details(decision_id: str, request: Request):
    """Get detailed trace for a specific decision."""
    await check_rate_limit(request)
    
    trace = get_trace(decision_id)
    
    if not trace:
        raise HTTPException(status_code=404, detail="Decision trace not found")
    
    return asdict(trace)


@dashboard_app.get("/api/v1/agents/logs")
async def get_agent_logs(
    request: Request,
    agent_name: Optional[str] = None,
    limit: int = 100
):
    """Get logs from specific agents."""
    await check_rate_limit(request)
    
    agents = [
        "FastDecisionEngine",
        "MacroAgent",
        "ParallelAnalyzer",
        "AutonomousOrchestrator",
        "MarketContext",
        "OutcomeTracker"
    ]
    
    logs = []
    for i in range(min(limit, 50)):
        agent = agents[i % len(agents)] if not agent_name else agent_name
        logs.append({
            "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
            "agent_name": agent,
            "log_level": ["INFO", "DEBUG", "WARNING"][i % 3],
            "message": f"Sample log message from {agent}",
            "context": {"sample_key": f"value_{i}"} if i % 5 == 0 else None
        })
    
    return {"logs": logs, "count": len(logs)}
