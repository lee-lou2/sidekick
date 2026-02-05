# src/core/lifecycle.py
"""Lifecycle management for singleton components.

Provides a centralized manager for startup and shutdown of all
singleton components (SchedulerManager, etc.) in the application.

Example:
    >>> from src.core.lifecycle import get_lifecycle_manager
    >>> from src.core.scheduler import SchedulerManager
    >>>
    >>> lm = get_lifecycle_manager()
    >>> lm.register("scheduler", SchedulerManager.get_instance())
    >>> await lm.startup()
    >>> # ... application runs ...
    >>> await lm.shutdown()
"""

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LifecycleComponent(Protocol):
    """Protocol for components with lifecycle management."""

    def shutdown(self) -> None:
        """Shutdown the component and release resources."""
        ...


class LifecycleManager:
    """Manages startup and shutdown of all singleton components."""

    def __init__(self) -> None:
        self._components: list[tuple[str, Any]] = []
        self._started = False

    def register(self, name: str, component: Any) -> None:
        """Register a component. Must have start()/startup() and shutdown()."""
        self._components.append((name, component))
        logger.debug("Registered lifecycle component: %s", name)

    async def startup(self) -> None:
        """Start all registered components in order.

        Skips if already started. Components can implement either
        start() or startup() methods.
        """
        if self._started:
            logger.debug("Lifecycle manager already started")
            return

        for name, component in self._components:
            logger.info("Starting %s", name)
            if hasattr(component, "start"):
                component.start()
            elif hasattr(component, "startup"):
                component.startup()

        self._started = True
        logger.info(
            "All lifecycle components started (%d total)", len(self._components)
        )

    async def shutdown(self) -> None:
        """Shutdown all registered components in reverse order.

        Components are shutdown in reverse registration order to handle
        dependencies properly.
        """
        if not self._started:
            logger.debug("Lifecycle manager not started, skipping shutdown")
            return

        for name, component in reversed(self._components):
            logger.info("Stopping %s", name)
            try:
                if hasattr(component, "shutdown"):
                    component.shutdown()
            except Exception as e:
                logger.error("Error shutting down %s: %s", name, e)

        self._started = False
        logger.info("All lifecycle components stopped")

    @property
    def is_started(self) -> bool:
        """Check if the manager has started all components.

        Returns:
            True if startup() has been called and completed.
        """
        return self._started

    @property
    def component_count(self) -> int:
        """Get the number of registered components.

        Returns:
            Number of registered components.
        """
        return len(self._components)


# Singleton instance
_lifecycle_manager: LifecycleManager | None = None


def get_lifecycle_manager() -> LifecycleManager:
    """Get the global lifecycle manager singleton.

    Returns:
        The global LifecycleManager instance.
    """
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = LifecycleManager()
    return _lifecycle_manager


def reset_lifecycle_manager() -> None:
    """Reset the global lifecycle manager (for testing).

    Creates a fresh instance on next get_lifecycle_manager() call.
    """
    global _lifecycle_manager
    _lifecycle_manager = None
