"""AI Resume Screener · Multi-page Streamlit App

Pages:
- 🏢 岗位管理   — 多岗位 CRUD,每岗位独立 JD/阈值/规则
- 🎯 候选人初筛 — 选岗位,单/批量上传,LLM 评估,自动入库
- 📊 历史与统计 — 按岗位/时段查询历史,Dashboard,导出

Persistence: SQLite (data/screener.db)
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

from core import db
from core.extractor import extract_resume
from core.matcher import match_resume
from core.parser import parse_file, parse_url
from core.report import screenings_to_excel
from core.screener import screen_candidates_concurrent

EXAMPLES_DIR = Path(__file__).parent / "examples"
CAND_DIR = EXAMPLES_DIR / "candidates"

# 岗位名 → 候选人目录映射
JOB_SLUG_MAP = {
    "AI Agent 开发工程师": "ai_agent",
    "活动策划": "event_planning",
    "海外营销专员": "overseas_marketing",
    "前端工程师 (Vue)": "frontend",
    "AI 内容运营": "ai_content",
}


def load_example_candidates(job_name: str, limit: int | None = None) -> list[tuple[str, bytes]]:
    """根据岗位名加载示例候选人 zip 列表。"""
    slug = None
    for jn, sl in JOB_SLUG_MAP.items():
        if jn in job_name or job_name in jn:
            slug = sl
            break
    if slug is None:
        return []
    folder = CAND_DIR / slug
    if not folder.exists():
        return []
    zips = sorted(folder.glob("*.zip"))
    if limit:
        zips = zips[:limit]
    return [(z.name, z.read_bytes()) for z in zips]

st.set_page_config(
    page_title="AI 简历初筛 Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- One-time DB init + sample seed ----------
db.init_db()
if not db.list_jobs():
    jd_default = (EXAMPLES_DIR / "sample_jd.md").read_text(encoding="utf-8")
    db.create_job(
        name="AI Agent 开发工程师",
        department="AI 创新部",
        jd_text=jd_default,
        threshold=80,
        custom_rules=(
            "- 必须有 3 年以上 Python 一线经验\n"
            "- 加分:有 Dify / LangChain 实战项目\n"
            "- 加分:有跨境业务或海外酒店行业背景\n"
            "- 减分:跳槽频繁(1 年内换 2 次以上)"
        ),
    )


# ---------- Custom CSS ----------
st.markdown(
    """
    <style>
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        color: white;
    }
    .score-card-warn { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
    .score-card-pass { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
    .score-num { font-size: 48px; font-weight: 800; line-height: 1; color: white; }
    .score-label { font-size: 13px; opacity: 0.95; margin-top: 4px; color: white; }
    .pass-badge {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-weight: 700; font-size: 12px; margin-top: 6px;
    }
    .pass-yes { background: rgba(255,255,255,0.25); color: white; }
    .pass-no  { background: rgba(0,0,0,0.2); color: white; }

    .hit-item, .risk-item, .q-item {
        padding: 10px 14px; border-radius: 8px; margin-bottom: 8px;
        font-size: 14px; line-height: 1.55; color: #1a1a1a !important;
    }
    .hit-item  { background: #d4edda; border-left: 4px solid #28a745; }
    .risk-item { background: #fff3cd; border-left: 4px solid #fd7e14; }
    .q-item    { background: #cfe2ff; border-left: 4px solid #0d6efd; }
    .hit-item *, .risk-item *, .q-item * { color: #1a1a1a !important; }

    .rank-row {
        display: flex; align-items: center; gap: 14px;
        padding: 12px 14px; margin-bottom: 6px; border-radius: 10px;
        background: #f7f9fc; color: #1a1a1a;
    }
    .rank-row.pass { background: linear-gradient(90deg, #d4edda 0%, #f7f9fc 100%); }
    .rank-row.fail { background: linear-gradient(90deg, #f8d7da 0%, #f7f9fc 100%); }
    .rank-num { font-size: 18px; font-weight: 700; min-width: 32px; color: #555; }
    .rank-name { font-size: 15px; font-weight: 600; flex: 1; }
    .rank-score { font-size: 18px; font-weight: 800; }
    .job-card {
        padding: 18px 20px;
        border-radius: 14px;
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fc 100%);
        border: 1px solid #e3e8ef;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        margin-bottom: 14px;
        color: #1a1a1a;
        transition: transform .15s ease, box-shadow .15s ease;
    }
    .job-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(102,126,234,0.18);
    }
    .job-card.closed { opacity: 0.55; }
    .job-card-header {
        display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
    }
    .job-id-badge {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 999px;
        background: #eef0ff;
        color: #4f5bd5;
        font-weight: 700;
        font-size: 12px;
    }
    .job-name {
        font-size: 17px; font-weight: 700; color: #1a1a1a; flex: 1;
    }
    .job-status-open {
        background: #d4edda; color: #155724;
        padding: 2px 9px; border-radius: 999px;
        font-size: 11px; font-weight: 600;
    }
    .job-status-closed {
        background: #f8d7da; color: #721c24;
        padding: 2px 9px; border-radius: 999px;
        font-size: 11px; font-weight: 600;
    }
    .job-meta {
        font-size: 13px; color: #5a6373; margin-bottom: 12px;
    }
    .job-meta b { color: #2c3242; }
    .job-stats {
        display: flex; gap: 16px; padding-top: 10px;
        border-top: 1px dashed #e3e8ef;
    }
    .job-stat {
        flex: 1; text-align: center;
    }
    .job-stat-num {
        font-size: 20px; font-weight: 800; color: #4f5bd5; line-height: 1;
    }
    .job-stat-label {
        font-size: 11px; color: #7a8294; margin-top: 4px;
    }
    .small { font-size: 12px; color: #7a8294; }

    /* ----- 候选人画像卡 ----- */
    .profile-card {
        background: linear-gradient(135deg, #ffffff 0%, #f7f9fc 100%);
        border: 1px solid #e3e8ef;
        border-radius: 14px;
        padding: 22px 26px;
        margin-bottom: 14px;
        color: #1a1a1a;
    }
    .profile-header {
        display: flex; align-items: center; gap: 18px;
        padding-bottom: 16px;
        border-bottom: 1px solid #e8ebf3;
        margin-bottom: 16px;
    }
    .profile-avatar {
        width: 64px; height: 64px; border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex; align-items: center; justify-content: center;
        color: white; font-size: 26px; font-weight: 800;
        flex-shrink: 0;
    }
    .profile-name {
        font-size: 22px; font-weight: 700; color: #1a1a1a;
        line-height: 1.2;
    }
    .profile-tagline {
        font-size: 13px; color: #6b7280; margin-top: 4px;
    }
    .profile-section-title {
        font-size: 13px;
        font-weight: 700;
        color: #4f5bd5;
        margin: 16px 0 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .profile-contact {
        display: flex; flex-wrap: wrap; gap: 8px 18px;
        font-size: 13px; color: #4a5160;
    }
    .profile-row {
        padding: 10px 0;
        border-bottom: 1px dashed #eef0f5;
        color: #2c3242;
    }
    .profile-row:last-child { border-bottom: none; }
    .profile-row-title {
        font-weight: 700; font-size: 14px; color: #1a1a1a;
    }
    .profile-row-sub {
        font-size: 12px; color: #6b7280; margin-top: 2px;
    }
    .profile-row-desc {
        font-size: 13px; color: #4a5160;
        margin-top: 6px; line-height: 1.6;
    }
    .skill-tag {
        display: inline-block;
        padding: 4px 11px;
        margin: 0 6px 6px 0;
        border-radius: 999px;
        background: #eef0ff;
        color: #4f5bd5;
        font-size: 12px;
        font-weight: 600;
    }
    .highlight-box {
        background: #fff8e1;
        border-left: 4px solid #ffc107;
        padding: 10px 14px;
        margin-bottom: 8px;
        border-radius: 6px;
        font-size: 13px;
        color: #5d4d00;
        line-height: 1.55;
    }
    .empty-hint {
        font-size: 12px; color: #9ca3af; font-style: italic;
    }
    .portfolio-link {
        display: inline-block;
        margin: 0 8px 6px 0;
        padding: 4px 10px;
        background: #e0f2fe;
        color: #0369a1 !important;
        border-radius: 6px;
        font-size: 12px;
        text-decoration: none;
        font-weight: 500;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ================================================================
# Render helpers
# ================================================================
def render_score_card(match: dict, threshold: int):
    score = int(match.get("score", 0))
    verdict = match.get("verdict", "—")
    verdict_reason = match.get("verdict_reason", "")
    summary = match.get("summary", "")
    passed = score >= threshold
    if passed:
        cls = "score-card-pass"
    elif score >= max(threshold - 15, 0):
        cls = ""
    else:
        cls = "score-card-warn"
    badge = (
        f'<div class="pass-badge pass-yes">✅ 已通过(阈值 {threshold})</div>'
        if passed
        else f'<div class="pass-badge pass-no">⏸ 未通过(阈值 {threshold})</div>'
    )
    st.markdown(
        f"""
        <div class="score-card {cls}">
            <div class="score-num">{score}<span style="font-size:20px;">/100</span></div>
            <div class="score-label">{verdict} · {summary}</div>
            {badge}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if verdict_reason:
        st.caption(f"🧠 **判定依据**:{verdict_reason}")


def render_candidate_profile(resume: dict):
    """HR 友好的候选人画像卡 — 单次 HTML 渲染,避免暗黑模式被劫持。"""
    basic = resume.get("basic", {}) or {}
    name = basic.get("name") or "未知候选人"
    initial = (name[0] if name else "?").strip() or "?"

    def _safe(s):
        return str(s).replace("<", "&lt;").replace(">", "&gt;") if s else ""

    # Header
    tagline_parts = []
    if basic.get("gender"):
        tagline_parts.append(_safe(basic["gender"]))
    if basic.get("age"):
        tagline_parts.append(f"{_safe(basic['age'])} 岁")
    if basic.get("location"):
        tagline_parts.append(_safe(basic["location"]))
    if basic.get("years_of_experience"):
        tagline_parts.append(f"工作 {_safe(basic['years_of_experience'])} 年")
    tagline = "  ·  ".join(tagline_parts) or "—"

    contact_parts = []
    if basic.get("phone"):
        contact_parts.append(f"<span>📞 {_safe(basic['phone'])}</span>")
    if basic.get("email"):
        contact_parts.append(f"<span>✉️ {_safe(basic['email'])}</span>")
    contact_html = (
        f'<div class="profile-contact">{"".join(contact_parts)}</div>'
        if contact_parts else ""
    )

    sections = []

    # 核心亮点
    highlights = resume.get("highlights") or []
    if highlights:
        items = "".join(
            f'<div class="highlight-box">💡 {_safe(h)}</div>' for h in highlights
        )
        sections.append(
            f'<div class="profile-section-title">⭐ 核心亮点</div>{items}'
        )

    # 工作经历
    work = resume.get("work_experience") or []
    if work:
        rows = "".join(
            f'<div class="profile-row">'
            f'<div class="profile-row-title">{_safe(w.get("company", "—"))} · {_safe(w.get("title", "—"))}</div>'
            f'<div class="profile-row-sub">📅 {_safe(w.get("period", "—"))}</div>'
            f'<div class="profile-row-desc">{_safe(w.get("description", ""))}</div>'
            f'</div>'
            for w in work
        )
        sections.append(
            f'<div class="profile-section-title">💼 工作经历</div>{rows}'
        )

    # 项目经验
    projects = resume.get("projects") or []
    if projects:
        rows = []
        for p in projects:
            stack = p.get("tech_stack") or []
            stack_html = "".join(
                f'<span class="skill-tag">{_safe(s)}</span>' for s in stack
            )
            ach = p.get("achievements") or ""
            ach_html = (
                f'<div class="profile-row-desc">📈 <b>成果</b>:{_safe(ach)}</div>'
                if ach else ""
            )
            role = p.get("role") or ""
            role_html = (
                f' · <small style="color:#6b7280;font-weight:500;">{_safe(role)}</small>'
                if role else ""
            )
            rows.append(
                f'<div class="profile-row">'
                f'<div class="profile-row-title">{_safe(p.get("name", "—"))}{role_html}</div>'
                f'<div class="profile-row-desc">{_safe(p.get("description", ""))}</div>'
                f'{ach_html}'
                f'<div style="margin-top:8px">{stack_html}</div>'
                f'</div>'
            )
        sections.append(
            f'<div class="profile-section-title">🚀 项目经验</div>{"".join(rows)}'
        )

    # 教育经历
    edu = resume.get("education") or []
    if edu:
        rows = "".join(
            f'<div class="profile-row">'
            f'<div class="profile-row-title">'
            f'{_safe(e.get("school", "—"))} · {_safe(e.get("degree", ""))} · {_safe(e.get("major", ""))}'
            f'</div>'
            f'<div class="profile-row-sub">📅 {_safe(e.get("period", "—"))}</div>'
            f'</div>'
            for e in edu
        )
        sections.append(
            f'<div class="profile-section-title">🎓 教育经历</div>{rows}'
        )

    # 技能
    skills = resume.get("skills") or []
    if skills:
        tags = "".join(
            f'<span class="skill-tag">{_safe(s)}</span>' for s in skills
        )
        sections.append(
            f'<div class="profile-section-title">🛠 技能栈</div><div>{tags}</div>'
        )

    # 作品集链接
    links = resume.get("portfolio_links") or []
    if links:
        link_html = "".join(
            f'<a class="portfolio-link" href="{_safe(l)}" target="_blank">{_safe(l)}</a>'
            for l in links if l
        )
        sections.append(
            f'<div class="profile-section-title">🔗 作品集 / 链接</div><div>{link_html}</div>'
        )

    body = "".join(sections)

    html = (
        f'<div class="profile-card">'
        f'<div class="profile-header">'
        f'<div class="profile-avatar">{_safe(initial)}</div>'
        f'<div style="flex:1">'
        f'<div class="profile-name">{_safe(name)}</div>'
        f'<div class="profile-tagline">{tagline}</div>'
        f'{contact_html}'
        f'</div>'
        f'</div>'
        f'{body}'
        f'</div>'
    )

    st.markdown(html, unsafe_allow_html=True)


def _bd_score(bd_item) -> int:
    """Backward-compat: 老数据是 int, 新数据是 dict."""
    if isinstance(bd_item, dict):
        return int(bd_item.get("score", 0))
    try:
        return int(bd_item)
    except (TypeError, ValueError):
        return 0


def _bd_explain(bd_item) -> tuple[str, str]:
    if isinstance(bd_item, dict):
        return bd_item.get("evidence", ""), bd_item.get("reasoning", "")
    return "", ""


def render_detail(resume: dict, match: dict):
    bd = match.get("score_breakdown", {})
    if bd:
        labels = [
            ("experience_match", "📅 经验"),
            ("skill_match", "🛠 技能"),
            ("domain_match", "🌐 领域"),
            ("potential", "🚀 潜力"),
        ]
        cols = st.columns(4)
        for col, (key, label) in zip(cols, labels):
            col.metric(label, f"{_bd_score(bd.get(key))}")

        # 评分依据可展开
        with st.expander("📜 评分依据 (HR / 业务方对账用)", expanded=False):
            wexp = bd.get("weight_explanation")
            if wexp:
                st.info(f"**权重说明**:{wexp}")
            for key, label in labels:
                item = bd.get(key)
                score = _bd_score(item)
                evidence, reasoning = _bd_explain(item)
                if not (evidence or reasoning):
                    continue
                st.markdown(
                    f"<div style='padding:10px 14px;background:#f7f9fc;"
                    f"border-left:4px solid #667eea;border-radius:8px;"
                    f"margin-bottom:8px;color:#1a1a1a;'>"
                    f"<div style='font-weight:700;font-size:14px;'>"
                    f"{label} — <span style='color:#4f5bd5'>{score}/100</span></div>"
                    f"<div style='margin-top:6px;font-size:13px;color:#374151;'>"
                    f"📌 <b>依据</b>:{evidence}</div>"
                    f"<div style='margin-top:4px;font-size:13px;color:#374151;'>"
                    f"💭 <b>推理</b>:{reasoning}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    tabs = st.tabs(["✅ 亮点", "⚠️ 风险", "💬 追问问题",
                    "📜 规则符合度", "👤 候选人画像"])

    def _norm_hit(h):
        if isinstance(h, dict):
            return h.get("point", ""), h.get("source", ""), h.get("matches_requirement", "")
        return str(h), "", ""

    def _norm_risk(r):
        if isinstance(r, dict):
            return r.get("point", ""), r.get("missing_in_resume", ""), r.get("vs_requirement", "")
        return str(r), "", ""

    def _norm_q(q):
        if isinstance(q, dict):
            return q.get("question", ""), q.get("targets_risk", ""), q.get("why", "")
        return str(q), "", ""

    with tabs[0]:
        for h in match.get("hits", []) or []:
            point, src, req = _norm_hit(h)
            sub = ""
            if src or req:
                sub_parts = []
                if req:
                    sub_parts.append(f"🎯 命中:{req}")
                if src:
                    sub_parts.append(f"📌 来源:{src}")
                sub = f"<div style='font-size:12px;color:#5a6373;margin-top:6px;'>{' · '.join(sub_parts)}</div>"
            st.markdown(
                f'<div class="hit-item">✅ <b>{point}</b>{sub}</div>',
                unsafe_allow_html=True,
            )
        if not match.get("hits"):
            st.caption("—")

    with tabs[1]:
        for r in match.get("risks", []) or []:
            point, missing, vs = _norm_risk(r)
            sub_parts = []
            if vs:
                sub_parts.append(f"🎯 对照:{vs}")
            if missing:
                sub_parts.append(f"📌 缺失:{missing}")
            sub = (
                f"<div style='font-size:12px;color:#5a6373;margin-top:6px;'>{' · '.join(sub_parts)}</div>"
                if sub_parts else ""
            )
            st.markdown(
                f'<div class="risk-item">⚠️ <b>{point}</b>{sub}</div>',
                unsafe_allow_html=True,
            )
        if not match.get("risks"):
            st.caption("—")

    with tabs[2]:
        for q in match.get("questions", []) or []:
            qtxt, target, why = _norm_q(q)
            sub_parts = []
            if target:
                sub_parts.append(f"🎯 针对:{target}")
            if why:
                sub_parts.append(f"💡 用意:{why}")
            sub = (
                f"<div style='font-size:12px;color:#5a6373;margin-top:6px;'>{' · '.join(sub_parts)}</div>"
                if sub_parts else ""
            )
            st.markdown(
                f'<div class="q-item">💬 <b>{qtxt}</b>{sub}</div>',
                unsafe_allow_html=True,
            )
        if not match.get("questions"):
            st.caption("—")
    with tabs[3]:
        rc = match.get("rule_compliance", []) or []
        if not rc:
            st.info("该岗位未设置自定义规则,或本次评估未注入。")
        else:
            for r in rc:
                ok = r.get("compliant")
                icon = "✅" if ok else "❌"
                cls = "hit-item" if ok else "risk-item"
                st.markdown(
                    f'<div class="{cls}">{icon} <b>{r.get("rule", "")}</b><br/>'
                    f'<small>{r.get("evidence", "")}</small></div>',
                    unsafe_allow_html=True,
                )
    with tabs[4]:
        render_candidate_profile(resume)
        with st.expander("🔧 查看原始 JSON (工程师视角)"):
            st.json(resume)


def show_exception(stage: str, e: Exception):
    import traceback as _tb
    st.error(f"❌ {stage}出错:`{type(e).__name__}: {e}`")
    with st.expander("查看堆栈"):
        st.code(_tb.format_exc())


# ================================================================
# Sidebar — Page navigation
# ================================================================
with st.sidebar:
    st.title("🎯 AI 简历初筛 Agent")
    st.caption("多岗位 · 多格式 · LLM 语义匹配 · HR 可配规则 · SQLite 持久化")

    # 主题切换
    theme_mode = st.radio(
        "🎨 主题",
        ["🌞 浅色", "🌙 深色"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
    )

    page = st.radio(
        "页面",
        ["🏢 岗位管理", "🎯 候选人初筛", "📊 历史与统计", "🤖 Agent 设计"],
        label_visibility="collapsed",
    )

# 全局:隐藏 Streamlit 默认顶部工具栏(Deploy/三点菜单/header) + caption 左对齐
st.markdown(
    """
    <style>
    [data-testid="stToolbar"] { visibility: hidden !important; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 0 !important;
    }
    .stApp > header { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    .stDeployButton { display: none !important; }

    /* caption 强制左对齐,去除任何卡片背景 */
    [data-testid="stCaptionContainer"],
    [data-testid="stMarkdownContainer"] > p > small,
    .stCaption {
        text-align: left !important;
        background: transparent !important;
        padding: 0 !important;
        border: none !important;
        box-shadow: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 深色模式 CSS 覆盖
if theme_mode == "🌙 深色":
    st.markdown(
        """
        <style>
        /* 全局深色背景 */
        .stApp { background-color: #0e1117 !important; }
        section[data-testid="stSidebar"] { background-color: #1a1d27 !important; }
        header[data-testid="stHeader"] { background-color: #0e1117 !important; }

        /* 主区域文字颜色 */
        .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp label,
        .stApp .stMarkdown, .stApp [data-testid="stText"] {
            color: #e6e9ef !important;
        }

        /* 卡片改为深灰背景 */
        .job-card {
            background: linear-gradient(135deg, #1e2230 0%, #252a3d 100%) !important;
            border: 1px solid #2d3349 !important;
            color: #e6e9ef !important;
        }
        .job-card:hover { box-shadow: 0 6px 16px rgba(102,126,234,0.35) !important; }
        .job-name { color: #ffffff !important; }
        .job-meta { color: #aab1c1 !important; }
        .job-meta b { color: #e6e9ef !important; }
        .job-stats { border-top: 1px dashed #2d3349 !important; }
        .job-stat-num { color: #8b9eff !important; }
        .job-stat-label { color: #8b93a7 !important; }
        .job-id-badge { background: #2d3349 !important; color: #b3bdf5 !important; }

        /* Profile card 深色版 */
        .profile-card {
            background: linear-gradient(135deg, #1e2230 0%, #252a3d 100%) !important;
            border: 1px solid #2d3349 !important;
            color: #e6e9ef !important;
        }
        .profile-header { border-bottom: 1px solid #2d3349 !important; }
        .profile-name { color: #ffffff !important; }
        .profile-tagline { color: #aab1c1 !important; }
        .profile-section-title { color: #8b9eff !important; }
        .profile-contact { color: #b8bfd1 !important; }
        .profile-row { border-bottom: 1px dashed #2d3349 !important; color: #d4d8e3 !important; }
        .profile-row-title { color: #ffffff !important; }
        .profile-row-sub { color: #aab1c1 !important; }
        .profile-row-desc { color: #c5cad7 !important; }
        .skill-tag {
            background: #2d3349 !important;
            color: #b3bdf5 !important;
        }
        .highlight-box {
            background: #3d3520 !important;
            color: #ffe599 !important;
            border-left-color: #ffc107 !important;
        }
        .portfolio-link {
            background: #1c3a5c !important;
            color: #7fb6f0 !important;
        }

        /* Hit/Risk/Question cards 深色版 */
        .hit-item {
            background: #1f3a28 !important;
            border-left-color: #4ade80 !important;
            color: #d4f4dd !important;
        }
        .hit-item * { color: #d4f4dd !important; }
        .risk-item {
            background: #3a2e15 !important;
            border-left-color: #fbbf24 !important;
            color: #fde68a !important;
        }
        .risk-item * { color: #fde68a !important; }
        .q-item {
            background: #1c2d4a !important;
            border-left-color: #60a5fa !important;
            color: #c7dafd !important;
        }
        .q-item * { color: #c7dafd !important; }

        /* 排序行深色 */
        .rank-row { background: #1e2230 !important; color: #e6e9ef !important; }
        .rank-row.pass {
            background: linear-gradient(90deg, #1f3a28 0%, #1e2230 100%) !important;
        }
        .rank-row.fail {
            background: linear-gradient(90deg, #3a1e20 0%, #1e2230 100%) !important;
        }
        .rank-num { color: #8b93a7 !important; }
        .rank-name { color: #ffffff !important; }
        .rank-score { color: #ffffff !important; }
        .small { color: #8b93a7 !important; }

        /* Streamlit 内置组件深色适配 */
        .stMetric { background: #1e2230 !important; padding: 10px; border-radius: 8px; }
        [data-testid="stMetricValue"] { color: #ffffff !important; }
        [data-testid="stMetricLabel"] { color: #aab1c1 !important; }
        [data-testid="stMetricDelta"] { color: #8b9eff !important; }

        /* 表格 */
        .stDataFrame, table { background: #1e2230 !important; color: #e6e9ef !important; }

        /* Status 容器 */
        [data-testid="stStatusWidget"] { background: #1a1d27 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ============ 全局 sidebar 底部:并发数 + 岗位统计(无论主题都显示) ============
with st.sidebar:
    st.divider()
    st.subheader("⚡ 并发处理")
    concurrency = st.slider(
        "并发数 (批量模式)",
        min_value=1, max_value=15, value=8, step=1,
        help="同时处理多少个候选人。API 限流时调低,稳定时调高。",
    )
    st.caption(f"💡 8 并发约 {8 * 5:.0f}-{8 * 8:.0f} 份/分钟")

    st.divider()
    jobs_all = db.list_jobs()
    open_n = sum(1 for j in jobs_all if j["status"] == "open")
    st.caption(
        f"📌 当前 **{len(jobs_all)}** 个岗位 · 开放 **{open_n}** 个"
    )


# ================================================================
# Page 1: 岗位管理
# ================================================================
def page_jobs():
    st.title("🏢 岗位管理")
    st.caption("每个岗位独立配置 JD + 通过阈值 + 自定义匹配规则。")

    with st.expander("➕ 新建岗位", expanded=False):
        with st.form("new_job", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("岗位名称*", placeholder="如:AI Agent 开发工程师")
            dept = c2.text_input("部门", placeholder="如:AI 创新部")
            jd = st.text_area("岗位 JD*", height=200,
                              placeholder="粘贴完整 JD 文本...")
            c3, c4 = st.columns(2)
            thr = c3.slider("通过阈值", 50, 95, 80, 5)
            rules = c4.text_area(
                "自定义匹配规则",
                placeholder=(
                    "- 必须有 3 年以上 Python\n"
                    "- 加分:跨境业务背景\n"
                    "- 减分:跳槽频繁"
                ),
                height=120,
            )
            submit = st.form_submit_button("✅ 创建岗位", type="primary")
            if submit:
                if not name.strip() or not jd.strip():
                    st.error("岗位名称和 JD 必填")
                else:
                    jid = db.create_job(name, jd, thr, rules, dept)
                    st.success(f"已创建岗位 #{jid}: {name}")
                    st.rerun()

    st.divider()
    head1, head2 = st.columns([3, 1])
    head1.subheader("📋 岗位列表")
    sort_by = head2.selectbox(
        "排序",
        ["按编号 ↑", "按编号 ↓", "按更新时间 ↓"],
        label_visibility="collapsed",
    )
    order_map = {
        "按编号 ↑": "id_asc",
        "按编号 ↓": "id_desc",
        "按更新时间 ↓": "updated_desc",
    }

    jobs = db.list_jobs(order=order_map[sort_by])
    if not jobs:
        st.info("还没有岗位 — 用上面表单创建第一个。")
        return

    # 取统计数据用于卡片显示
    gs = {j["id"]: j for j in db.global_stats()["jobs"]}

    # 双列网格
    cols_per_row = 2
    for i in range(0, len(jobs), cols_per_row):
        row = st.columns(cols_per_row, gap="medium")
        for col, job in zip(row, jobs[i:i + cols_per_row]):
            with col:
                stats = gs.get(job["id"], {})
                total = stats.get("total") or 0
                passed = stats.get("passed") or 0
                avg = stats.get("avg_score")
                pass_rate = f"{(passed / total * 100):.0f}%" if total else "—"
                avg_str = f"{round(avg, 1)}" if avg else "—"
                status_html = (
                    '<span class="job-status-open">● 开放中</span>'
                    if job["status"] == "open"
                    else '<span class="job-status-closed">● 已关闭</span>'
                )
                closed_cls = "closed" if job["status"] == "closed" else ""

                st.markdown(
                    f"""
                    <div class="job-card {closed_cls}">
                        <div class="job-card-header">
                            <span class="job-id-badge">#{job['id']}</span>
                            <span class="job-name">{job['name']}</span>
                            {status_html}
                        </div>
                        <div class="job-meta">
                            🏢 {job.get('department') or '—'}  ·
                            🎚️ 阈值 <b>{job['threshold']}</b>  ·
                            🕒 {job['updated_at'][:10]}
                        </div>
                        <div class="job-stats">
                            <div class="job-stat">
                                <div class="job-stat-num">{total}</div>
                                <div class="job-stat-label">总投递</div>
                            </div>
                            <div class="job-stat">
                                <div class="job-stat-num">{passed}</div>
                                <div class="job-stat-label">已通过</div>
                            </div>
                            <div class="job-stat">
                                <div class="job-stat-num">{pass_rate}</div>
                                <div class="job-stat-label">通过率</div>
                            </div>
                            <div class="job-stat">
                                <div class="job-stat-num">{avg_str}</div>
                                <div class="job-stat-label">平均分</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander("⚙️ 编辑 / 删除", expanded=False):
                    with st.form(f"edit_{job['id']}"):
                        e1, e2 = st.columns(2)
                        e_name = e1.text_input("岗位名称", value=job["name"])
                        e_dept = e2.text_input("部门", value=job.get("department") or "")
                        e_jd = st.text_area("JD", value=job["jd_text"], height=160)
                        e3, e4 = st.columns(2)
                        e_thr = e3.slider(
                            "通过阈值", 50, 95, int(job["threshold"]), 5,
                            key=f"thr_{job['id']}",
                        )
                        e_rules = e4.text_area(
                            "自定义规则", value=job["custom_rules"] or "",
                            height=100, key=f"rules_{job['id']}",
                        )
                        e_status = st.radio(
                            "状态", ["open", "closed"],
                            index=0 if job["status"] == "open" else 1,
                            horizontal=True, key=f"st_{job['id']}",
                        )
                        cc1, cc2 = st.columns([3, 1])
                        if cc1.form_submit_button("💾 保存", type="primary"):
                            db.update_job(
                                job["id"], name=e_name, department=e_dept,
                                jd_text=e_jd, threshold=e_thr,
                                custom_rules=e_rules, status=e_status,
                            )
                            st.success("已保存")
                            st.rerun()
                        if cc2.form_submit_button("🗑️ 删除"):
                            db.delete_job(job["id"])
                            st.warning(f"已删除 #{job['id']}")
                            st.rerun()


# ================================================================
# Page 2: 候选人初筛
# ================================================================
def page_screen():
    st.title("🎯 候选人初筛")
    jobs_open = db.list_jobs(status="open")
    if not jobs_open:
        st.warning("还没有开放中的岗位 — 请先去【岗位管理】创建。")
        return

    options = [f"#{j['id']} · {j['name']}" for j in jobs_open]
    pick = st.selectbox("选择岗位", options)
    job = jobs_open[options.index(pick)]

    with st.expander("查看该岗位配置", expanded=False):
        st.write(f"**部门**:{job.get('department') or '—'}")
        st.write(f"**通过阈值**:{job['threshold']}")
        st.write(f"**自定义规则**:")
        st.code(job.get("custom_rules") or "(无)")
        st.write("**JD**:")
        st.markdown(job["jd_text"])

    mode = st.radio(
        "模式",
        ["🧑 单候选人模式", "👥 批量模式 (多个 zip)"],
        horizontal=True,
    )

    threshold = int(job["threshold"])
    rules = job.get("custom_rules") or ""
    jd_text = job["jd_text"]

    # ---------- 单候选人 ----------
    if mode.startswith("🧑"):
        col_in, col_out = st.columns([1, 1.4], gap="large")
        with col_in:
            st.subheader("📥 候选人材料")
            use_demo = st.checkbox(
                f"🚀 使用本岗位示例候选人(取池中第 1 位)", value=False,
                key=f"single_demo_{job['id']}",
            )
            files = st.file_uploader(
                "上传文件(PDF/Word/Excel/MD/视频/ZIP)",
                type=["pdf", "docx", "xlsx", "xls", "md", "markdown", "txt",
                      "mp4", "mov", "avi", "webm", "m4a", "mp3", "wav", "zip"],
                accept_multiple_files=True, disabled=use_demo,
                key=f"single_files_{job['id']}",
            )
            urls = st.text_area(
                "作品集 / 个人网站(每行一个)", height=70,
                disabled=use_demo, key=f"single_urls_{job['id']}",
            )
            notes = st.text_area(
                "补充说明", height=60, disabled=use_demo,
                key=f"single_notes_{job['id']}",
            )
            run = st.button("🎯 开始初筛", type="primary", use_container_width=True)

        with col_out:
            st.subheader("📊 评估结果")
            out = st.empty()
            if not run:
                out.info("👈 上传材料或勾选示例,点击「开始初筛」")

        if run:
            sources, chunks = [], []
            if use_demo:
                # 从该岗位的强匹配候选人池里取第一个示例
                examples = load_example_candidates(job["name"], limit=1)
                if not examples:
                    out.error("此岗位还没有示例候选人")
                    st.stop()
                ex_name, ex_bytes = examples[0]
                chunks.append(parse_file(ex_bytes, ex_name))
                sources.append(f"示例:{ex_name}")
            else:
                if files:
                    for f in files:
                        data = f.read()
                        sources.append(f"文件:{f.name}")
                        chunks.append(f"=== {f.name} ===\n{parse_file(data, f.name)}")
                if urls.strip():
                    for u in [x.strip() for x in urls.splitlines() if x.strip()]:
                        sources.append(f"URL:{u}")
                        chunks.append(f"=== {u} ===\n{parse_url(u)}")
                if notes.strip():
                    sources.append("补充说明")
                    chunks.append(f"=== 补充说明 ===\n{notes}")

            raw = "\n\n".join(chunks).strip()
            if not raw:
                out.error("请至少上传一份材料")
                st.stop()

            with out.container():
                with st.status("处理中...", expanded=True) as status:
                    st.write(f"✅ 采集 {len(sources)} 个来源")
                    try:
                        t = time.time()
                        rs = extract_resume(raw)
                        st.write(f"  🧠 抽取 {time.time()-t:.1f}s")
                        t = time.time()
                        m = match_resume(jd_text, rs, rules)
                        st.write(f"  🎯 匹配 {time.time()-t:.1f}s")
                    except Exception as e:
                        status.update(label="失败", state="error")
                        show_exception("评估", e)
                        st.stop()
                    status.update(label="✅ 完成", state="complete", expanded=False)

                # 自动入库
                sid = db.save_screening(
                    job_id=job["id"],
                    candidate_name=rs.get("basic", {}).get("name") or "(未识别)",
                    candidate_source=", ".join(sources)[:200],
                    score=int(m.get("score", 0)),
                    passed=int(m.get("score", 0)) >= threshold,
                    verdict=m.get("verdict", ""),
                    summary=m.get("summary", ""),
                    resume_struct=rs,
                    match=m,
                )
                st.toast(f"✅ 已入库 #{sid}", icon="💾")

                render_score_card(m, threshold)
                render_detail(rs, m)

                # HR 友好的 Excel 单条报告
                excel_bytes = screenings_to_excel(
                    [{
                        "id": sid,
                        "candidate_name": rs.get("basic", {}).get("name") or "—",
                        "candidate_source": ", ".join(sources)[:200],
                        "score": int(m.get("score", 0)),
                        "passed": int(m.get("score", 0)) >= threshold,
                        "verdict": m.get("verdict", ""),
                        "summary": m.get("summary", ""),
                        "created_at": db.get_screening(sid)["created_at"],
                        "resume": rs,
                        "match": m,
                    }],
                    job_name=job["name"],
                )
                st.download_button(
                    "📊 下载 HR 评估报告 (Excel)",
                    data=excel_bytes,
                    file_name=f"评估报告-{job['name']}-{rs.get('basic',{}).get('name') or sid}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    # ---------- 批量模式 ----------
    else:
        col_in, col_out = st.columns([1, 1.7], gap="large")
        with col_in:
            st.subheader("📥 批量上传")
            example_count = len(load_example_candidates(job["name"]))
            use_batch_demo = st.checkbox(
                f"🚀 使用本岗位示例候选人池(共 {example_count} 人)",
                value=False, key=f"batch_demo_{job['id']}",
                disabled=example_count == 0,
                help="不同岗位对应不同的候选人 — 强匹配/中等/弱各 5 人",
            )
            demo_n = example_count
            if use_batch_demo and example_count > 0:
                demo_n = st.slider(
                    f"使用前 N 个示例候选人",
                    1, example_count, min(15, example_count),
                    key=f"demo_n_{job['id']}",
                )
            zips = st.file_uploader(
                "或上传自己的 ZIP(每包=一个候选人全部材料)",
                type=["zip"], accept_multiple_files=True,
                disabled=use_batch_demo, key=f"batch_zips_{job['id']}",
            )
            run = st.button("🎯 批量初筛 + 排序", type="primary",
                            use_container_width=True)

        with col_out:
            st.subheader("🏆 排序榜")
            out = st.empty()
            if not run:
                out.info("👈 上传多个 ZIP 或勾选示例,点击「批量初筛」")

        if run:
            inputs: list[tuple[str, bytes]] = []
            if use_batch_demo:
                inputs = load_example_candidates(job["name"], limit=demo_n)
                if not inputs:
                    out.error("此岗位还没有示例候选人池")
                    st.stop()
            else:
                if not zips:
                    out.error("请至少上传一个 ZIP")
                    st.stop()
                for f in zips:
                    inputs.append((f.name, f.read()))

            with out.container():
                started_at = time.time()
                # 实时进度状态卡片(st.status 在 Streamlit 是真实时的)
                with st.status(
                    f"⚡ 并发处理中 (并发数 {concurrency}, 共 {len(inputs)} 个候选人)...",
                    expanded=True,
                ) as status:
                    progress_log = st.empty()
                    rolling = []

                    def on_progress(done: int, total: int, latest: dict):
                        elapsed = time.time() - started_at
                        if latest.get("error"):
                            mark = f"❌ {latest['name']} 失败"
                        else:
                            mark = (
                                f"{'✅' if latest['passed'] else '⏸'} "
                                f"{latest['name']} — {latest['score']}/100"
                            )
                        rolling.append(
                            f"`[{elapsed:5.1f}s]` `{done}/{total}`  {mark}"
                        )
                        # 只显示最新 10 条避免太长
                        progress_log.markdown("\n\n".join(rolling[-10:]))

                    results = screen_candidates_concurrent(
                        inputs=inputs,
                        jd_text=jd_text,
                        custom_rules=rules,
                        threshold=threshold,
                        job_id=job["id"],
                        max_workers=concurrency,
                        progress_cb=on_progress,
                    )
                    total_t = time.time() - started_at
                    passed_n = sum(1 for r in results if r.get("passed"))
                    err_n = sum(1 for r in results if r.get("error"))
                    status.update(
                        label=(
                            f"✅ 完成 {len(results)} 人 · 通过 {passed_n} · "
                            f"失败 {err_n} · 耗时 {total_t:.1f}s"
                        ),
                        state="complete",
                        expanded=False,
                    )

                # 总览大字
                avg_per_candidate = total_t / max(len(results), 1)
                speed_text = (
                    f"⚡ **{len(results) / total_t * 60:.1f}** 份/分钟"
                    if total_t > 0 else "—"
                )
                colA, colB, colC, colD = st.columns(4)
                colA.metric("总人数", len(results))
                colB.metric("通过", passed_n,
                            delta=f"{passed_n / len(results) * 100:.0f}%"
                            if results else "0%")
                colC.metric("总耗时", f"{total_t:.1f}s",
                            delta=f"每人 {avg_per_candidate:.1f}s")
                colD.metric("吞吐量", speed_text)
                for idx, r in enumerate(results, 1):
                    if r.get("error"):
                        st.markdown(
                            f'<div class="rank-row fail"><div class="rank-num">#{idx}</div>'
                            f'<div class="rank-name">{r["name"]}</div>'
                            f'<div class="rank-score">❌</div></div>',
                            unsafe_allow_html=True,
                        )
                        with st.expander(f"错误:{r['name']}"):
                            st.error(r["error"])
                        continue
                    cls = "pass" if r["passed"] else "fail"
                    badge = "✅" if r["passed"] else "⏸"
                    st.markdown(
                        f'<div class="rank-row {cls}">'
                        f'<div class="rank-num">#{idx}</div>'
                        f'<div class="rank-name">{r["name"]} '
                        f'<small style="color:#666">({r["source"]})</small></div>'
                        f'<div class="rank-score">{r["score"]}/100 {badge}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    with st.expander(f"📖 详情 + 🤖 Agent 思考过程 - {r['name']}"):
                        sub_tabs = st.tabs(["📊 评估结果", "🤖 Agent Trace"])
                        with sub_tabs[0]:
                            render_score_card(r["match"], threshold)
                            render_detail(r["resume"], r["match"])
                        with sub_tabs[1]:
                            trace = r.get("trace") or []
                            if not trace:
                                st.caption("(无 trace)")
                            else:
                                st.caption(
                                    f"💡 Agent 在 {r.get('elapsed', 0):.1f}s 内完成了 "
                                    f"{len(trace)} 步操作"
                                )
                                for ev in trace:
                                    icon = {
                                        "plan": "🤖", "tool": "🔧",
                                        "parse": "📁", "extract": "🧠",
                                        "match": "⚖️", "save": "💾",
                                        "done": "✅", "error": "❌",
                                    }.get(ev["step"], "·")
                                    st.markdown(
                                        f"<div style='font-family:Menlo,monospace;"
                                        f"font-size:12px;padding:3px 8px;"
                                        f"border-left:3px solid #667eea;"
                                        f"margin-bottom:3px;background:#f8f9fc;"
                                        f"color:#1a1a1a;'>"
                                        f"<span style='color:#888;'>[{ev['t']:5.2f}s]</span> "
                                        f"{icon} {ev['message']}"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )

                # 批量结果一键导出 Excel
                exportable = [
                    {
                        "id": r.get("sid"),
                        "candidate_name": r.get("name"),
                        "candidate_source": r.get("source"),
                        "score": r.get("score", 0),
                        "passed": r.get("passed", False),
                        "verdict": (r.get("match") or {}).get("verdict", ""),
                        "summary": (r.get("match") or {}).get("summary", ""),
                        "created_at": "",
                        "resume": r.get("resume") or {},
                        "match": r.get("match") or {},
                    }
                    for r in results if not r.get("error")
                ]
                if exportable:
                    excel_bytes = screenings_to_excel(
                        exportable, job_name=job["name"]
                    )
                    st.markdown("---")
                    st.download_button(
                        "📊 一键导出本次批量结果 (Excel)",
                        data=excel_bytes,
                        file_name=f"批量初筛-{job['name']}-{int(time.time())}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                    )


# ================================================================
# Page 3: 历史与统计
# ================================================================
def page_history():
    st.title("📊 历史与统计")
    jobs_all = db.list_jobs()
    if not jobs_all:
        st.info("还没有岗位,请先创建。")
        return

    # 全局 dashboard
    st.subheader("🌐 全局概览")
    gs = db.global_stats()
    if gs["jobs"]:
        total_screen = sum((j["total"] or 0) for j in gs["jobs"])
        total_pass = sum((j["passed"] or 0) for j in gs["jobs"])
        c1, c2, c3 = st.columns(3)
        c1.metric("岗位数", len(gs["jobs"]))
        c2.metric("累计初筛", total_screen)
        c3.metric("累计通过", total_pass,
                  delta=f"{total_pass/total_screen*100:.0f}%" if total_screen else "0%")

        st.dataframe(
            [
                {
                    "岗位": j["name"],
                    "阈值": j["threshold"],
                    "投递": j["total"] or 0,
                    "通过": j["passed"] or 0,
                    "通过率": (f"{(j['passed'] or 0) / j['total'] * 100:.0f}%"
                               if j["total"] else "—"),
                    "平均分": round(j["avg_score"], 1) if j["avg_score"] else "—",
                }
                for j in gs["jobs"]
            ],
            use_container_width=True, hide_index=True,
        )

    st.divider()
    st.subheader("🔎 按岗位深入查询")

    options = [f"#{j['id']} · {j['name']}" for j in jobs_all]
    pick = st.selectbox("选择岗位", options, key="hist_job")
    job = jobs_all[options.index(pick)]

    # 单岗位统计
    js = db.job_stats(job["id"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总投递", js["total"])
    c2.metric("通过数", js["passed"])
    c3.metric("通过率", f"{js['pass_rate']*100:.0f}%" if js["total"] else "—")
    c4.metric("平均分", js["avg_score"] if js["total"] else "—")

    # 按日趋势
    if js["per_day"]:
        import pandas as pd
        df = pd.DataFrame(js["per_day"])
        df.columns = ["日期", "投递数", "通过数", "平均分"]
        if len(df) == 1:
            d = df.iloc[0]
            st.info(
                f"📅 当前仅有 **{d['日期']}** 一天的数据 — "
                f"投递 **{int(d['投递数'])}** 人 · "
                f"通过 **{int(d['通过数'])}** 人 · "
                f"平均分 **{round(d['平均分'], 1)}**。"
                f"\n\n*多日数据时会自动绘制趋势图。*"
            )
        else:
            tab1, tab2 = st.tabs(["📈 投递/通过趋势", "📊 平均分趋势"])
            with tab1:
                st.bar_chart(df, x="日期", y=["投递数", "通过数"], height=220)
            with tab2:
                st.line_chart(df, x="日期", y="平均分", height=220)

    # 筛选 + 列表
    st.markdown("##### 候选人记录")
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
    today = date.today()
    start = f1.date_input("起始日期", today - timedelta(days=30))
    end = f2.date_input("结束日期", today)
    pass_only = f3.checkbox("仅看通过", value=False)
    min_score = f4.slider("最低分", 0, 100, 0, 5)

    items = db.list_screenings(
        job_id=job["id"],
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        passed_only=pass_only,
        min_score=min_score if min_score > 0 else None,
    )

    if not items:
        if js["total"] == 0:
            st.warning(
                f"⚠️ 岗位「{job['name']}」还没有候选人初筛记录 — "
                f"去【🎯 候选人初筛】跑几个候选人后再来看。"
            )
        else:
            st.info("当前筛选条件下没有记录,试着调宽日期/分数范围。")
    else:
        st.caption(f"共 {len(items)} 条记录")
        for idx, r in enumerate(items, 1):
            cls = "pass" if r["passed"] else "fail"
            badge = "✅ 通过" if r["passed"] else "⏸ 未通过"
            basic = (r.get("resume") or {}).get("basic", {}) or {}
            tags = []
            if basic.get("gender"):
                tags.append(basic["gender"])
            if basic.get("age"):
                tags.append(f"{basic['age']}岁")
            if basic.get("location"):
                tags.append(basic["location"])
            if basic.get("years_of_experience"):
                tags.append(f"{basic['years_of_experience']}年经验")
            tag_html = "  ·  ".join(tags) if tags else "—"

            summary = r.get("summary") or "—"
            top_hit = ((r.get("match") or {}).get("hits") or ["—"])[0]
            initial = (r.get("candidate_name") or "?")[0]
            row_bg = (
                "linear-gradient(90deg, #d4edda 0%, #ffffff 100%)"
                if r["passed"]
                else "linear-gradient(90deg, #fff5f5 0%, #ffffff 100%)"
            )
            border_color = "#28a745" if r["passed"] else "#dc3545"

            st.markdown(
                f"""
                <div style="background:{row_bg};
                            border-left:4px solid {border_color};
                            border-radius:10px; padding:14px 18px;
                            margin-bottom:10px; color:#1a1a1a;
                            display:flex; align-items:center; gap:14px;">
                    <div style="font-size:14px;font-weight:700;color:#888;min-width:30px;">
                        #{idx}
                    </div>
                    <div style="width:46px;height:46px;border-radius:50%;
                                background:linear-gradient(135deg,#667eea,#764ba2);
                                color:white;font-weight:800;font-size:18px;
                                display:flex;align-items:center;justify-content:center;
                                flex-shrink:0;">{initial}</div>
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:15px;font-weight:700;color:#1a1a1a;">
                            {r['candidate_name']}
                        </div>
                        <div style="font-size:12px;color:#6b7280;margin-top:2px;">
                            {tag_html}  ·  {r['created_at'][:16]}
                        </div>
                        <div style="font-size:13px;color:#4a5160;margin-top:6px;
                                    line-height:1.5;">
                            💬 {summary}
                        </div>
                        <div style="font-size:12px;color:#155724;background:#d4edda;
                                    padding:4px 10px;border-radius:6px;
                                    margin-top:6px;display:inline-block;">
                            ✅ {top_hit}
                        </div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:24px;font-weight:800;color:#1a1a1a;">
                            {r['score']}<span style="font-size:14px;color:#888;">/100</span>
                        </div>
                        <div style="font-size:12px;color:{'#155724' if r['passed'] else '#721c24'};
                                    font-weight:600;margin-top:2px;">
                            {badge}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"📖 完整画像 + 评估详情 - {r['candidate_name']}"):
                render_score_card(r["match"], job["threshold"])
                render_detail(r["resume"], r["match"])
                if st.button(f"🗑️ 删除记录 #{r['id']}",
                             key=f"del_{r['id']}"):
                    db.delete_screening(r["id"])
                    st.rerun()

        excel_bytes = screenings_to_excel(items, job_name=job["name"])
        st.download_button(
            "📊 导出 Excel 报告 (HR 友好)",
            data=excel_bytes,
            file_name=f"候选人初筛报告-{job['name']}-{start}至{end}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="包含每个候选人的姓名/性别/年龄/经验/分数/通过状态/亮点/风险/追问问题等",
        )


# ================================================================
# Page 4: Agent 设计
# ================================================================
def page_agent_design():
    st.title("🤖 Agent 设计原理")
    st.caption("揭开黑盒 — 这个 Agent 是怎么工作的、用了哪些工具、做了什么决策")

    st.markdown("---")

    st.subheader("🧠 Agent 是什么")
    st.markdown(
        """
        一个 **AI Agent** 不是简单"调 LLM 给个答案",而是一个能:

        1. **理解任务** — 收到候选人材料知道要做什么
        2. **规划步骤** — 决定先做什么后做什么
        3. **调用工具** — 主动选择合适的解析器 / LLM / 数据库
        4. **观察结果** — 看到中间结果决定下一步
        5. **输出决策** — 最后给出可执行的判断

        这个 **简历初筛 Agent** 就是按这个模式工作的。
        """
    )

    st.markdown("---")
    st.subheader("🏗 Agent 架构")
    st.markdown(
        """
        ```
        ┌─────────────────────────────────────────────────────────┐
        │                  🤖 Screening Agent                      │
        │                                                          │
        │  Goal: 对候选人 X 做初筛,基于 JD Y + HR 规则 Z          │
        │                                                          │
        │  Plan:                                                   │
        │   1. 识别材料格式 → 选解析器                              │
        │   2. 抽取结构化画像                                       │
        │   3. 评分 + 规则合规检查                                  │
        │   4. 入库 + 输出决策                                      │
        │                                                          │
        │  Tools Available:                                        │
        │   📄 PDFParser    📝 DocxParser   📊 XlsxParser          │
        │   📃 TextReader   🎙 Whisper-ASR  📦 ZipExtractor        │
        │   🧠 LLM-Extract  ⚖️ LLM-Match    💾 DB-Save             │
        │                                                          │
        │  Memory:                                                 │
        │   - 短期: trace (本次处理的所有步骤)                       │
        │   - 长期: SQLite (所有历史评估,可追溯/统计)               │
        │                                                          │
        │  Personality (HR 可配):                                  │
        │   - 通过阈值 (严格/宽松)                                  │
        │   - 自定义规则 (必须项/加分项/减分项)                      │
        └─────────────────────────────────────────────────────────┘
        ```
        """
    )

    st.markdown("---")
    st.subheader("🔧 工具清单")

    tools_data = [
        ("📄 PDFParser", "pypdf", "PDF 简历提取纯文本", "确定性"),
        ("📝 DocxParser", "python-docx", "Word 自荐信 / 报告", "确定性"),
        ("📊 XlsxParser", "openpyxl", "Excel 作品集 / 项目表", "确定性"),
        ("📃 TextReader", "io", "Markdown / TXT", "确定性"),
        ("🎙 Whisper-ASR", "OpenAI Whisper", "视频自我介绍转写", "AI"),
        ("📦 ZipExtractor", "zipfile", "解开邮件附件包", "确定性"),
        ("🌐 URLFetcher", "requests + bs4", "抓取作品集网站", "确定性"),
        ("🧠 LLM-Extract", "GPT-5.4 / Claude", "把原始文本抽成 14 字段 JSON 画像", "AI"),
        ("⚖️ LLM-Match", "GPT-5.4 / Claude", "JD + HR 规则 语义级评分", "AI"),
        ("💾 DB-Save", "SQLite", "持久化所有评估,可追溯", "确定性"),
    ]
    st.dataframe(
        [{"工具": t[0], "底层实现": t[1], "用途": t[2], "类型": t[3]} for t in tools_data],
        use_container_width=True, hide_index=True,
    )

    st.markdown("---")
    st.subheader("🎯 Agent 工作流")
    st.markdown(
        """
        每个候选人,Agent 经历 **6 个阶段**:

        | 阶段 | Agent 在做什么 | 调用工具 |
        |---|---|---|
        | 1. **Plan** | 分析材料格式,规划工具链 | (内部) |
        | 2. **Parse** | 多工具并行解析所有附件 | PDFParser / DocxParser / XlsxParser / Whisper |
        | 3. **Extract** | LLM 抽取 14 字段画像 | LLM-Extract |
        | 4. **Match** | LLM 评分 + 规则合规 | LLM-Match |
        | 5. **Save** | 入库 + 写入 trace | DB-Save |
        | 6. **Done** | 输出决策 + 通过/不通过 | (内部) |

        **每一步都有可观测的 trace** — 在批量结果里展开任一候选人,
        切到 **「🤖 Agent Trace」**Tab 就能看到 Agent 的完整思考过程。
        """
    )

    st.markdown("---")
    st.subheader("⚡ 并发模型")
    st.markdown(
        """
        生产场景 HR 每天收几千份简历,**串行处理几十小时**赶不上。

        Agent 通过 **ThreadPoolExecutor 多个 Agent 实例并发** 解决:

        ```
        Job Queue (N 个候选人)
              ↓
        ┌─────┴─────┐
        │  Worker 1 │ Agent ──→ LLM
        │  Worker 2 │ Agent ──→ LLM
        │  Worker 3 │ Agent ──→ LLM   (同时 8 个,可调)
        │     ...   │   ...
        │  Worker 8 │ Agent ──→ LLM
        └───────────┘
              ↓
        as_completed → 排序 → UI 实时显示
        ```

        - **每个 Worker 独立 Agent** 实例,处理一个候选人完整全流程
        - **失败的不阻塞其他** — 单个 LLM 调用失败,其他 Worker 继续
        - **退避重试** — 每个 LLM 调用有 3 次指数退避
        - **可观测** — 实时进度 + 每个候选人的 trace 都可查
        """
    )

    st.markdown("---")
    st.subheader("📜 HR 可配置的 Agent 行为")
    st.markdown(
        """
        Agent 不是"出厂即定"的黑盒 — HR 可以**实时调整 Agent 的判断标准**:

        - 🎚️ **通过阈值** — 严格(85)还是宽松(65),看池子大小动态调
        - 📜 **匹配规则** — "必须有跨境业务" / "加分:Dify 实战" 等
        - 🧵 **并发数** — API 限流时降速,稳定时跑满

        所有这些参数**都会注入到 Agent 的 system prompt 里**,
        让 Agent 按 HR 的具体要求评分,而不是按通用规则。
        """
    )

    st.markdown("---")
    st.subheader("🎬 视频材料的深度处理(V2 重点)")
    st.warning(
        "**当前 V1 实现**:视频仅做 Whisper 音频转写 —— "
        "适合**自我介绍 / 口播讲解**类视频,但**作品集 / 活动现场 / "
        "PPT 演讲**类视频会丢失大量视觉信息。"
    )

    st.markdown(
        """
        ### 视频不只是「自我介绍」 — 至少 4 种类型

        | 视频类型 | 当前 V1 处理 | V2 应该怎么处理 |
        |---|---|---|
        | 🗣 **自我介绍 / 口播** | ✅ Whisper 转写够用 | 保持不变 |
        | 🎨 **作品集 / 产品 demo / UI 录屏** | ❌ 听不到画面 | **Vision LLM 看关键帧** |
        | 🎤 **活动现场视频** | ❌ 只听到杂音 | Whisper + Vision **结合判断** |
        | 📊 **PPT / 案例讲解** | ⚠️ 只能听文字,看不到图 | Vision OCR + Whisper |

        ### V2 视频理解架构

        ```
        🎬 候选人视频
            ↓
            ├── 1. 🎙 Whisper 音频转写  ← V1 已有
            ├── 2. 🖼 ffmpeg 抽关键帧  (每 5s 一帧, 8-15 张)
            ├── 3. 👁 Vision LLM (GPT-4V / Claude-3 Sonnet)
            │      → 描述每帧画面 (场景/人物/文字/产品 UI)
            ├── 4. 🧠 综合分类 Agent
            │      → 判断视频类型 (自我介绍 / 作品 / 活动 / 演讲)
            └── 5. 📝 合成完整描述给 Extractor
        ```

        ### 工程上的注意点

        1. **成本控制** — Vision 调用比文本 LLM 贵 5-10x,
           不能每帧都调,需要先做关键帧筛选
        2. **延迟** — Vision 调用比文本慢,
           视频处理可能成为整个 Pipeline 的瓶颈
        3. **降级** — 视频处理失败不能阻塞整个候选人评估,
           失败时回退到「只用 Whisper 转写」
        4. **类型识别先行** — 用文件名 / 时长 / 帧抽样**先判断类型**,
           再决定调几次 Vision (省成本)

        ### 真实场景对照

        - 候选人投**活动策划岗**,附了 1 分钟现场视频:
          - V1 只听到 "今天天气不错" 的杂音 → 评分会偏低
          - V2 看到画面 "200 人会场 / 国际嘉宾 / 高级布置" → 评分准确
        - 候选人投**前端岗**,附了 30 秒产品 UI 录屏:
          - V1 全程静音 → 完全无信息
          - V2 看到 UI 流畅度 / 设计细节 → 能给出技术评价
        """
    )

    st.markdown("---")
    st.subheader("🚀 V2 规划(可接 Dify 编排)")
    st.markdown(
        """
        当前实现是**单 Agent 处理单候选人** + 并发池。下一步可以演进为
        **多 Agent 协作**(用 Dify Workflow 编排):

        - **采集 Agent** — 监听 HR 邮箱,自动归类候选人材料
        - **抽取 Agent** — 当前的 LLM-Extract
        - **匹配 Agent** — 当前的 LLM-Match
        - **背调 Agent** — 自动搜索候选人公开信息(GitHub / 知乎 / 公开演讲)
        - **HR 反馈 Agent** — 收集 HR 标记 → 持续微调匹配策略 (RLHF-lite)

        所有 Agent 都用 Dify 编排成 Workflow,
        每个 Agent 独立可观测、可重跑、可 A/B 测试。
        """
    )


# ================================================================
# Router
# ================================================================
if page.startswith("🏢"):
    page_jobs()
elif page.startswith("🎯"):
    page_screen()
elif page.startswith("📊"):
    page_history()
else:
    page_agent_design()

# (底部页脚已移除 — 信息已整合到左侧 Sidebar 标题)
