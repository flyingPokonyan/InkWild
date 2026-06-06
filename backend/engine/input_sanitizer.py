import html
import re


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F-\x9F]")


def strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text)


def xml_escape_user_input(text: str) -> str:
    return html.escape(text, quote=True)


def wrap_player_input(text: str) -> str:
    sanitized = strip_control_chars(text)
    escaped = xml_escape_user_input(sanitized)
    return f"<player_input>{escaped}</player_input>"
