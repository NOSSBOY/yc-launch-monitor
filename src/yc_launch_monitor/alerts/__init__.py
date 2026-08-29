"""Alerting package for YC Launch Monitor."""

from __future__ import annotations

from yc_launch_monitor.alerts.slack import SlackNotifier

__all__ = ["SlackNotifier"]
