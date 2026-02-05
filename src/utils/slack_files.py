# src/utils/slack_files.py
"""Slack file handling utilities.

Provides functions for downloading files from Slack and uploading images.
"""

import asyncio
import base64
import io
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Timeout settings
AIOHTTP_TOTAL_TIMEOUT = 120
AIOHTTP_CONNECT_TIMEOUT = 30
MAX_RETRIES = 3

# Global aiohttp session
_session: aiohttp.ClientSession | None = None
_session_loop: asyncio.AbstractEventLoop | None = None


async def get_aiohttp_session() -> aiohttp.ClientSession:
    """Get or create a shared aiohttp session.

    Returns:
        Shared aiohttp.ClientSession instance.
    """
    global _session, _session_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    needs_recreate = (
        _session is None or _session.closed or _session_loop is not current_loop
    )

    if needs_recreate:
        # Close old session if it exists and belongs to a different event loop
        if (
            _session is not None
            and not _session.closed
            and _session_loop is not current_loop
        ):
            try:
                await _session.close()
            except Exception as e:
                logger.debug(f"Error closing old session: {e}")

        timeout = aiohttp.ClientTimeout(
            total=AIOHTTP_TOTAL_TIMEOUT,
            connect=AIOHTTP_CONNECT_TIMEOUT,
        )
        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=20,
            ttl_dns_cache=300,
        )
        _session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        _session_loop = current_loop
        logger.debug("Created new aiohttp session")

    assert _session is not None
    return _session


async def close_aiohttp_session() -> None:
    """Close the shared aiohttp session."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
        logger.debug("Closed aiohttp session")


async def download_slack_file(file_url: str, token: str) -> bytes | None:
    """Download a file from Slack.

    Args:
        file_url: Slack file URL (url_private).
        token: Slack bot token for authorization.

    Returns:
        File bytes or None on error.
    """
    headers = {"Authorization": f"Bearer {token}"}

    try:
        session = await get_aiohttp_session()
        async with session.get(file_url, headers=headers) as response:
            if response.status == 200:
                return await response.read()
            else:
                logger.error(f"Failed to download file: HTTP {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return None


async def upload_image_bytes(
    client: Any,
    channel_id: str,
    image_bytes: bytes,
    filename: str = "image.png",
    title: str = "Image",
    thread_ts: str | None = None,
    initial_comment: str | None = None,
) -> bool:
    """Upload image bytes to Slack.

    Args:
        client: Slack AsyncWebClient.
        channel_id: Target channel ID.
        image_bytes: Image data as bytes.
        filename: File name.
        title: File title.
        thread_ts: Thread timestamp for reply.
        initial_comment: Comment to accompany the image.

    Returns:
        True if upload successful.
    """
    try:
        file_obj = io.BytesIO(image_bytes)
        result = await client.files_upload_v2(
            channel=channel_id,
            file=file_obj,
            filename=filename,
            title=title,
            thread_ts=thread_ts,
            initial_comment=initial_comment or "",
        )

        if result.get("ok"):
            logger.info(f"Uploaded image: {filename}")
            return True
        else:
            logger.error(f"Upload failed: {result.get('error')}")
            return False
    except AttributeError:
        # Fallback to v1 API
        try:
            file_obj = io.BytesIO(image_bytes)
            await client.files_upload(
                channels=channel_id,
                file=file_obj,
                filename=filename,
                title=title,
                thread_ts=thread_ts,
                initial_comment=initial_comment or "",
            )
            logger.info(f"Uploaded image (v1): {filename}")
            return True
        except Exception as e:
            logger.error(f"Fallback upload failed: {e}")
            return False
    except Exception as e:
        logger.error(f"Failed to upload image: {e}")
        return False


async def upload_multiple_images(
    client: Any,
    channel_id: str,
    images: list[dict[str, Any]],
    thread_ts: str | None = None,
    initial_comment: str | None = None,
) -> bool:
    """Upload multiple images to Slack in batches.

    Args:
        client: Slack AsyncWebClient.
        channel_id: Target channel ID.
        images: List of dicts with 'bytes', 'filename', 'title' keys.
        thread_ts: Thread timestamp for reply.
        initial_comment: Comment to accompany the images.

    Returns:
        True if at least one upload successful.
    """
    if not images:
        logger.warning("No images to upload")
        return False

    MAX_BATCH_SIZE = 10

    # Split into batches for large uploads
    if len(images) > MAX_BATCH_SIZE:
        total_chunks = (len(images) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE
        logger.info(f"Splitting {len(images)} images into {total_chunks} batches")

        success = True
        for i in range(0, len(images), MAX_BATCH_SIZE):
            chunk = images[i : i + MAX_BATCH_SIZE]
            chunk_num = i // MAX_BATCH_SIZE + 1
            chunk_comment = (
                f"{initial_comment} ({chunk_num}/{total_chunks})"
                if initial_comment
                else None
            )

            if i > 0:
                await asyncio.sleep(1.0)

            chunk_success = await upload_multiple_images(
                client=client,
                channel_id=channel_id,
                images=chunk,
                thread_ts=thread_ts,
                initial_comment=chunk_comment,
            )
            if not chunk_success:
                success = False

        return success

    try:
        file_uploads = []
        for img in images:
            img_bytes = img.get("bytes")
            if img_bytes:
                file_uploads.append(
                    {
                        "file": io.BytesIO(img_bytes),
                        "filename": img.get("filename", "image.png"),
                        "title": img.get("title", "Image"),
                    }
                )

        if not file_uploads:
            logger.warning("No valid image bytes found")
            return False

        logger.info(f"Uploading {len(file_uploads)} images")

        result = await client.files_upload_v2(
            channel=channel_id,
            file_uploads=file_uploads,
            thread_ts=thread_ts,
            initial_comment=initial_comment or "",
        )

        if result is None:
            logger.warning("files_upload_v2 returned None (upload may have succeeded)")
            return True

        if not hasattr(result, "get"):
            logger.warning(f"Unexpected result type: {type(result)}")
            return True

        if result.get("ok"):
            logger.info(f"Uploaded {len(file_uploads)} images successfully")
            return True
        else:
            logger.error(f"Upload failed: {result.get('error')}")
            return False

    except AttributeError as e:
        error_msg = str(e).lower()
        if "files_upload_v2" in error_msg or "file_uploads" in error_msg:
            logger.warning("files_upload_v2 not available, uploading individually")
            success_count = 0
            for img in images:
                img_bytes = img.get("bytes")
                if img_bytes:
                    result = await upload_image_bytes(
                        client=client,
                        channel_id=channel_id,
                        image_bytes=img_bytes,
                        filename=img.get("filename", "image.png"),
                        title=img.get("title", "Image"),
                        thread_ts=thread_ts,
                    )
                    if result:
                        success_count += 1
            return success_count > 0
        else:
            logger.warning(f"AttributeError (upload may have succeeded): {e}")
            return True

    except Exception as e:
        logger.error(f"Failed to upload multiple images: {e}")
        return False


def extract_images_from_event(
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract image file information from a Slack event.

    Args:
        event: Slack event dict containing 'files' key.

    Returns:
        List of image file info dicts with 'url', 'mime_type', 'name' keys.
    """
    files = event.get("files", [])
    images = []

    for file_info in files:
        mime_type = file_info.get("mimetype", "")
        if mime_type.startswith("image/"):
            images.append(
                {
                    "url": file_info.get("url_private", ""),
                    "mime_type": mime_type,
                    "name": file_info.get("name", "image"),
                    "size": file_info.get("size", 0),
                }
            )

    return images


async def process_slack_images(
    files: list[dict[str, Any]], token: str
) -> list[dict[str, Any]]:
    """Download and process image files from Slack.

    Args:
        files: List of file info dicts from Slack event.
        token: Slack bot token.

    Returns:
        List of processed images with 'bytes', 'mime_type', 'name' keys.
    """
    MAX_SIZE = 20 * 1024 * 1024  # 20MB limit

    processed = []
    for file_info in files:
        mime_type = file_info.get("mimetype", file_info.get("mime_type", ""))
        if not mime_type.startswith("image/"):
            continue

        file_url = file_info.get("url_private", file_info.get("url", ""))
        file_name = file_info.get("name", "image")
        file_size = file_info.get("size", 0)

        if not file_url:
            continue

        if file_size > MAX_SIZE:
            logger.warning(
                f"Image too large, skipping: {file_name} ({file_size} bytes)"
            )
            continue

        image_bytes = await download_slack_file(file_url, token)
        if image_bytes:
            processed.append(
                {
                    "bytes": image_bytes,
                    "mime_type": mime_type,
                    "name": file_name,
                    "base64": base64.b64encode(image_bytes).decode("utf-8"),
                }
            )
            logger.info(f"Processed image: {file_name} ({len(image_bytes)} bytes)")

    return processed


async def process_slack_audio_files(
    files: list[dict[str, Any]], token: str
) -> list[dict[str, str]]:
    """Download and transcribe audio files from Slack using Qwen3-ASR MLX.

    Instead of passing audio binary to LLM (which causes token overflow),
    this function transcribes audio to text first using MLX-optimized model.

    Args:
        files: List of file info dicts from Slack event.
        token: Slack bot token.

    Returns:
        List of transcription results with 'name', 'text', 'language' keys.
    """
    import tempfile

    MAX_SIZE = 100 * 1024 * 1024  # 100MB limit for audio

    # Supported audio MIME types
    AUDIO_MIMES = {"audio/", "video/"}  # video/ for voice messages in some clients

    transcriptions = []
    for file_info in files:
        mime_type = file_info.get("mimetype", file_info.get("mime_type", ""))

        # Check if it's an audio file
        is_audio = any(mime_type.startswith(prefix) for prefix in AUDIO_MIMES)
        if not is_audio:
            continue

        file_url = file_info.get("url_private", file_info.get("url", ""))
        file_name = file_info.get("name", "audio")
        file_size = file_info.get("size", 0)

        if not file_url:
            continue

        if file_size > MAX_SIZE:
            logger.warning(
                f"Audio file too large, skipping: {file_name} ({file_size} bytes)"
            )
            transcriptions.append(
                {
                    "name": file_name,
                    "text": f"[오류: 파일이 너무 큽니다 ({file_size / 1024 / 1024:.1f}MB > 100MB)]",
                    "language": "unknown",
                }
            )
            continue

        logger.info(f"Downloading audio file: {file_name} ({file_size} bytes)")
        audio_bytes = await download_slack_file(file_url, token)

        if not audio_bytes:
            logger.error(f"Failed to download audio file: {file_name}")
            transcriptions.append(
                {
                    "name": file_name,
                    "text": "[오류: 파일 다운로드 실패]",
                    "language": "unknown",
                }
            )
            continue

        # Log file info for debugging
        logger.info(
            f"Downloaded {file_name}: {len(audio_bytes)} bytes, "
            f"magic bytes: {audio_bytes[:16].hex()}"
        )

        # Save to temp file for transcription
        suffix = "." + file_name.split(".")[-1] if "." in file_name else ".wav"
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(audio_bytes)
                temp_path = f.name

            # Verify file was written correctly
            import os as os_module

            actual_size = os_module.path.getsize(temp_path)
            logger.info(f"Saved temp file: {temp_path}, size: {actual_size}")

            # Import and run transcription (optional - custom tool may not exist)
            logger.info(f"Transcribing audio: {file_name}")
            try:
                from src.tools.custom.audio_transcriber import transcribe_audio
            except ImportError:
                logger.warning(
                    "audio_transcriber tool not installed. "
                    "Install it in src/tools/custom/ to enable audio transcription."
                )
                transcriptions.append(
                    {
                        "name": file_name,
                        "text": "[오류: audio_transcriber 도구가 설치되지 않았습니다]",
                        "language": "unknown",
                    }
                )
                continue

            result = transcribe_audio(audio_source=temp_path, language="")

            # If transcription fails with decode error, try converting with ffmpeg
            if "DecodeError" in result or "could not open/decode" in result:
                logger.warning("Direct decode failed, trying ffmpeg conversion...")
                import subprocess

                wav_path = temp_path.rsplit(".", 1)[0] + "_converted.wav"
                try:
                    # Convert to WAV using ffmpeg
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            temp_path,
                            "-ar",
                            "16000",
                            "-ac",
                            "1",
                            "-f",
                            "wav",
                            wav_path,
                        ],
                        capture_output=True,
                        check=True,
                        timeout=60,
                    )
                    logger.info(f"Converted to WAV: {wav_path}")

                    # Retry transcription with converted file
                    result = transcribe_audio(audio_source=wav_path, language="")

                    # Clean up converted file
                    try:
                        os_module.unlink(wav_path)
                    except Exception:
                        pass
                except subprocess.CalledProcessError as e:
                    logger.error(f"ffmpeg conversion failed: {e.stderr.decode()}")
                except Exception as e:
                    logger.error(f"Conversion error: {e}")

            if result.startswith("Error:"):
                logger.error(f"Transcription failed for {file_name}: {result}")
                transcriptions.append(
                    {
                        "name": file_name,
                        "text": f"[전사 오류: {result}]",
                        "language": "unknown",
                    }
                )
            else:
                # Parse language from result (format: "[언어: English]\ntext")
                language = "unknown"
                text = result
                if result.startswith("[언어:"):
                    try:
                        lang_end = result.index("]")
                        language = result[5:lang_end].strip()
                        text = result[lang_end + 1 :].strip()
                    except ValueError:
                        pass

                transcriptions.append(
                    {
                        "name": file_name,
                        "text": text,
                        "language": language,
                    }
                )
                logger.info(f"Transcribed {file_name}: {language}, {len(text)} chars")

        except Exception as e:
            logger.error(f"Error transcribing {file_name}: {e}")
            transcriptions.append(
                {
                    "name": file_name,
                    "text": f"[전사 오류: {type(e).__name__}: {str(e)}]",
                    "language": "unknown",
                }
            )
        finally:
            # Clean up temp file
            if temp_path:
                import os

                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    return transcriptions
