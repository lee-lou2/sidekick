# tests/test_slack_formatter.py
"""Tests for Slack mrkdwn formatter."""

from src.utils.slack_formatter import escape_mrkdwn, markdown_to_mrkdwn


class TestMarkdownToMrkdwn:
    """Tests for markdown_to_mrkdwn function."""

    def test_empty_string(self):
        assert markdown_to_mrkdwn("") == ""
        assert markdown_to_mrkdwn(None) is None

    def test_plain_text(self):
        text = "Hello, world!"
        assert markdown_to_mrkdwn(text) == text

    def test_bold_conversion(self):
        """**text** -> *text*"""
        assert markdown_to_mrkdwn("This is **bold** text") == "This is *bold* text"
        assert markdown_to_mrkdwn("**start** and **end**") == "*start* and *end*"

    def test_strikethrough_conversion(self):
        """~~text~~ -> ~text~"""
        assert (
            markdown_to_mrkdwn("This is ~~deleted~~ text") == "This is ~deleted~ text"
        )

    def test_link_conversion(self):
        """[text](url) -> <url|text>"""
        assert (
            markdown_to_mrkdwn("Click [here](https://example.com)")
            == "Click <https://example.com|here>"
        )
        assert (
            markdown_to_mrkdwn("[Link 1](url1) and [Link 2](url2)")
            == "<url1|Link 1> and <url2|Link 2>"
        )

    def test_heading_conversion(self):
        """# Heading -> *Heading*"""
        assert markdown_to_mrkdwn("# Title") == "*Title*"
        assert markdown_to_mrkdwn("## Subtitle") == "*Subtitle*"
        assert markdown_to_mrkdwn("### Section") == "*Section*"

    def test_unordered_list_conversion(self):
        """- item -> • item"""
        text = "- Item 1\n- Item 2\n- Item 3"
        expected = "• Item 1\n• Item 2\n• Item 3"
        assert markdown_to_mrkdwn(text) == expected

        # Also test * lists
        text2 = "* Item A\n* Item B"
        expected2 = "• Item A\n• Item B"
        assert markdown_to_mrkdwn(text2) == expected2

    def test_horizontal_rule_conversion(self):
        """--- -> ───────"""
        assert "─" in markdown_to_mrkdwn("---")
        assert "─" in markdown_to_mrkdwn("***")
        assert "─" in markdown_to_mrkdwn("___")

    def test_code_block_preserved(self):
        """Code blocks should be preserved."""
        text = "```python\nprint('hello')\n```"
        result = markdown_to_mrkdwn(text)
        assert "```" in result
        assert "print('hello')" in result

    def test_inline_code_preserved(self):
        """Inline code should be preserved."""
        text = "Use `code` here"
        assert markdown_to_mrkdwn(text) == "Use `code` here"

    def test_code_block_language_removed(self):
        """Language identifier after ``` should be removed for Slack."""
        text = "```python\ncode\n```"
        result = markdown_to_mrkdwn(text)
        # Should not have ```python, just ```
        assert "```python" not in result
        assert "```\ncode\n```" in result

    def test_mixed_formatting(self):
        """Test multiple formatting in one text."""
        text = """# Title

This is **bold** and ~~deleted~~.

- Item 1
- Item 2

Click [here](https://example.com).
"""
        result = markdown_to_mrkdwn(text)
        assert "*Title*" in result
        assert "*bold*" in result
        assert "~deleted~" in result
        assert "• Item 1" in result
        assert "<https://example.com|here>" in result

    def test_table_conversion(self):
        """Tables should be converted to plain text."""
        text = """| Col1 | Col2 |
|------|------|
| A    | B    |
| C    | D    |"""
        result = markdown_to_mrkdwn(text)
        # Should not contain | characters (except maybe in content)
        assert "Col1" in result
        assert "Col2" in result


class TestWordBoundaries:
    """Tests for zero-width space insertion at word boundaries."""

    def test_bold_followed_by_text(self):
        """*bold*이라는 should have ZWS after closing *"""
        result = markdown_to_mrkdwn("**bold**이라는")
        assert "*bold*" in result
        assert "\u200b이라는" in result

    def test_bold_preceded_by_punctuation(self):
        """'*text*' should have ZWS around formatting"""
        result = markdown_to_mrkdwn("'**text**'")
        # Should have ZWS before * and after *
        assert "\u200b*text*\u200b" in result or "'\u200b*text*\u200b'" in result

    def test_real_world_example(self):
        """Test the actual problematic case from user."""
        text = "*'클래식과 트렌드의 공존'*이라는"
        result = markdown_to_mrkdwn(text)
        # Should have ZWS after the closing *
        assert "\u200b이라는" in result

    def test_multiple_formatted_words(self):
        """Multiple formatted words in sequence."""
        result = markdown_to_mrkdwn("이것은 **중요한**내용이고 **핵심**입니다")
        assert "\u200b내용" in result
        assert "\u200b입니다" in result


class TestEscapeMrkdwn:
    """Tests for escape_mrkdwn function."""

    def test_escape_ampersand(self):
        assert escape_mrkdwn("A & B") == "A &amp; B"

    def test_escape_angle_brackets(self):
        assert escape_mrkdwn("<script>") == "&lt;script&gt;"

    def test_no_escape_needed(self):
        assert escape_mrkdwn("Hello World") == "Hello World"
