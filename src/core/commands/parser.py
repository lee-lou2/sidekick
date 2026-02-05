"""Pure function-based command parser for extracting commands from text."""

from dataclasses import dataclass


@dataclass
class ParsedCommand:
    """Represents a parsed command with name, input, and additional instructions.

    Attributes:
        name: The command name (lowercase normalized).
        input: The primary input/argument for the command (whitespace normalized).
        additional_instructions: Optional additional instructions after comma separator.
    """

    name: str
    input: str
    additional_instructions: str = ""


def parse_command(text: str) -> ParsedCommand | None:
    """Parse a command from text.

    Detects commands in the format `!command_name input_text, additional instructions`
    and extracts the command name, input, and optional additional instructions.
    Command names are normalized to lowercase, and whitespace is normalized
    (leading/trailing stripped, multiple spaces collapsed to single space).

    The comma (,) acts as a separator between the primary input and additional
    instructions that modify how the command should be executed.

    Args:
        text: The text to parse for a command.

    Returns:
        ParsedCommand with name, input, and additional_instructions if text
        starts with `!` and has a command name, otherwise None.

    Examples:
        >>> parse_command("!날씨 서울")
        ParsedCommand(name='날씨', input='서울', additional_instructions='')

        >>> parse_command("!브소개 아디다스, 영어로 답변줘")
        ParsedCommand(name='브소개', input='아디다스', additional_instructions='영어로 답변줘')

        >>> parse_command("!help")
        ParsedCommand(name='help', input='', additional_instructions='')

        >>> parse_command("!HELLO world")
        ParsedCommand(name='hello', input='world', additional_instructions='')

        >>> parse_command("일반 메시지")
        None

        >>> parse_command("!")
        None
    """
    text = text.strip()

    if not text.startswith("!"):
        return None

    text = text[1:]

    if not text:
        return None

    parts = text.split(None, 1)
    command_name = parts[0].lower()

    if len(parts) > 1:
        raw_input = parts[1]

        comma_pos = raw_input.find(",")
        if comma_pos != -1:
            command_input = " ".join(raw_input[:comma_pos].split())
            additional = " ".join(raw_input[comma_pos + 1 :].split())
        else:
            command_input = " ".join(raw_input.split())
            additional = ""
    else:
        command_input = ""
        additional = ""

    return ParsedCommand(
        name=command_name, input=command_input, additional_instructions=additional
    )
