"""Event subscribers. Every module exposes ``register(app)`` returning its plugin object."""

from __future__ import annotations

PLUGIN_MODULES = (
    "plugins.audit",
    "plugins.cache_invalidator",
    "plugins.metrics",
    "plugins.email_notifier",
    "plugins.loyalty",
    "plugins.sms_notifier",
    "plugins.fraud_check",
    "plugins.slack_alerts",
    "plugins.analytics",
    "plugins.search_indexer",
    "plugins.stock_guard",
    "plugins.ops_dashboard",
    "plugins.warehouse_sync",
    "plugins.webhooks",
    "plugins.reporting",
)
