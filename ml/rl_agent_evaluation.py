"""
RL Agent Evaluation and Promotion

Implements evaluation of RL agents on out-of-sample data and promotion logic
for moving agents to paper trading based on performance criteria.

Requirements: 12.5
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
import json

from stable_baselines3 import PPO

from ml.rl_training_environment import TradingEnvironment
from ml.ppo_agent_training import AgentMetrics, PPOConfig
from data.historical_data_warehouse import HistoricalDataWarehouse
from data.feature_pipeline import FeaturePipeline
from core.logger import get_agent_logger

log = get_agent_logger("RL_EVALUATION")


@dataclass
class EvaluationResult:
    """Result of agent evaluation"""
    agent_id: str
    symbol: str
    evaluation_date: datetime
    eval_start_date: datetime
    eval_end_date: datetime
    metrics: AgentMetrics
    promotion_eligible: bool
    promotion_reason: str
    detailed_stats: Dict[str, Any]


class RLAgentEvaluator:
    """
    RL agent evaluator and promoter.
    
    Features:
    - Evaluates agents on out-of-sample data
    - Computes comprehensive performance metrics
    - Determines promotion eligibility based on Sharpe ratio
    - Tracks evaluation history
    - Manages agent lifecycle (training -> testing -> production)
    
    Requirements: 12.5
    """
    
    def __init__(
        self,
        warehouse: HistoricalDataWarehouse,
        feature_pipeline: FeaturePipeline,
        models_dir: str = "models/reinforcement",
        min_sharpe_for_promotion: float = 1.5
    ):
        self.warehouse = warehouse
        self.feature_pipeline = feature_pipeline
        self.models_dir = Path(models_dir)
        self.min_sharpe_for_promotion = min_sharpe_for_promotion
        
        # Evaluation history
        self.evaluation_history: List[EvaluationResult] = []
        
        log.info("RL Agent Evaluator initialized")
        log.info(f"Minimum Sharpe for promotion: {min_sharpe_for_promotion}")
    
    def evaluate_agent_comprehensive(
        self,
        agent: PPO,
        agent_id: str,
        symbol: str,
        timeframe: str = "M15",
        eval_start: Optional[datetime] = None,
        eval_end: Optional[datetime] = None,
        initial_capital: float = 10000.0,
        max_position_size: float = 0.02,
        trade_cost: float = 0.0001,
        reward_window: int = 100
    ) -> EvaluationResult:
        """
        Comprehensive evaluation of RL agent on out-of-sample data.
        
        Requirements: 12.5 - Evaluate on out-of-sample data
        
        Args:
            agent: Trained PPO agent
            agent_id: Unique identifier for agent
            symbol: Trading symbol
            timeframe: Timeframe for evaluation
            eval_start: Evaluation start date (default: 1 month ago)
            eval_end: Evaluation end date (default: now)
            initial_capital: Initial capital for simulation
            max_position_size: Maximum position size
            trade_cost: Trading cost per trade
            reward_window: Rolling window for Sharpe calculation
        
        Returns:
            EvaluationResult with comprehensive metrics
        """
        log.info(f"Starting comprehensive evaluation for agent {agent_id}")
        
        # Set default evaluation period
        if eval_end is None:
            eval_end = datetime.now()
        if eval_start is None:
            eval_start = eval_end - timedelta(days=30)  # 1 month evaluation
        
        log.info(f"Evaluation period: {eval_start} to {eval_end}")
        
        # Create evaluation environment
        eval_env = TradingEnvironment(
            warehouse=self.warehouse,
            feature_pipeline=self.feature_pipeline,
            symbol=symbol,
            timeframe=timeframe,
            start_date=eval_start,
            end_date=eval_end,
            initial_capital=initial_capital,
            max_position_size=max_position_size,
            trade_cost=trade_cost,
            reward_window=reward_window
        )
        
        # Run evaluation episode
        obs, _ = eval_env.reset()
        done = False
        step_count = 0
        
        while not done:
            action, _ = agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = eval_env.step(action)
            done = terminated or truncated
            step_count += 1
        
        log.info(f"Evaluation complete: {step_count} steps")
        
        # Get detailed statistics
        stats = eval_env.get_trade_statistics()
        
        # Create metrics
        metrics = AgentMetrics(
            sharpe_ratio=stats['sharpe_ratio'],
            total_return=stats['total_return'],
            num_trades=stats['num_trades'],
            win_rate=stats['win_rate'],
            avg_pnl=stats['avg_pnl'],
            max_drawdown=stats['max_drawdown']
        )
        
        # Determine promotion eligibility
        promotion_eligible = metrics.meets_promotion_criteria(self.min_sharpe_for_promotion)
        
        if promotion_eligible:
            promotion_reason = (
                f"Agent meets promotion criteria: Sharpe ratio {metrics.sharpe_ratio:.3f} > "
                f"{self.min_sharpe_for_promotion}"
            )
        else:
            promotion_reason = (
                f"Agent does not meet promotion criteria: Sharpe ratio {metrics.sharpe_ratio:.3f} <= "
                f"{self.min_sharpe_for_promotion}"
            )
        
        # Create evaluation result
        result = EvaluationResult(
            agent_id=agent_id,
            symbol=symbol,
            evaluation_date=datetime.now(),
            eval_start_date=eval_start,
            eval_end_date=eval_end,
            metrics=metrics,
            promotion_eligible=promotion_eligible,
            promotion_reason=promotion_reason,
            detailed_stats=stats
        )
        
        # Add to history
        self.evaluation_history.append(result)
        
        # Log results
        log.info("Evaluation Results:")
        log.info(f"  Sharpe Ratio: {metrics.sharpe_ratio:.3f}")
        log.info(f"  Total Return: {metrics.total_return:.2%}")
        log.info(f"  Number of Trades: {metrics.num_trades}")
        log.info(f"  Win Rate: {metrics.win_rate:.2%}")
        log.info(f"  Average P&L: {metrics.avg_pnl:.2f}")
        log.info(f"  Max Drawdown: {metrics.max_drawdown:.2%}")
        log.info(f"  Promotion Eligible: {promotion_eligible}")
        log.info(f"  Reason: {promotion_reason}")
        
        return result
    
    def promote_to_paper_trading(
        self,
        agent: PPO,
        agent_id: str,
        evaluation_result: EvaluationResult,
        model_dir: Path
    ) -> bool:
        """
        Promote agent to paper trading if it meets criteria.
        
        Requirements: 12.5 - Promote to paper trading if Sharpe > 1.5
        
        Args:
            agent: Trained PPO agent
            agent_id: Unique identifier for agent
            evaluation_result: Evaluation result
            model_dir: Path to model directory
        
        Returns:
            True if promoted, False otherwise
        """
        if not evaluation_result.promotion_eligible:
            log.warning(f"Agent {agent_id} not eligible for promotion")
            log.warning(f"Reason: {evaluation_result.promotion_reason}")
            return False
        
        log.info(f"Promoting agent {agent_id} to paper trading")
        
        # Update metadata with promotion information
        metadata_path = model_dir / "metadata.json"
        
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Add promotion information
        metadata['promotion_status'] = 'PAPER_TRADING'
        metadata['promotion_date'] = datetime.now().isoformat()
        metadata['promotion_sharpe'] = evaluation_result.metrics.sharpe_ratio
        metadata['promotion_return'] = evaluation_result.metrics.total_return
        metadata['evaluation_period'] = {
            'start': evaluation_result.eval_start_date.isoformat(),
            'end': evaluation_result.eval_end_date.isoformat()
        }
        
        # Save updated metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        log.info(f"Agent {agent_id} promoted to paper trading")
        log.info(f"  Sharpe Ratio: {evaluation_result.metrics.sharpe_ratio:.3f}")
        log.info(f"  Total Return: {evaluation_result.metrics.total_return:.2%}")
        
        return True
    
    def compare_agents(
        self,
        agent1: PPO,
        agent1_id: str,
        agent2: PPO,
        agent2_id: str,
        symbol: str,
        timeframe: str = "M15",
        eval_start: Optional[datetime] = None,
        eval_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Compare two agents on the same evaluation data.
        
        Args:
            agent1: First agent
            agent1_id: First agent ID
            agent2: Second agent
            agent2_id: Second agent ID
            symbol: Trading symbol
            timeframe: Timeframe for evaluation
            eval_start: Evaluation start date
            eval_end: Evaluation end date
        
        Returns:
            Dictionary with comparison results
        """
        log.info(f"Comparing agents {agent1_id} vs {agent2_id}")
        
        # Evaluate both agents
        result1 = self.evaluate_agent_comprehensive(
            agent1, agent1_id, symbol, timeframe, eval_start, eval_end
        )
        
        result2 = self.evaluate_agent_comprehensive(
            agent2, agent2_id, symbol, timeframe, eval_start, eval_end
        )
        
        # Compare metrics
        comparison = {
            'agent1_id': agent1_id,
            'agent2_id': agent2_id,
            'symbol': symbol,
            'evaluation_period': {
                'start': result1.eval_start_date.isoformat(),
                'end': result1.eval_end_date.isoformat()
            },
            'metrics_comparison': {
                'sharpe_ratio': {
                    'agent1': result1.metrics.sharpe_ratio,
                    'agent2': result2.metrics.sharpe_ratio,
                    'winner': agent1_id if result1.metrics.sharpe_ratio > result2.metrics.sharpe_ratio else agent2_id
                },
                'total_return': {
                    'agent1': result1.metrics.total_return,
                    'agent2': result2.metrics.total_return,
                    'winner': agent1_id if result1.metrics.total_return > result2.metrics.total_return else agent2_id
                },
                'win_rate': {
                    'agent1': result1.metrics.win_rate,
                    'agent2': result2.metrics.win_rate,
                    'winner': agent1_id if result1.metrics.win_rate > result2.metrics.win_rate else agent2_id
                },
                'max_drawdown': {
                    'agent1': result1.metrics.max_drawdown,
                    'agent2': result2.metrics.max_drawdown,
                    'winner': agent1_id if result1.metrics.max_drawdown < result2.metrics.max_drawdown else agent2_id
                }
            },
            'promotion_status': {
                'agent1': result1.promotion_eligible,
                'agent2': result2.promotion_eligible
            }
        }
        
        # Determine overall winner
        wins = {agent1_id: 0, agent2_id: 0}
        for metric, values in comparison['metrics_comparison'].items():
            wins[values['winner']] += 1
        
        comparison['overall_winner'] = agent1_id if wins[agent1_id] > wins[agent2_id] else agent2_id
        
        log.info(f"Comparison complete: {comparison['overall_winner']} wins overall")
        
        return comparison
    
    def get_evaluation_history(
        self,
        agent_id: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[EvaluationResult]:
        """
        Get evaluation history, optionally filtered by agent ID or symbol.
        
        Args:
            agent_id: Optional agent ID filter
            symbol: Optional symbol filter
        
        Returns:
            List of evaluation results
        """
        results = self.evaluation_history
        
        if agent_id:
            results = [r for r in results if r.agent_id == agent_id]
        
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        
        return results
    
    def generate_evaluation_report(
        self,
        evaluation_result: EvaluationResult,
        output_path: Optional[Path] = None
    ) -> str:
        """
        Generate a detailed evaluation report.
        
        Args:
            evaluation_result: Evaluation result
            output_path: Optional path to save report
        
        Returns:
            Report as string
        """
        report = []
        report.append("=" * 80)
        report.append("RL AGENT EVALUATION REPORT")
        report.append("=" * 80)
        report.append("")
        report.append(f"Agent ID: {evaluation_result.agent_id}")
        report.append(f"Symbol: {evaluation_result.symbol}")
        report.append(f"Evaluation Date: {evaluation_result.evaluation_date}")
        report.append(f"Evaluation Period: {evaluation_result.eval_start_date} to {evaluation_result.eval_end_date}")
        report.append("")
        report.append("-" * 80)
        report.append("PERFORMANCE METRICS")
        report.append("-" * 80)
        report.append(f"Sharpe Ratio:        {evaluation_result.metrics.sharpe_ratio:>10.3f}")
        report.append(f"Total Return:        {evaluation_result.metrics.total_return:>10.2%}")
        report.append(f"Number of Trades:    {evaluation_result.metrics.num_trades:>10}")
        report.append(f"Win Rate:            {evaluation_result.metrics.win_rate:>10.2%}")
        report.append(f"Average P&L:         {evaluation_result.metrics.avg_pnl:>10.2f}")
        report.append(f"Max Drawdown:        {evaluation_result.metrics.max_drawdown:>10.2%}")
        report.append("")
        report.append("-" * 80)
        report.append("PROMOTION STATUS")
        report.append("-" * 80)
        report.append(f"Eligible: {evaluation_result.promotion_eligible}")
        report.append(f"Reason: {evaluation_result.promotion_reason}")
        report.append("")
        report.append("-" * 80)
        report.append("DETAILED STATISTICS")
        report.append("-" * 80)
        for key, value in evaluation_result.detailed_stats.items():
            if isinstance(value, float):
                report.append(f"{key:.<30} {value:>15.4f}")
            else:
                report.append(f"{key:.<30} {value:>15}")
        report.append("")
        report.append("=" * 80)
        
        report_text = "\n".join(report)
        
        # Save to file if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report_text)
            log.info(f"Evaluation report saved to {output_path}")
        
        return report_text
