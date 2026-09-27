"""Context builder — thin wrapper used by report_generator.

The main context building logic lives inside report_generator.build_context_string().
This module re-exports it for any external consumers and adds a small helper
for summarising context size.
"""

from report_generator import build_context_string  # noqa: F401


def context_char_count(ctx: dict) -> int:
    """Return the approximate character length of the serialised context."""
    return len(build_context_string(ctx))
