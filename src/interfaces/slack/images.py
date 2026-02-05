# src/interfaces/slack/images.py
"""Image handling utilities for Slack bot.

Provides functions for:
- Extracting images from thread history
- Formatting images for agent context
- Uploading images to Slack
"""

import logging
from typing import Any

from src.interfaces.slack.slack_api import _slack_api_with_retry
from src.utils.image_handler import ImageData, extract_data_uri_images

logger = logging.getLogger(__name__)


def _extract_images_from_thread_history(
    context_messages: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Extract data URI images from bot responses in thread history.

    This allows editing of previously generated images across conversation turns.

    Args:
        context_messages: List of messages with 'user' and 'text' keys.

    Returns:
        List of image dicts with 'bytes', 'base64', 'mime_type', 'name' keys.
    """
    images: list[dict[str, Any]] = []

    for msg in reversed(context_messages):  # Start from most recent
        if msg.get("user") != "assistant":
            continue

        text = msg.get("text", "")
        if "data:image/" not in text or ";base64," not in text:
            continue

        # Extract data URI images from the bot's message
        extracted = extract_data_uri_images(text)
        for idx, img_data in enumerate(extracted):
            images.append(
                {
                    "bytes": img_data.data,
                    "base64": img_data.to_data_uri().split(",", 1)[1]
                    if "," in img_data.to_data_uri()
                    else "",
                    "mime_type": img_data.mime_type,
                    "name": f"previous_generated_{len(images)}.{img_data.extension}",
                }
            )

        # Only get images from the most recent bot message with images
        if images:
            break

    return images


def _format_images_for_agent(images: list[dict[str, Any]]) -> str:
    """Format image data description for the agent.

    The actual image data is stored in context variables (set_attached_images),
    so we only need to inform the agent about what images are available.

    Args:
        images: List of processed images with 'base64', 'mime_type', 'name' keys.

    Returns:
        Formatted string describing the attached images.
    """
    if not images:
        return ""

    lines = ["\n[첨부된 이미지]"]
    for i, img in enumerate(images):
        name = img.get("name", f"image_{i}")
        mime_type = img.get("mime_type", "image/png")
        byte_size = len(img.get("bytes", b"")) if img.get("bytes") else 0

        size_str = (
            f"{byte_size / 1024:.1f}KB"
            if byte_size < 1024 * 1024
            else f"{byte_size / (1024 * 1024):.1f}MB"
        )
        lines.append(f"- 이미지 {i} ({name}, {mime_type}, {size_str})")

    lines.append(
        "참고: edit_image 도구 호출 시 image_data 파라미터를 비워두면 "
        "첨부된 이미지가 자동으로 사용됩니다. image_index로 특정 이미지를 선택할 수 있습니다."
    )
    lines.append("")
    return "\n".join(lines)


async def _upload_images_to_slack(
    images: list[ImageData],
    client: Any,
    channel: str,
    thread_ts: str,
) -> None:
    """Upload images to Slack thread using files_upload_v2."""
    for idx, image in enumerate(images):
        try:
            filename = image.filename or f"screenshot_{idx}.{image.extension}"
            await _slack_api_with_retry(
                client.files_upload_v2,
                channel=channel,
                thread_ts=thread_ts,
                file=image.data,
                filename=filename,
                title=f"Screenshot {idx + 1}" if len(images) > 1 else "Screenshot",
            )
            logger.info("Uploaded image %s to channel %s", filename, channel)
        except Exception as e:
            logger.warning("Failed to upload image %d: %s", idx, e)
