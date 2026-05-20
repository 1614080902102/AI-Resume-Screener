"""Concurrent screening engine with Agent-style trace.

Each candidate is processed by an "Agent" that:
1. 🤖 plans:看到候选人材料,决定调用哪些工具
2. 📁 calls parser tools (PDF / DOCX / XLSX / Whisper)
3. 🧠 calls extractor LLM tool (with schema)
4. ⚖️ calls matcher LLM tool (with JD + rules)
5. 💾 calls DB save tool
6. ✅ reports final decision

Per-step traces are returned so the UI can show them.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import db
from .extractor import extract_resume
from .matcher import match_resume
from .parser import parse_file


def _classify_files(filename: str, file_bytes: bytes) -> list[str]:
    """Detect what tools will be called for this material."""
    ext = Path(filename).suffix.lower()
    if ext == ".zip":
        import io, zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = [
                    n for n in zf.namelist()
                    if not n.startswith("__MACOSX/") and not n.endswith(".DS_Store")
                    and not n.endswith("/")
                ]
        except Exception:
            names = []
        tools = []
        for n in names:
            e = Path(n).suffix.lower()
            if e == ".pdf":
                tools.append(f"📄 PDFParser({Path(n).name})")
            elif e == ".docx":
                tools.append(f"📝 DocxParser({Path(n).name})")
            elif e in (".xlsx", ".xls"):
                tools.append(f"📊 XlsxParser({Path(n).name})")
            elif e in (".md", ".markdown", ".txt"):
                tools.append(f"📃 TextReader({Path(n).name})")
            elif e in (".mp4", ".mov", ".avi", ".webm", ".m4a", ".mp3", ".wav"):
                tools.append(f"🎙 Whisper-ASR({Path(n).name})")
            else:
                tools.append(f"📦 BytesReader({Path(n).name})")
        return tools
    if ext == ".pdf":
        return [f"📄 PDFParser({filename})"]
    if ext == ".docx":
        return [f"📝 DocxParser({filename})"]
    if ext in (".xlsx", ".xls"):
        return [f"📊 XlsxParser({filename})"]
    if ext in (".md", ".markdown", ".txt"):
        return [f"📃 TextReader({filename})"]
    if ext in (".mp4", ".mov", ".avi", ".webm", ".m4a", ".mp3", ".wav"):
        return [f"🎙 Whisper-ASR({filename})"]
    return [f"📦 BytesReader({filename})"]


def _screen_one(
    idx: int,
    name: str,
    data: bytes,
    jd_text: str,
    custom_rules: str,
    threshold: int,
    job_id: int,
    trace_cb: Callable[[int, str, str], None] | None = None,
) -> dict:
    """Process one candidate; emit trace events via trace_cb(idx, step, message)."""
    started = time.time()
    trace = []

    def emit(step: str, message: str):
        trace.append({"t": time.time() - started, "step": step, "message": message})
        if trace_cb is not None:
            try:
                trace_cb(idx, step, message)
            except Exception:
                pass

    try:
        emit("plan", f"🤖 收到候选人材料 ({len(data) // 1024} KB),开始规划...")

        tools = _classify_files(name, data)
        emit("plan", f"🧭 识别到 {len(tools)} 个解析工具需调用")
        for t in tools:
            emit("tool", f"  → {t}")

        emit("parse", "📁 [Parser] 提取所有文件文本...")
        raw = parse_file(data, name)
        emit("parse", f"  ✓ 提取完成 ({len(raw):,} 字符)")

        emit("extract", "🧠 [LLM Tool] 调用 Extractor — 抽取结构化简历...")
        rs = extract_resume(raw)
        basic = rs.get("basic", {}) or {}
        cand_name = basic.get("name") or name
        emit(
            "extract",
            f"  ✓ 已识别:{cand_name} · {basic.get('gender') or '—'} · "
            f"{basic.get('years_of_experience') or '?'} 年经验 · "
            f"{len(rs.get('projects') or [])} 个项目 · "
            f"{len(rs.get('skills') or [])} 项技能",
        )

        rules_note = f"含 {len([l for l in custom_rules.splitlines() if l.strip()])} 条 HR 规则" if custom_rules.strip() else "无 HR 规则"
        emit("match", f"⚖️ [LLM Tool] 调用 Matcher — JD 语义匹配({rules_note})...")
        m = match_resume(jd_text, rs, custom_rules)
        score = int(m.get("score", 0))
        passed = score >= threshold
        emit(
            "match",
            f"  ✓ 评分 {score}/100 · {m.get('verdict', '')} · "
            f"{'✅ 通过' if passed else '⏸ 未通过'}(阈值 {threshold})",
        )

        emit("save", "💾 [DB Tool] 写入历史记录...")
        sid = db.save_screening(
            job_id=job_id,
            candidate_name=cand_name,
            candidate_source=name,
            score=score,
            passed=passed,
            verdict=m.get("verdict", ""),
            summary=m.get("summary", ""),
            resume_struct=rs,
            match=m,
        )
        emit("save", f"  ✓ 已入库 #{sid}")
        emit("done", f"✅ 完成 [{time.time() - started:.1f}s]")

        return {
            "idx": idx, "sid": sid, "name": cand_name, "source": name,
            "score": score, "passed": passed, "resume": rs, "match": m,
            "elapsed": time.time() - started, "trace": trace,
        }
    except Exception as e:
        emit("error", f"❌ 失败:{type(e).__name__}: {e}")
        return {
            "idx": idx, "sid": None, "name": name, "source": name,
            "score": -1, "passed": False, "error": f"{type(e).__name__}: {e}",
            "elapsed": time.time() - started, "trace": trace,
        }


def screen_candidates_concurrent(
    inputs: list[tuple[str, bytes]],
    jd_text: str,
    custom_rules: str,
    threshold: int,
    job_id: int,
    max_workers: int = 8,
    progress_cb: Callable[[int, int, dict], None] | None = None,
    trace_cb: Callable[[int, str, str], None] | None = None,
) -> list[dict]:
    """Run N candidates in parallel with optional trace streaming."""
    max_workers = max(1, min(int(max_workers), 20))
    total = len(inputs)
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _screen_one, i, name, data,
                jd_text, custom_rules, threshold, job_id, trace_cb,
            ): i
            for i, (name, data) in enumerate(inputs)
        }
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            if progress_cb is not None:
                try:
                    progress_cb(len(results), total, r)
                except Exception:
                    pass
    results.sort(key=lambda r: r.get("score", -1), reverse=True)
    return results
