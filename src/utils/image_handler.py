# src/utils/image_handler.py
"""Image handling utilities for MCP tool outputs.

Extracts and processes images from MCP tool responses (e.g., Playwright screenshots).
Supports detection, extraction, and conversion of base64 encoded images.
"""

import base64
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ImageData:
    """Container for image data extracted from MCP tool output.

    Attributes:
        data: Raw image bytes (decoded from base64).
        mime_type: MIME type of the image (e.g., "image/png").
        filename: Optional filename for the image.
    """

    data: bytes
    mime_type: str
    filename: str | None = None

    @property
    def extension(self) -> str:
        """Get file extension from MIME type."""
        # image/png -> png, image/jpeg -> jpeg
        return self.mime_type.split("/")[-1] if "/" in self.mime_type else "png"

    def to_data_uri(self) -> str:
        """Convert to data URI format for embedding in HTML/JSON."""
        b64 = base64.b64encode(self.data).decode("utf-8")
        return f"data:{self.mime_type};base64,{b64}"


def _is_image_item(item: Any) -> bool:
    """Check if a content item contains image data."""
    if not isinstance(item, dict):
        return False
    item_type = item.get("type")
    if item_type == "image":
        return True
    # Playwright MCP returns images as type="binary" with media_type="image/..."
    if item_type == "binary":
        media_type = item.get("media_type", "")
        return media_type.startswith("image/")
    return False


def has_images(result: Any) -> bool:
    """Check if tool result contains image data.

    Supports:
    - MCP format: type="image"
    - Playwright MCP format: type="binary" with media_type="image/..."

    Args:
        result: Tool output to check.

    Returns:
        True if the result contains at least one image.
    """
    if not isinstance(result, dict):
        return False

    content = result.get("content")
    if not isinstance(content, list):
        return False

    return any(_is_image_item(item) for item in content)


def extract_data_uri_images(text: str) -> list[ImageData]:
    """Extract images from base64 data URIs in text.

    Parses text for data URIs like: data:image/png;base64,...

    Args:
        text: Text that may contain data URI images.

    Returns:
        List of ImageData objects extracted from data URIs.
    """
    import re

    images: list[ImageData] = []

    # Pattern for data URI: data:image/xxx;base64,<base64data>
    pattern = r"data:(image/[a-zA-Z0-9+-]+);base64,([A-Za-z0-9+/=]+)"
    matches = re.findall(pattern, text)

    for idx, (mime_type, b64_data) in enumerate(matches):
        try:
            image_bytes = base64.b64decode(b64_data)
            ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
            filename = f"generated_{idx}.{ext}"

            images.append(
                ImageData(
                    data=image_bytes,
                    mime_type=mime_type,
                    filename=filename,
                )
            )
            logger.debug(
                f"Extracted data URI image: {filename} ({len(image_bytes)} bytes)"
            )
        except Exception as e:
            logger.warning(f"Failed to decode data URI image at index {idx}: {e}")
            continue

    return images


def extract_images_from_result(result: Any) -> list[ImageData]:
    """Extract all images from tool output.

    Supports multiple formats:
    1. MCP format: {"content": [{"type": "image", "data": "<base64>", "mimeType": "..."}]}
    2. Data URI in text: {"content": [{"type": "text", "text": "data:image/png;base64,..."}]}

    Args:
        result: Tool output containing potential images.

    Returns:
        List of ImageData objects extracted from the result.
        Empty list if no images found or on error.
    """
    images: list[ImageData] = []

    if not isinstance(result, dict):
        return images

    content = result.get("content")
    if not isinstance(content, list):
        return images

    for idx, item in enumerate(content):
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")

        # Handle MCP image format (type="image")
        if item_type == "image":
            data_b64 = item.get("data")
            if not data_b64 or not isinstance(data_b64, str):
                logger.warning("Image item missing 'data' field at index %d", idx)
                continue

            try:
                image_bytes = base64.b64decode(data_b64)
                mime_type = item.get("mimeType", "image/png")

                ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
                filename = f"screenshot_{idx}.{ext}"

                images.append(
                    ImageData(
                        data=image_bytes,
                        mime_type=mime_type,
                        filename=filename,
                    )
                )
            except Exception as e:
                logger.warning("Failed to decode image at index %d: %s", idx, e)
                continue

        # Handle Playwright MCP format (type="binary" with media_type="image/...")
        elif item_type == "binary":
            media_type = item.get("media_type", "")
            if not media_type.startswith("image/"):
                continue

            data_b64 = item.get("content")
            if not data_b64 or not isinstance(data_b64, str):
                logger.warning(
                    "Binary image item missing 'content' field at index %d", idx
                )
                continue

            try:
                image_bytes = base64.b64decode(data_b64)
                ext = media_type.split("/")[-1] if "/" in media_type else "png"
                filename = f"screenshot_{idx}.{ext}"

                images.append(
                    ImageData(
                        data=image_bytes,
                        mime_type=media_type,
                        filename=filename,
                    )
                )
                logger.info(
                    "Extracted Playwright screenshot: %s (%d bytes)",
                    filename,
                    len(image_bytes),
                )
            except Exception as e:
                logger.warning("Failed to decode binary image at index %d: %s", idx, e)
                continue

        # Handle text containing data URIs (from generate_image tool)
        elif item_type == "text":
            text = item.get("text", "")
            if "data:image/" in text and ";base64," in text:
                data_uri_images = extract_data_uri_images(text)
                images.extend(data_uri_images)

    return images


def extract_text_from_result(result: Any) -> str:
    """Extract text content from MCP tool output.

    Args:
        result: Tool output containing potential text content.

    Returns:
        Concatenated text content, or str(result) if not MCP format.
    """
    if not isinstance(result, dict):
        return str(result) if result else ""

    content = result.get("content")
    if not isinstance(content, list):
        return str(result) if result else ""

    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text", "")
            if text:
                texts.append(text)

    return "\n".join(texts) if texts else str(result)
