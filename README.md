# 🎯 AI Resume Screener · 简历初筛 Agent

> 一个**多岗位、多格式、可解释、生产级**的简历初筛 Agent 系统。
>
> HR 上传候选人材料(PDF/Word/Excel/视频/作品集链接/ZIP 包) →
> Agent **8 并发** + **6 阶段透明 trace** 处理 → 返回**可解释 4 维评分** +
> 亮点/风险/追问 + 自动入库 + Excel 报告。
>
> **不是 demo,是能落地的产品**。

---

## 💡 这套 Agent 解决的 3 个核心痛点

| HR 真实痛点 | 传统方案 | 本系统 |
|---|---|---|
| 每天几千份简历跑不过来 | 人工逐份看 / 串行处理 | ⚡ **ThreadPool 8 并发**,300 份 20 分钟搞定 |
| PDF/Word/Excel/视频/链接混在一封邮件 | 手动开附件复制粘贴 | 📁 **7 种格式自动解析 + ZIP 自动展开** |
| AI 黑盒打分,HR 不敢用 / 不会解释 | "AI 说他不行" 无法跟业务方对账 | 🔍 **每分都可解释** — evidence + reasoning + 来源溯源 |

---

## ✨ 4 个差异化特色

### ① **HR 在驾驶座** —— AI 是工具,不是黑盒
- 🎚️ 通过阈值可调(没合适人选时降到 70,池子太大时调到 85)
- 📜 自定义匹配规则文本框(必须项 / 加分项 / 减分项)
- 🏢 每个岗位**独立配置** JD / 阈值 / 规则
- 规则**实时注入 LLM 评分提示词**

### ② **Agent 透明 Trace** —— 告别 AI 黑魔法
每个候选人都有 6 阶段可视化:
```
🤖 Plan → 🔧 Tool Selection → 📁 Parse → 🧠 Extract → ⚖️ Match → 💾 Save
```
HR 展开任一候选人 → 切到 **「🤖 Agent Trace」** Tab,看到 Agent 调了哪些工具、提取了多少字、抽出了什么画像、评分依据是什么(毫秒级时间戳)。

### ③ **可解释评分** —— 每个数字都能追溯
- 4 维评分(经验/技能/领域/潜力)各有 **evidence + reasoning + 引用 rubric 哪一档**
- verdict(推荐/可考虑/不推荐)有 **判定依据**(引用分数 + 规则合规 + 关键 risk)
- 亮点带 **🎯 命中哪条 JD** + **📌 来自简历哪段**
- 风险带 **🎯 对照 JD 哪条** + **📌 简历缺什么具体内容**
- 追问带 **🎯 针对哪个 risk** + **💡 想验证什么**

### ④ **生产级而非 Demo**
- ⚡ ThreadPool **8 并发**(可调 1-15)
- 🔄 失败不阻塞 + LLM 调用 **退避重试 3 次**
- 💾 SQLite 持久化所有评估(可追溯/查询/统计)
- 📊 Dashboard:全局通过率 / 各岗位投递量 / 按日趋势
- 📤 一键导出 HR 友好的 **Excel 报告**(不是 JSON)

---

## 🏗 系统架构

```
┌────────────────────────────────────────────────────────┐
│                    Streamlit 4 页面 UI                  │
│   🏢 岗位管理   🎯 候选人初筛   📊 历史与统计   🤖 Agent设计  │
└────────────────────────┬───────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │   Concurrent Pool    │  ThreadPool · 8 workers
              │  ┌──┐ ┌──┐ ┌──┐ ... │  每个 worker = 一个独立 Agent
              │  │A1│ │A2│ │A3│     │  实例处理一个候选人
              │  └─┬┘ └─┬┘ └─┬┘     │
              └────┼────┼────┼──────┘
                   │    │    │
              ┌────▼────▼────▼──────┐
              │      🤖 Agent        │
              │                     │
              │  Plan → Tools →     │
              │  Parse → Extract →  │
              │  Match → Save       │
              └────┬────────────────┘
                   │
        ┌──────────┼───────────┬──────────┬─────────┐
        ▼          ▼           ▼          ▼         ▼
   📄PDFParser  📝Docx     📊Xlsx    🎙Whisper  🌐URLFetch
   📦ZipExtract → 递归用上面工具
        │          │           │          │         │
        └──────────┴───────────┴──────────┴─────────┘
                   ▼
              📝 合并文本
                   ▼
              🧠 LLM-Extract (GPT-5.4 / Claude)
                   ▼ 14 字段结构化画像
              ⚖️ LLM-Match (JD + HR 规则)
                   ▼ 0-100 评分 + evidence + reasoning
              💾 SQLite 持久化
                   ▼
              📊 排序榜 + 评估卡 + Excel 导出
```

---

## 🚀 快速开始

### 装环境
```bash
git clone <this-repo>
cd ai-resume-screener

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 配 API Key
```bash
cp .env.example .env
# 编辑 .env:
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1   (或任意 OpenAI 兼容代理)
# OPENAI_MODEL=gpt-4o-mini                    (或其他模型)
```

### (可选)生成示例候选人池
```bash
python scripts/generate_samples.py
# 生成 5 个岗位 × 15 个候选人 = 75 个独立候选人材料
# 输出到 examples/candidates/{job_slug}/
```

### 启动
```bash
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

---

## 🎬 5 分钟体验

1. **🏢 岗位管理** — 看预置的 5 个岗位(AI Agent / 活动策划 / 海外营销 / 前端 / AI 内容运营)
2. **🎯 候选人初筛** → 选 #1 AI Agent → 👥 批量模式 → 勾选 **"使用本岗位示例候选人池(共 15 人)"**
3. 调右上 **并发数 = 8** → 点 **「批量初筛 + 排序」**
4. 观察 **st.status 实时日志**(8 个 Agent 同时跑)→ 1-2 分钟出排序榜
5. 展开任一候选人 → 切 **「🤖 Agent Trace」** → 看完整 6 阶段思考
6. **📊 历史与统计** — 看 Dashboard / 按日趋势 / 筛选导出 Excel
7. **🤖 Agent 设计** — 看架构图 + 工具清单 + V2 路线图(含视频多模态深度处理)

---

## 📁 项目结构

```
ai-resume-screener/
├── app.py                         # Streamlit 4 页面入口
├── core/
│   ├── db.py                     # SQLite 持久化(jobs + screenings + 统计)
│   ├── parser.py                 # 多格式 Parser(PDF/Word/Excel/Whisper/ZIP/URL)
│   ├── extractor.py              # LLM 简历结构化抽取
│   ├── matcher.py                # JD + HR 规则 语义匹配 + 可解释评分
│   ├── screener.py               # 并发引擎 + Agent 6 阶段 trace
│   ├── llm.py                    # OpenAI 客户端(流式 + 退避重试 + JSON 兜底)
│   └── report.py                 # HR 友好 Excel 报告生成
├── prompts/
│   ├── extract.md                # 抽取 Prompt(14 字段 schema)
│   └── match.md                  # 匹配 Prompt(评分 rubric + evidence 要求)
├── scripts/
│   └── generate_samples.py       # 75 个示例候选人生成器
├── examples/
│   ├── sample_jd.md              # 示例 JD
│   └── candidates/
│       ├── ai_agent/             # 15 人 × {PDF简历, Word自荐, zip}
│       ├── event_planning/       # 15 人 ...
│       ├── overseas_marketing/   # 15 人 ...
│       ├── frontend/             # 15 人 ...
│       └── ai_content/           # 15 人 ...
├── data/
│   └── screener.db               # SQLite (自动创建)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| **前端** | Streamlit 1.57+(4 页面架构) |
| **后端** | Python 3.12 |
| **LLM** | OpenAI 协议兼容(默认 gpt-4o-mini,可换 Claude / DeepSeek / 国产模型) |
| **并发** | ThreadPoolExecutor + as_completed |
| **解析** | pypdf / python-docx / openpyxl / Whisper / BeautifulSoup |
| **持久化** | SQLite(无依赖,开箱即用) |
| **报告** | openpyxl(HR 友好样式 + 冻结表头) |

---

## 🚀 V2 路线图

> V1 完成后,与一线 HR / 技术领导交流,沉淀出**真实落地视角**的 V2 优先级。
> 务实功能优先,花哨概念后置。

### 🎯 一线反馈(优先级最高)

> 📅 反馈时间:2026-05-21 16:00 左右 · 来源:行业内同行

直击"AI 工具能否被信任 + 被持续使用"的核心,三条务实建议:

#### 1. 场景重定位:领导直招路径

- **问题**:HR 批量筛简历是表层场景,真正的痛点是**技术领导想自助招人**
- **流程**:Boss 批准招人需求 → 领导直招(跳过 HR 在筛人环节的瓶颈)
- **AI 价值定位**:
  - ✅ 已做:LLM 分析需求 + 制定招聘标准
  - ⏳ 待做:领导侧的"标准可调 + 规则可加 + 一键直招"工作流

#### 2. 字段级溯源(可信度关键)

- **问题**:大家不敢完全放权给 AI,因为"AI 说得很专业,但没有依据"
- **现状**:V1 的 `evidence` 字段是文本描述,LLM 给了证据但**无法点击验证**
- **V2 目标**:每个评分点 → **可点击 → 跳转到简历原文位置高亮**
- **意义**:这是"AI 推荐"被信任的硬门槛,做到了才有人敢真的用

#### 3. JD 模板库 + 规则继承

- **问题**:每个岗位 HR 都手写规则,**1 年后还在重复劳动**
- **V2 目标**:
  - **规则继承**:同岗位上次配的规则下次自动复用
  - **行业模板**:同行业的标准模板一键导入(酒店 / 跨境电商 / 制造业...)
- **意义**:把"工具"变"资产" —— 用得越久,沉淀越多,壁垒越高

> 💡 同行原话警告:**"别堆花哨概念,踏实做务实功能"** —— 画像分析、多模态花活那些,
> 远不如"溯源 + 模板库"对 HR / 领导真买单。

---

### 🧪 探索向(优先级次之)

#### 视频材料的深度处理
当前 V1 视频仅做 Whisper 音频转写 — 适合**自我介绍/口播**,但**作品集 demo /
活动现场 / PPT 演讲**会丢失大量视觉信息:
- ffmpeg 抽关键帧 + Vision LLM(GPT-4V / Claude-3 Sonnet)看图
- 视频类型分类 Agent(自我介绍 / 作品 / 活动 / 演讲)
- 综合多模态(画面 + 音频 + 字幕)再喂给 Extractor

#### 多 Agent 协作(可接 Dify 编排)
- **采集 Agent** — 监听 HR 邮箱(IMAP)自动归类
- **抽取 Agent** — 当前的 LLM-Extract
- **匹配 Agent** — 当前的 LLM-Match
- **背调 Agent** — 自动搜索候选人公开信息(GitHub / 知乎)
- **HR 反馈 Agent** — 收集 HR 标记 → 微调匹配策略(RLHF-lite)

#### 其他
- [ ] 多语言简历(英/日/韩)统一画像
- [ ] 候选人去重 + 跨岗位推荐
- [ ] 接入 IMAP / Outlook API 真实邮件触发

---

## 📝 License

MIT
