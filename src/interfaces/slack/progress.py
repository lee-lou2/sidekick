# src/interfaces/slack/progress.py
"""Progress formatting utilities for Slack messages.

Provides emoji mappings and formatting functions for displaying tool progress
and status updates in Slack messages.
"""

TOOL_EMOJI = {
    "fetch": ":globe_with_meridians:",
    "search": ":mag:",
    "git": ":git:",
    "read": ":page_facing_up:",
    "write": ":pencil2:",
    "create": ":sparkles:",
    "delete": ":wastebasket:",
    "list": ":clipboard:",
    "memory": ":brain:",
}


def _get_tool_emoji(tool_name: str) -> str:
    """Get emoji for a tool name.

    Args:
        tool_name: Name of the tool.

    Returns:
        Slack emoji code for the tool, or :gear: as default.
    """
    tool_lower = tool_name.lower()
    for key, emoji in TOOL_EMOJI.items():
        if key in tool_lower:
            return emoji
    return ":gear:"


def _muted_block(text: str) -> list[dict]:
    """Create a context block for muted (small gray) text in Slack.

    Args:
        text: Text to display in muted style.

    Returns:
        List containing a single context block with muted text.
    """
    return [{"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}]


def _format_progress(tool_name: str) -> tuple[str, list[dict]]:
    """Return (fallback_text, blocks) for tool progress.

    Args:
        tool_name: Name of the tool being executed.

    Returns:
        Tuple of (fallback_text, blocks) for Slack message update.
    """
    emoji = _get_tool_emoji(tool_name)
    text = f"{emoji} {tool_name}"
    return text, _muted_block(text)
