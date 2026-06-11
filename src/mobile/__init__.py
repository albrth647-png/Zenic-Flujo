"""Zenic-Flijo Mobile Architecture — Android & iOS client support.

Architecture Decision: THIN CLIENT + SERVER-SIDE ENGINE
=======================================================

Zenic-Flijo's core engine (Orbital, NLU, Workflows, Agents, Connectors)
runs 100% on the SERVER. The mobile device is a THIN CLIENT that
communicates via REST API, WebSocket, and Push Notifications.

This solves the Android constraints:
- No root needed → Everything runs server-side
- Scoped storage → Server handles file I/O, mobile shows results
- Background limits → Server runs 24/7, mobile receives push notifications
- Battery optimization → Minimal CPU on device, heavy lifting on server

Mobile Interaction Modes:
1. PWA (Progressive Web App) — installable from browser, no Play Store needed
2. REST API Client — any HTTP client can interact
3. WebSocket Real-time — live workflow status updates
4. Push Notifications — Firebase Cloud Messaging for alerts
"""

from src.mobile.api import MobileAPIRouter
from src.mobile.push import PushNotificationService
from src.mobile.sync import OfflineSyncManager

__all__ = [
    "MobileAPIRouter",
    "PushNotificationService",
    "OfflineSyncManager",
]
