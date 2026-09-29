"""Minimal in-process event bus (spec §31).

Phase 1-N: synchronous, in-process pub/sub - good enough to decouple modules
(e.g. Notifications reacting to VaccinationDue without Livestock importing
Notifications directly) without introducing infra complexity yet.

Extraction path: swap `publish`'s body for a RabbitMQ/Kafka producer call and
keep every call site (`await publish("AnimalAcquired", {...})`) unchanged.
"""
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger("events")

Handler = Callable[[dict[str, Any]], Awaitable[None]]

_subscribers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_name: str, handler: Handler) -> None:
    _subscribers[event_name].append(handler)


async def publish(event_name: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget within the current request; handler errors are logged,
    never raised, so a notification bug can't fail the primary business
    transaction (spec §31: services should not become tightly coupled)."""
    logger.info("event.published", extra={"event": event_name, "payload": payload})
    for handler in _subscribers.get(event_name, []):
        try:
            await handler(payload)
        except Exception:  # noqa: BLE001
            logger.exception("event handler failed", extra={"event": event_name})
