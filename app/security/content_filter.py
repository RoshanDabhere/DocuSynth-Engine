"""Defense-in-depth content filter for user-submitted questions.

Scans for common prompt injection patterns before the question
reaches the LLM. This is a supplementary defense — the system prompt
already instructs the model to ignore injected instructions.
"""

import logging
import re

logger = logging.getLogger("app.security.content_filter")

# Patterns that indicate prompt injection attempts.
# Each tuple: (compiled regex, human-readable label)
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(ignore|disregard|forget|override)\s+"
            r"(all\s+)?(previous|above|prior|earlier|system)\s+"
            r"(instructions?|prompts?|rules?|context)",
            re.IGNORECASE,
        ),
        "instruction_override",
    ),
    (
        re.compile(
            r"you\s+are\s+now\s+",
            re.IGNORECASE,
        ),
        "role_hijack",
    ),
    (
        re.compile(
            r"(system\s*prompt|<\s*/?\s*system\s*>|<<\s*SYS\s*>>)",
            re.IGNORECASE,
        ),
        "system_prompt_reference",
    ),
    (
        re.compile(
            r"\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>",
            re.IGNORECASE,
        ),
        "chat_template_injection",
    ),
]


def scan_question(question: str) -> str | None:
    """Return the injection label if a pattern matches, else None.

    This does NOT block the request — it returns a label that the
    caller can use for logging, flagging, or rejection.
    """
    for pattern, label in _INJECTION_PATTERNS:
        if pattern.search(question):
            logger.warning(
                "Prompt injection detected: pattern=%s, preview=%.80s",
                label,
                question,
            )
            return label
    return None
