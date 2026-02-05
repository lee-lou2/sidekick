# src/utils/slack_formatter.py
"""Convert standard Markdown to Slack mrkdwn format.

Slack uses a custom markup format called mrkdwn that differs from standard Markdown.
This module provides utilities to convert between the two formats.

Key differences:
- Bold: **text** -> *text*
- Italic: *text* or _text_ -> _text_
- Strikethrough: ~~text~~ -> ~text~
- Links: [text](url) -> <url|text>
- Headings: # Heading -> *Heading* (bold, no heading support)
- Lists: - item -> • item
- Blockquotes: > quote -> >quote (no space)
"""

import re

# Zero-width space - invisible but creates word boundary for Slack
ZWS = "\u200b"


def markdown_to_mrkdwn(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn format.

    Args:
        text: Standard Markdown text.

    Returns:
        Slack mrkdwn formatted text.
    """
    if not text:
        return text

    result = text

    # 1. Code blocks first (preserve them from other transformations)
    code_blocks: list[str] = []

    def save_code_block(match: re.Match) -> str:
        code_blocks.append(match.group(0))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    # Save fenced code blocks (```...```)
    result = re.sub(r"```[\s\S]*?```", save_code_block, result)

    # Save inline code (`...`)
    inline_codes: list[str] = []

    def save_inline_code(match: re.Match) -> str:
        inline_codes.append(match.group(0))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    result = re.sub(r"`[^`]+`", save_inline_code, result)

    # 2. Convert links: [text](url) -> <url|text>
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", result)

    # 3. Convert headings: # Heading -> *Heading*
    # Must do before bold conversion
    result = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", result, flags=re.MULTILINE)

    # 4. Convert bold: **text** -> *text*
    # Be careful not to convert already-converted headings or italic
    result = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", result)

    # 5. Convert italic with asterisks to underscores
    # Single * that's not part of ** -> _text_
    # This is tricky because Slack uses * for bold
    # We need to convert *text* (italic) to _text_ but not touch *text* (now bold)
    # After step 4, all **text** became *text*, so we skip this to avoid conflicts

    # 6. Convert strikethrough: ~~text~~ -> ~text~
    result = re.sub(r"~~([^~]+)~~", r"~\1~", result)

    # 7. Convert unordered lists: - item or * item -> • item
    result = re.sub(r"^[\-\*]\s+", "• ", result, flags=re.MULTILINE)

    # 8. Convert blockquotes: > quote -> >quote (remove space after >)
    # Slack requires no space, but we keep it readable
    # Actually Slack supports > with space, so this is optional
    # result = re.sub(r'^>\s+', '>', result, flags=re.MULTILINE)

    # 9. Convert horizontal rules: --- or *** or ___ -> ───────
    result = re.sub(r"^[-*_]{3,}$", "───────────────", result, flags=re.MULTILINE)

    # 10. Convert tables to simple format (basic support)
    # Tables aren't supported in Slack mrkdwn, convert to plain text
    def convert_table(match: re.Match) -> str:
        lines = match.group(0).strip().split("\n")
        # Remove separator line (|---|---|)
        lines = [line for line in lines if not re.match(r"^\|[\s\-:|]+\|$", line)]
        # Convert | col1 | col2 | to col1    col2
        converted = []
        for line in lines:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            converted.append("    ".join(cells))
        return "\n".join(converted)

    # Match tables (lines starting with |)
    result = re.sub(r"(?:^\|.+\|\n?)+", convert_table, result, flags=re.MULTILINE)

    # 11. Restore code blocks
    for i, code in enumerate(code_blocks):
        # Remove language identifier from code blocks for Slack
        cleaned_code = re.sub(r"```\w*\n", "```\n", code)
        result = result.replace(f"\x00CODEBLOCK{i}\x00", cleaned_code)

    # 12. Restore inline code
    for i, code in enumerate(inline_codes):
        result = result.replace(f"\x00INLINECODE{i}\x00", code)

    # 13. Add zero-width spaces around formatting markers for Slack compatibility
    # This ensures *bold*, _italic_, ~strike~ work even when adjacent to other chars
    result = _add_word_boundaries(result)

    return result


def _add_word_boundaries(text: str) -> str:
    """Add zero-width spaces around Slack formatting markers.

    Slack mrkdwn only applies formatting when markers are at word boundaries.
    This function adds invisible ZWS characters to ensure formatting works
    even when adjacent to punctuation or non-ASCII characters.

    Examples:
        '*bold*이라는' -> '*bold*\u200b이라는' (now renders as bold)
        "'*text*'" -> "'\u200b*text*\u200b'" (now renders as bold)
    """
    # Only add ZWS when formatting markers are adjacent to:
    # - Non-ASCII characters (Korean, Japanese, etc.)
    # - Punctuation that breaks Slack formatting (quotes, brackets, etc.)
    #
    # Don't add ZWS when adjacent to:
    # - Whitespace (already a word boundary)
    # - ASCII alphanumeric (Slack handles these)

    # Characters that need ZWS insertion (non-ASCII or problematic punctuation)
    needs_boundary = r"[^\s\w]|[^\x00-\x7F]"

    # Bold: *text*
    # Add ZWS after closing * if followed by non-ASCII or certain punctuation
    text = re.sub(
        rf"(\*[^*\n]+\*)({needs_boundary})",
        rf"\1{ZWS}\2",
        text,
    )
    # Add ZWS before opening * if preceded by non-ASCII or certain punctuation
    text = re.sub(
        rf"({needs_boundary})(\*[^*\n]+\*)",
        rf"\1{ZWS}\2",
        text,
    )

    # Italic: _text_
    text = re.sub(
        rf"(_[^_\n]+_)({needs_boundary})",
        rf"\1{ZWS}\2",
        text,
    )
    text = re.sub(
        rf"({needs_boundary})(_[^_\n]+_)",
        rf"\1{ZWS}\2",
        text,
    )

    # Strikethrough: ~text~
    text = re.sub(
        rf"(~[^~\n]+~)({needs_boundary})",
        rf"\1{ZWS}\2",
        text,
    )
    text = re.sub(
        rf"({needs_boundary})(~[^~\n]+~)",
        rf"\1{ZWS}\2",
        text,
    )

    return text


def escape_mrkdwn(text: str) -> str:
    """Escape special mrkdwn characters.

    Args:
        text: Text that may contain special characters.

    Returns:
        Text with special characters escaped.
    """
    # Escape &, <, > for Slack
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text
