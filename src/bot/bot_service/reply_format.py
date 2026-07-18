from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ReplyFormat:
    """Describes how an action reply should be rendered and sent to Telegram."""

    name: str
    parse_mode: str | None
    fenced: bool
    fence_lang: str = ""


# Registry of built-in reply formats and their default rendering behavior.
_FORMAT_REGISTRY: dict[str, ReplyFormat] = {
    "markdown": ReplyFormat(name="markdown", parse_mode="Markdown", fenced=False),
    "text": ReplyFormat(name="text", parse_mode=None, fenced=False),
    "json": ReplyFormat(name="json", parse_mode="Markdown", fenced=True, fence_lang="json"),
    "yaml": ReplyFormat(name="yaml", parse_mode="Markdown", fenced=True, fence_lang="yaml"),
    "html": ReplyFormat(name="html", parse_mode="HTML", fenced=False),
}

DEFAULT_REPLY_FORMAT = _FORMAT_REGISTRY["markdown"]


def get_reply_format(name: str) -> ReplyFormat:
    """Return the registry entry for ``name`` (case-insensitive)."""
    key = name.strip().lower()
    fmt = _FORMAT_REGISTRY.get(key)
    if fmt is None:
        raise ValueError(
            f"Unknown reply_format '{name}'. "
            f"Supported formats: {', '.join(sorted(_FORMAT_REGISTRY))}"
        )
    return fmt


def resolve_reply_format(spec: Any) -> ReplyFormat | None:
    """Normalize a config ``reply_format`` value into a :class:`ReplyFormat`.

    Accepts either a shorthand string (``reply_format: json``) or a mapping
    (``reply_format: {format: json, fenced: false}``). Returns ``None`` when the
    value is absent so callers can fall back to their own default.
    """
    if spec is None:
        return None

    if isinstance(spec, str):
        name = spec.strip()
        if not name:
            raise ValueError("reply_format string cannot be empty")
        return get_reply_format(name)

    if isinstance(spec, dict):
        raw_name = spec.get("format")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("reply_format mapping must include a non-empty 'format' string")

        base = get_reply_format(raw_name)

        fenced = base.fenced
        if "fenced" in spec:
            raw_fenced = spec.get("fenced")
            if not isinstance(raw_fenced, bool):
                raise ValueError("reply_format 'fenced' must be a boolean")
            fenced = raw_fenced

        fence_lang = base.fence_lang
        if "fence_lang" in spec:
            raw_lang = spec.get("fence_lang")
            if not isinstance(raw_lang, str):
                raise ValueError("reply_format 'fence_lang' must be a string")
            fence_lang = raw_lang.strip()

        return ReplyFormat(
            name=base.name,
            parse_mode=base.parse_mode,
            fenced=fenced,
            fence_lang=fence_lang,
        )

    raise ValueError("reply_format must be a string or a mapping")


def apply_reply_format(text: str, fmt: ReplyFormat | None) -> tuple[str, str | None]:
    """Render ``text`` for the given format.

    Returns a tuple of ``(rendered_text, parse_mode)`` ready to hand to
    Telegram's ``reply_text``.
    """
    if fmt is None:
        fmt = DEFAULT_REPLY_FORMAT

    if fmt.fenced:
        lang = fmt.fence_lang or ""
        rendered = f"```{lang}\n{text}\n```"
    else:
        rendered = text

    return rendered, fmt.parse_mode
