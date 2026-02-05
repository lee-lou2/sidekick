# src/core/context/__init__.py
"""Request context management for cross-cutting concerns.

This module provides async-safe context storage using ContextVar for:
- Attached images (for image editing tools)
- Other request-scoped data that needs to be shared across layers
"""

from src.core.context.image import (
    cache_images_for_thread,
    clear_all_caches,
    clear_attached_images,
    get_attached_image_by_index,
    get_attached_images,
    get_cached_images_for_thread,
    get_generated_images,
    set_attached_images,
    store_generated_images,
)

__all__ = [
    "set_attached_images",
    "get_attached_images",
    "get_attached_image_by_index",
    "clear_attached_images",
    "store_generated_images",
    "get_generated_images",
    "cache_images_for_thread",
    "get_cached_images_for_thread",
    "clear_all_caches",
]
