# src/core/context/image.py
"""Image context management for request-scoped image data.

Stores attached images in a ContextVar so that image tools
can access them without passing large base64 data through the prompt.
"""

from collections import OrderedDict
from contextvars import ContextVar
from typing import Any

_attached_images: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "attached_images", default=None
)


def set_attached_images(images: list[dict[str, Any]]) -> None:
    """Set the attached images for the current request context.

    Args:
        images: List of processed images with 'bytes', 'base64', 'mime_type', 'name' keys.
    """
    _attached_images.set(images)


def get_attached_images() -> list[dict[str, Any]]:
    """Get the attached images from the current request context.

    Returns:
        List of attached images, or empty list if none.
    """
    return _attached_images.get() or []


def clear_attached_images() -> None:
    """Clear attached images after request is complete."""
    _attached_images.set(None)


def get_attached_image_by_index(index: int = 0) -> dict[str, Any] | None:
    """Get a specific attached image by index.

    Args:
        index: Image index (0-based). Default: 0 (first image).

    Returns:
        Image dict with 'bytes', 'base64', 'mime_type', 'name' keys, or None.
    """
    images = _attached_images.get()
    if images is None:
        return None
    if 0 <= index < len(images):
        return images[index]
    return None


# =============================================================================
# Generated Images Storage (for image generation tools)
# =============================================================================

_MAX_GENERATED_IMAGES = 100
_MAX_THREAD_CACHE = 50

_generated_images: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
_thread_image_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()


def store_generated_images(request_id: str, images: list[dict[str, Any]]) -> None:
    """Store generated images by request ID (thread-safe storage).

    Maintains a bounded cache of max 100 entries. When the limit is reached,
    the oldest entry is removed to prevent unbounded memory growth.
    """
    if len(_generated_images) >= _MAX_GENERATED_IMAGES:
        _generated_images.popitem(last=False)
    _generated_images[request_id] = images


def get_generated_images(request_id: str) -> list[dict[str, Any]]:
    """Get and remove generated images by request ID."""
    return _generated_images.pop(request_id, [])


def cache_images_for_thread(thread_key: str, images: list[dict[str, Any]]) -> None:
    """Cache images for a thread to enable cross-message editing.

    Maintains a bounded cache of max 50 entries. When the limit is reached,
    the oldest entry is removed to prevent unbounded memory growth.
    """
    if len(_thread_image_cache) >= _MAX_THREAD_CACHE:
        _thread_image_cache.popitem(last=False)
    _thread_image_cache[thread_key] = images


def get_cached_images_for_thread(thread_key: str) -> list[dict[str, Any]]:
    """Get cached images for a thread."""
    return _thread_image_cache.get(thread_key, [])


def clear_all_caches() -> None:
    """Clear all global image caches.

    Removes all entries from both _generated_images and _thread_image_cache.
    Useful for cleanup during shutdown or testing.
    """
    _generated_images.clear()
    _thread_image_cache.clear()
