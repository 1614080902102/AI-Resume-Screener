"""OpenAI-compatible LLM client with file logging."""
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------- Logging ----------
_LOG_PATH = Path(__file__).parent.parent / "llm.log"
logger = logging.getLogger("ai_resume_screener.llm")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(_LOG_PATH, mode="a", encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter("[LLM] %(message)s"))
    logger.addHandler(sh)

# ---------- Client ----------
_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
_model = os.getenv("OPENAI_MODEL", "gpt-5.4")
logger.info(f"LLM client init: model={_model} base_url={os.getenv('OPENAI_BASE_URL')}")


def _stream_chat(messages: list[dict], max_retries: int = 3, **kwargs) -> str:
    """Stream chat and accumulate full text. Retries with exponential backoff on transient errors."""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            stream = _client.chat.completions.create(
                model=_model,
                stream=True,
                messages=messages,
                **kwargs,
            )
            out = []
            chunks_seen = 0
            for chunk in stream:
                chunks_seen += 1
                try:
                    delta = chunk.choices[0].delta.content
                except (AttributeError, IndexError):
                    continue
                if delta:
                    out.append(delta)
            text = "".join(out)
            if not text.strip() and attempt < max_retries - 1:
                # 空回复也重试一次
                logger.warning(f"empty response, retry {attempt + 1}")
                import time as _t
                _t.sleep(2 ** attempt)
                continue
            logger.info(
                f"recv: attempt={attempt + 1} chunks={chunks_seen} text_len={len(text)}"
            )
            return text
        except Exception as e:
            last_err = e
            msg = str(e)
            # 限流 / 5xx / upstream → 重试
            retryable = any(
                k in msg for k in ("429", "502", "503", "504", "Upstream", "timeout")
            )
            if attempt < max_retries - 1 and retryable:
                wait = 2 ** attempt + 1
                logger.warning(
                    f"call failed (attempt {attempt + 1}/{max_retries}), retry in {wait}s: {msg[:120]}"
                )
                import time as _t
                _t.sleep(wait)
                continue
            logger.error(f"call failed (final attempt {attempt + 1}): {msg[:200]}")
            raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM call exhausted retries without exception")


def chat_json(system: str, user: str, temperature: float = 0.2) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": system + "\n\n严格只输出 JSON,不要任何前后缀文字、不要 markdown 代码块。",
        },
        {"role": "user", "content": user},
    ]
    raw = _stream_chat(messages, temperature=temperature)
    if not raw.strip():
        logger.error("Empty response from LLM")
        raise RuntimeError("LLM 返回空内容")
    try:
        return _extract_json(raw)
    except ValueError as e:
        logger.error(f"JSON parse failed: {e}\nRAW:\n{raw}")
        raise


def chat_text(system: str, user: str, temperature: float = 0.3) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return _stream_chat(messages, temperature=temperature)


def transcribe_audio(file_path: str) -> str:
    try:
        with open(file_path, "rb") as f:
            resp = _client.audio.transcriptions.create(model="whisper-1", file=f)
        return resp.text
    except Exception as e:
        logger.error(f"transcribe failed: {e}")
        return f"[视频/音频转写失败:{e}]"


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.lstrip("`")
        if text.startswith(("json", "JSON")):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法从 LLM 输出中解析 JSON:\n{text[:500]}")
