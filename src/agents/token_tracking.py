"""Token & Cost Tracking — Monitor AI model usage and costs.

Provides comprehensive tracking of token usage and costs across all AI
providers (OpenAI, Anthropic, HuggingFace, DeepSeek, Ollama, etc.).

Features:
- Per-request token counting (prompt + completion)
- Cost calculation with provider-specific pricing
- Budget management with alerts and hard limits
- Usage analytics by agent, tenant, provider, model
- Real-time cost dashboards
- Rate limiting based on token budgets
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("token_tracking")


class PricingModel(Enum):
    """Pricing model types."""

    PER_TOKEN = "per_token"
    PER_REQUEST = "per_request"
    PER_SECOND = "per_second"


@dataclass
class ModelPricing:
    """Pricing information for a specific model."""

    provider: str
    model: str
    input_cost_per_1k: float = 0.0  # USD per 1K input tokens
    output_cost_per_1k: float = 0.0  # USD per 1K output tokens
    pricing_model: PricingModel = PricingModel.PER_TOKEN
    effective_date: str = "2025-01-01"

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate the cost for a request."""
        if self.pricing_model == PricingModel.PER_TOKEN:
            input_cost = (input_tokens / 1000.0) * self.input_cost_per_1k
            output_cost = (output_tokens / 1000.0) * self.output_cost_per_1k
            return round(input_cost + output_cost, 6)
        if self.pricing_model == PricingModel.PER_REQUEST:
            return self.input_cost_per_1k
        return 0.0


@dataclass
class TokenUsageRecord:
    """Record of a single token usage event."""

    record_id: str = ""
    timestamp: float = field(default_factory=time.time)
    tenant_id: str = "default"
    agent_id: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    request_type: str = "chat"  # chat, completion, embedding, image
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"usage-{uuid.uuid4().hex[:8]}"
        self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class BudgetAlert:
    """An alert triggered when a budget threshold is reached."""

    alert_id: str = ""
    tenant_id: str = ""
    budget_type: str = ""  # daily, monthly, total
    threshold_pct: float = 0.0
    current_spend: float = 0.0
    budget_limit: float = 0.0
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False

    def __post_init__(self) -> None:
        if not self.alert_id:
            self.alert_id = f"alert-{uuid.uuid4().hex[:8]}"


# ── Default Pricing Table ──────────────────────────────────

DEFAULT_PRICING: dict[str, ModelPricing] = {
    # OpenAI
    "openai/gpt-4o": ModelPricing("openai", "gpt-4o", 0.0025, 0.01),
    "openai/gpt-4o-mini": ModelPricing("openai", "gpt-4o-mini", 0.00015, 0.0006),
    "openai/gpt-4-turbo": ModelPricing("openai", "gpt-4-turbo", 0.01, 0.03),
    "openai/gpt-3.5-turbo": ModelPricing("openai", "gpt-3.5-turbo", 0.0005, 0.0015),
    "openai/text-embedding-3-small": ModelPricing("openai", "text-embedding-3-small", 0.00002, 0.0),
    "openai/text-embedding-3-large": ModelPricing("openai", "text-embedding-3-large", 0.00013, 0.0),
    "openai/dall-e-3": ModelPricing("openai", "dall-e-3", 0.04, 0.0, PricingModel.PER_REQUEST),
    # Anthropic
    "anthropic/claude-3.5-sonnet": ModelPricing("anthropic", "claude-3.5-sonnet", 0.003, 0.015),
    "anthropic/claude-3-opus": ModelPricing("anthropic", "claude-3-opus", 0.015, 0.075),
    "anthropic/claude-3-haiku": ModelPricing("anthropic", "claude-3-haiku", 0.00025, 0.00125),
    # DeepSeek
    "deepseek/deepseek-chat": ModelPricing("deepseek", "deepseek-chat", 0.00014, 0.00028),
    "deepseek/deepseek-coder": ModelPricing("deepseek", "deepseek-coder", 0.00014, 0.00028),
    # HuggingFace
    "huggingface/inference": ModelPricing("huggingface", "inference", 0.0, 0.0),
    # Ollama (local, free)
    "ollama/*": ModelPricing("ollama", "*", 0.0, 0.0),
}


class TokenCostTracker:
    """Track token usage and costs across all AI providers.

    Provides:
    - Real-time cost tracking per request
    - Budget management with configurable limits
    - Usage analytics by provider, model, agent, tenant
    - Alert system for budget thresholds
    - Persistent storage via SQLite

    Usage:
        tracker = TokenCostTracker.get_instance()
        tracker.record_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=150,
            output_tokens=500,
            tenant_id="tenant-1",
            agent_id="agent-1",
        )
        summary = tracker.get_usage_summary(tenant_id="tenant-1")
    """

    _instance: TokenCostTracker | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = "token_usage.db") -> None:
        self._db_path = db_path
        self._pricing: dict[str, ModelPricing] = dict(DEFAULT_PRICING)
        self._budgets: dict[str, dict[str, float]] = {}  # tenant_id -> {daily, monthly, total}
        self._alerts: list[BudgetAlert] = []
        self._alert_callbacks: list[Any] = []
        self._conn: sqlite3.Connection | None = None
        self._local_lock = threading.Lock()
        self._init_db()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> TokenCostTracker:
        """Get or create the singleton tracker."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def _init_db(self) -> None:
        """Initialize SQLite for persistent token usage storage."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                record_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                agent_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                request_type TEXT NOT NULL DEFAULT 'chat',
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_tenant ON token_usage(tenant_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_provider ON token_usage(provider, model)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON token_usage(timestamp)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_alerts (
                alert_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                budget_type TEXT NOT NULL,
                threshold_pct REAL NOT NULL,
                current_spend REAL NOT NULL,
                budget_limit REAL NOT NULL,
                timestamp REAL NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    # ── Pricing ─────────────────────────────────────────────

    def set_pricing(self, provider: str, model: str, pricing: ModelPricing) -> None:
        """Set or update pricing for a specific model."""
        key = f"{provider}/{model}"
        self._pricing[key] = pricing

    def get_pricing(self, provider: str, model: str) -> ModelPricing:
        """Get pricing for a model, falling back to defaults."""
        key = f"{provider}/{model}"
        if key in self._pricing:
            return self._pricing[key]

        # Try wildcard for provider
        wildcard = f"{provider}/*"
        if wildcard in self._pricing:
            return self._pricing[wildcard]

        # Default: free
        return ModelPricing(provider=provider, model=model)

    # ── Recording ───────────────────────────────────────────

    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tenant_id: str = "default",
        agent_id: str = "",
        request_type: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> TokenUsageRecord:
        """Record a token usage event.

        Args:
            provider: AI provider name (openai, anthropic, etc.)
            model: Model identifier (gpt-4o, claude-3.5-sonnet, etc.)
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.
            tenant_id: Tenant identifier for multi-tenant tracking.
            agent_id: Agent identifier if used by an agent.
            request_type: Type of request (chat, completion, embedding, image).
            metadata: Additional metadata.

        Returns:
            The created TokenUsageRecord with calculated cost.
        """
        pricing = self.get_pricing(provider, model)
        cost = pricing.calculate_cost(input_tokens, output_tokens)

        record = TokenUsageRecord(
            tenant_id=tenant_id,
            agent_id=agent_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            request_type=request_type,
            metadata=metadata or {},
        )

        # Persist
        self._persist_record(record)

        # Check budgets
        self._check_budgets(tenant_id, cost)

        # Sanitized log: avoid logging exact tokens/cost which could be sensitive
        logger.debug(
            "Token usage: provider=%s model=%s tokens=%d cost_usd=<redacted>",
            provider,
            model,
            record.total_tokens,
        )

        # Check budgets
        self._check_budgets(tenant_id)

        return record

    def _persist_record(self, record: TokenUsageRecord) -> None:
        """Persist a usage record to SQLite."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO token_usage
                   (record_id, timestamp, tenant_id, agent_id, provider, model,
                    input_tokens, output_tokens, total_tokens, cost_usd, request_type, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    record.timestamp,
                    record.tenant_id,
                    record.agent_id,
                    record.provider,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.total_tokens,
                    record.cost_usd,
                    record.request_type,
                    str(record.metadata),
                ),
            )
            self._conn.commit()
        except sqlite3.Error:
            # Sanitized error log: avoid logging exception details which might contain sensitive info
            logger.error("Failed to persist token usage: <error>")

    # ── Budgets ─────────────────────────────────────────────

    def set_budget(
        self,
        tenant_id: str,
        daily_limit: float | None = None,
        monthly_limit: float | None = None,
        total_limit: float | None = None,
    ) -> None:
        """Set budget limits for a tenant.

        Args:
            tenant_id: The tenant to set budgets for.
            daily_limit: Maximum daily spend in USD.
            monthly_limit: Maximum monthly spend in USD.
            total_limit: Maximum total spend in USD (lifetime).
        """
        if tenant_id not in self._budgets:
            self._budgets[tenant_id] = {}

        if daily_limit is not None:
            self._budgets[tenant_id]["daily"] = daily_limit
        if monthly_limit is not None:
            self._budgets[tenant_id]["monthly"] = monthly_limit
        if total_limit is not None:
            self._budgets[tenant_id]["total"] = total_limit

    def _check_budgets(self, tenant_id: str) -> None:
        """Check if current spend triggers any budget alerts."""
        budgets = self._budgets.get(tenant_id, {})
        if not budgets:
            return

        # Get current spend
        now = time.time()
        day_start = now - (now % 86400)
        month_start = now - (now % (86400 * 30))  # Approximate

        daily_spend = self._get_spend(tenant_id, day_start, now)
        monthly_spend = self._get_spend(tenant_id, month_start, now)
        total_spend = self._get_spend(tenant_id, 0, now)

        # Check thresholds at 50%, 75%, 90%, 100%
        for threshold_pct in [50, 75, 90, 100]:
            for budget_type, current_spend in [
                ("daily", daily_spend),
                ("monthly", monthly_spend),
                ("total", total_spend),
            ]:
                limit = budgets.get(budget_type, 0)
                if limit <= 0:
                    continue

                pct = (current_spend / limit) * 100
                if pct >= threshold_pct and pct < threshold_pct + 5:
                    self._fire_alert(
                        tenant_id, budget_type, threshold_pct, current_spend, limit
                    )

    def _fire_alert(
        self,
        tenant_id: str,
        budget_type: str,
        threshold_pct: float,
        current_spend: float,
        budget_limit: float,
    ) -> None:
        """Fire a budget alert."""
        alert = BudgetAlert(
            tenant_id=tenant_id,
            budget_type=budget_type,
            threshold_pct=threshold_pct,
            current_spend=current_spend,
            budget_limit=budget_limit,
        )

        self._alerts.append(alert)

        # Persist alert
        if self._conn is not None:
            try:
                self._conn.execute(
                    """INSERT INTO budget_alerts
                       (alert_id, tenant_id, budget_type, threshold_pct,
                        current_spend, budget_limit, timestamp, acknowledged)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        alert.alert_id,
                        alert.tenant_id,
                        alert.budget_type,
                        alert.threshold_pct,
                        alert.current_spend,
                        alert.budget_limit,
                        alert.timestamp,
                    ),
                )
                self._conn.commit()
            except sqlite3.Error:
                pass

        # Fire callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as exc:
                logger.error("Budget alert callback error: %s", exc)

        logger.warning(
            "Budget alert: %s %s at %.0f%% ($%.2f / $%.2f)",
            tenant_id,
            budget_type,
            threshold_pct,
            current_spend,
            budget_limit,
        )

    # legítimo: callback dinámico, signature depende del evento (skill §1.2)
    def register_alert_callback(self, callback: Any) -> None:
        """Register a callback for budget alerts."""
        self._alert_callbacks.append(callback)

    # ── Analytics ───────────────────────────────────────────

    def get_spend(
        self,
        tenant_id: str = "default",
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> float:
        """Get total spend for a tenant in a time range."""
        return self._get_spend(tenant_id, start_time or 0, end_time or time.time())

    def _get_spend(
        self,
        tenant_id: str,
        start_time: float,
        end_time: float,
    ) -> float:
        """Get total spend from the database."""
        if self._conn is None:
            return 0.0
        try:
            cursor = self._conn.execute(
                """SELECT SUM(cost_usd) FROM token_usage
                   WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?""",
                (tenant_id, start_time, end_time),
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else 0.0
        except sqlite3.Error:
            return 0.0

    def get_usage_summary(
        self,
        tenant_id: str = "default",
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> dict[str, Any]:
        """Get a comprehensive usage summary for a tenant.

        Returns:
            Dict with total tokens, costs, breakdown by provider/model.
        """
        end = end_time or time.time()
        start = start_time or 0

        if self._conn is None:
            return {"error": "Database not available"}

        try:
            # Overall totals
            cursor = self._conn.execute(
                """SELECT
                     COUNT(*) as requests,
                     SUM(input_tokens) as total_input,
                     SUM(output_tokens) as total_output,
                     SUM(total_tokens) as total_tokens,
                     SUM(cost_usd) as total_cost
                   FROM token_usage
                   WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?""",
                (tenant_id, start, end),
            )
            row = cursor.fetchone()

            # By provider
            cursor2 = self._conn.execute(
                """SELECT provider, model,
                     COUNT(*) as requests,
                     SUM(input_tokens) as total_input,
                     SUM(output_tokens) as total_output,
                     SUM(total_tokens) as total_tokens,
                     SUM(cost_usd) as total_cost
                   FROM token_usage
                   WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
                   GROUP BY provider, model
                   ORDER BY total_cost DESC""",
                (tenant_id, start, end),
            )
            by_provider = [
                {
                    "provider": r[0],
                    "model": r[1],
                    "requests": r[2],
                    "input_tokens": r[3] or 0,
                    "output_tokens": r[4] or 0,
                    "total_tokens": r[5] or 0,
                    "cost_usd": round(r[6] or 0, 6),
                }
                for r in cursor2.fetchall()
            ]

            # By agent
            cursor3 = self._conn.execute(
                """SELECT agent_id,
                     COUNT(*) as requests,
                     SUM(total_tokens) as total_tokens,
                     SUM(cost_usd) as total_cost
                   FROM token_usage
                   WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
                   GROUP BY agent_id
                   ORDER BY total_cost DESC""",
                (tenant_id, start, end),
            )
            by_agent = [
                {
                    "agent_id": r[0],
                    "requests": r[1],
                    "total_tokens": r[2] or 0,
                    "cost_usd": round(r[3] or 0, 6),
                }
                for r in cursor3.fetchall()
            ]

            return {
                "tenant_id": tenant_id,
                "period": {"start": start, "end": end},
                "total_requests": row[0] if row else 0,
                "total_input_tokens": row[1] if row else 0,
                "total_output_tokens": row[2] if row else 0,
                "total_tokens": row[3] if row else 0,
                "total_cost_usd": round(row[4] if row and row[4] else 0, 6),
                "by_provider_model": by_provider,
                "by_agent": by_agent,
            }
        except sqlite3.Error as exc:
            return {"error": str(exc)}

    def get_daily_usage(
        self,
        tenant_id: str = "default",
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get daily usage for the last N days."""
        if self._conn is None:
            return []

        now = time.time()
        start = now - (days * 86400)

        try:
            cursor = self._conn.execute(
                """SELECT
                     DATE(timestamp, 'unixepoch') as date,
                     COUNT(*) as requests,
                     SUM(total_tokens) as total_tokens,
                     SUM(cost_usd) as total_cost
                   FROM token_usage
                   WHERE tenant_id = ? AND timestamp >= ?
                   GROUP BY DATE(timestamp, 'unixepoch')
                   ORDER BY date DESC""",
                (tenant_id, start),
            )
            return [
                {
                    "date": r[0],
                    "requests": r[1],
                    "total_tokens": r[2] or 0,
                    "cost_usd": round(r[3] or 0, 6),
                }
                for r in cursor.fetchall()
            ]
        except sqlite3.Error:
            return []

    # ── Rate Limiting ───────────────────────────────────────

    def check_budget_available(self, tenant_id: str, estimated_cost: float = 0.0) -> bool:
        """Check if a tenant has budget available for a request.

        Returns:
            True if the request is within budget limits.
        """
        budgets = self._budgets.get(tenant_id, {})
        if not budgets:
            return True  # No budget set = unlimited

        now = time.time()
        day_start = now - (now % 86400)

        if "daily" in budgets:
            daily_spend = self._get_spend(tenant_id, day_start, now)
            if daily_spend + estimated_cost > budgets["daily"]:
                logger.warning(
                    "Daily budget exceeded for %s: $%.2f / $%.2f",
                    tenant_id,
                    daily_spend,
                    budgets["daily"],
                )
                return False

        if "monthly" in budgets:
            month_start = now - (now % (86400 * 30))
            monthly_spend = self._get_spend(tenant_id, month_start, now)
            if monthly_spend + estimated_cost > budgets["monthly"]:
                return False

        if "total" in budgets:
            total_spend = self._get_spend(tenant_id, 0, now)
            if total_spend + estimated_cost > budgets["total"]:
                return False

        return True

    # ── Management ──────────────────────────────────────────

    def get_alerts(
        self,
        tenant_id: str | None = None,
        unacknowledged_only: bool = False,
    ) -> list[BudgetAlert]:
        """Get budget alerts."""
        alerts = list(self._alerts)
        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]
        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a budget alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get tracker statistics."""
        return {
            "total_records": self._count_records(),
            "pricing_models": len(self._pricing),
            "tenants_with_budgets": len(self._budgets),
            "total_alerts": len(self._alerts),
            "unacknowledged_alerts": sum(1 for a in self._alerts if not a.acknowledged),
        }

    def _count_records(self) -> int:
        """Count total usage records."""
        if self._conn is None:
            return 0
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM token_usage")
            return cursor.fetchone()[0]
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
