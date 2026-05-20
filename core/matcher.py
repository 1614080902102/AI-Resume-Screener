"""LLM-based JD vs resume semantic matcher with custom rules."""
import json
from pathlib import Path

from .llm import chat_json

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "match.md"
_SYSTEM = _PROMPT_PATH.read_text(encoding="utf-8")


def match_resume(
    jd_text: str,
    resume_struct: dict,
    custom_rules: str = "",
) -> dict:
    """Score a structured resume against a JD + custom HR rules."""
    rules_block = (
        custom_rules.strip() if custom_rules.strip() else "(HR 未提供自定义规则)"
    )
    user = (
        f"【岗位 JD】\n{jd_text[:5000]}\n\n"
        f"【HR 自定义规则与偏好】\n{rules_block}\n\n"
        f"【候选人结构化简历】\n"
        f"{json.dumps(resume_struct, ensure_ascii=False, indent=2)}"
    )
    return chat_json(system=_SYSTEM, user=user, temperature=0.2)
