"""
Unit tests for Dashboard Backend

Tests REST API endpoints, WebSocket functionality, and rate limiting.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import pandas as pd

from api.dashboard_backend import dashboard_app, check_rate_limit, broadcast_message
from data.trade_journal import TradeJournalEntry, DecisionType, DecisionMaker
from ml.model_registry import ModelMetadata, ModelType, DeploymentStatus


@pytest