"""LLM-based resume structured extraction."""
from pathlib import Path

from .llm import chat_json

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract.md"
_SYSTEM = _PROMPT_PATH.read_text(encoding="utf-8")


def extract_resume(raw_text: str) -> dict:
    """Extract structured resume JSON from raw text."""
    return chat_json(
        system=_SYSTEM,
        user=f"简历原始文本如下:\n\n{raw_text[:15000]}",
        temperature=0.1,
    )
