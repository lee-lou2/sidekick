# tests/test_image_handler.py
"""Tests for image extraction utilities."""

import base64

from src.utils.image_handler import (
    ImageData,
    extract_data_uri_images,
    extract_images_from_result,
    extract_text_from_result,
    has_images,
)


class TestHasImages:
    def test_returns_true_for_mcp_image_content(self):
        result = {
            "content": [
                {"type": "text", "text": "Screenshot taken"},
                {"type": "image", "data": "base64data", "mimeType": "image/png"},
            ]
        }
        assert has_images(result) is True

    def test_returns_false_for_text_only_content(self):
        result = {"content": [{"type": "text", "text": "No images here"}]}
        assert has_images(result) is False

    def test_returns_false_for_non_dict_input(self):
        assert has_images("string") is False
        assert has_images(123) is False
        assert has_images(None) is False
        assert has_images([]) is False

    def test_returns_false_for_empty_content(self):
        assert has_images({}) is False
        assert has_images({"content": []}) is False

    def test_returns_false_for_non_list_content(self):
        assert has_images({"content": "not a list"}) is False


class TestExtractImagesFromResult:
    def test_extracts_single_image(self):
        png_data = b"\x89PNG\r\n\x1a\n"
        b64_data = base64.b64encode(png_data).decode("utf-8")

        result = {
            "content": [
                {"type": "image", "data": b64_data, "mimeType": "image/png"},
            ]
        }

        images = extract_images_from_result(result)

        assert len(images) == 1
        assert images[0].data == png_data
        assert images[0].mime_type == "image/png"
        assert images[0].filename == "screenshot_0.png"

    def test_extracts_multiple_images(self):
        png_data = b"\x89PNG\r\n\x1a\n"
        jpeg_data = b"\xff\xd8\xff\xe0"
        b64_png = base64.b64encode(png_data).decode("utf-8")
        b64_jpeg = base64.b64encode(jpeg_data).decode("utf-8")

        result = {
            "content": [
                {"type": "image", "data": b64_png, "mimeType": "image/png"},
                {"type": "text", "text": "Between images"},
                {"type": "image", "data": b64_jpeg, "mimeType": "image/jpeg"},
            ]
        }

        images = extract_images_from_result(result)

        assert len(images) == 2
        assert images[0].data == png_data
        assert images[0].mime_type == "image/png"
        assert images[1].data == jpeg_data
        assert images[1].mime_type == "image/jpeg"

    def test_returns_empty_for_non_dict_input(self):
        assert extract_images_from_result("string") == []
        assert extract_images_from_result(None) == []
        assert extract_images_from_result(123) == []

    def test_returns_empty_for_no_images(self):
        result = {"content": [{"type": "text", "text": "No images"}]}
        assert extract_images_from_result(result) == []

    def test_skips_invalid_image_items(self):
        valid_data = base64.b64encode(b"valid").decode("utf-8")

        result = {
            "content": [
                {"type": "image"},  # Missing data
                {"type": "image", "data": None},  # None data
                {"type": "image", "data": valid_data, "mimeType": "image/png"},
            ]
        }

        images = extract_images_from_result(result)
        assert len(images) == 1

    def test_defaults_mime_type_to_png(self):
        data = base64.b64encode(b"test").decode("utf-8")
        result = {"content": [{"type": "image", "data": data}]}

        images = extract_images_from_result(result)

        assert len(images) == 1
        assert images[0].mime_type == "image/png"


class TestExtractTextFromResult:
    def test_extracts_text_from_mcp_content(self):
        result = {
            "content": [
                {"type": "text", "text": "First line"},
                {"type": "image", "data": "ignored"},
                {"type": "text", "text": "Second line"},
            ]
        }

        text = extract_text_from_result(result)
        assert text == "First line\nSecond line"

    def test_returns_str_for_non_mcp_format(self):
        assert extract_text_from_result("simple string") == "simple string"
        assert extract_text_from_result(123) == "123"
        assert extract_text_from_result({"key": "value"}) == "{'key': 'value'}"

    def test_returns_empty_for_none(self):
        assert extract_text_from_result(None) == ""

    def test_handles_empty_content(self):
        result = {"content": []}
        assert extract_text_from_result(result) == "{'content': []}"


class TestExtractDataUriImages:
    """Tests for extract_data_uri_images function."""

    def test_extract_single_png(self):
        """Should extract a single PNG data URI."""
        image_bytes = b"\x89PNG\r\n\x1a\n"
        b64 = base64.b64encode(image_bytes).decode()
        text = f"Here is an image: data:image/png;base64,{b64}"

        images = extract_data_uri_images(text)

        assert len(images) == 1
        assert images[0].mime_type == "image/png"
        assert images[0].data == image_bytes

    def test_extract_multiple_images(self):
        """Should extract multiple data URIs."""
        img1 = base64.b64encode(b"image1").decode()
        img2 = base64.b64encode(b"image2").decode()
        text = (
            f"First: data:image/png;base64,{img1} Second: data:image/jpeg;base64,{img2}"
        )

        images = extract_data_uri_images(text)

        assert len(images) == 2
        assert images[0].mime_type == "image/png"
        assert images[1].mime_type == "image/jpeg"

    def test_no_images_in_text(self):
        """Should return empty list when no data URIs present."""
        text = "Just some regular text without images"

        images = extract_data_uri_images(text)

        assert len(images) == 0


class TestExtractImagesFromResultWithDataUri:
    """Tests for extract_images_from_result with data URI support."""

    def test_extract_data_uri_from_text_content(self):
        """Should extract data URI from text content type."""
        image_bytes = b"\x89PNG"
        b64 = base64.b64encode(image_bytes).decode()
        result = {
            "content": [
                {"type": "text", "text": f"Generated: data:image/png;base64,{b64}"},
            ]
        }

        images = extract_images_from_result(result)

        assert len(images) == 1
        assert images[0].data == image_bytes
        assert images[0].mime_type == "image/png"

    def test_extract_both_mcp_and_data_uri(self):
        """Should extract both MCP format and data URI images."""
        img1 = b"mcp_image"
        img2 = b"data_uri_image"
        b64_mcp = base64.b64encode(img1).decode()
        b64_uri = base64.b64encode(img2).decode()

        result = {
            "content": [
                {"type": "image", "data": b64_mcp, "mimeType": "image/png"},
                {"type": "text", "text": f"data:image/jpeg;base64,{b64_uri}"},
            ]
        }

        images = extract_images_from_result(result)

        assert len(images) == 2
        assert images[0].data == img1  # MCP format
        assert images[1].data == img2  # Data URI


class TestImageData:
    def test_extension_from_mime_type(self):
        img = ImageData(data=b"test", mime_type="image/png")
        assert img.extension == "png"

        img = ImageData(data=b"test", mime_type="image/jpeg")
        assert img.extension == "jpeg"

    def test_extension_from_invalid_mime_type(self):
        img = ImageData(data=b"test", mime_type="invalid")
        assert img.extension == "png"

    def test_to_data_uri(self):
        data = b"test data"
        img = ImageData(data=data, mime_type="image/png")

        uri = img.to_data_uri()

        expected_b64 = base64.b64encode(data).decode("utf-8")
        assert uri == f"data:image/png;base64,{expected_b64}"
