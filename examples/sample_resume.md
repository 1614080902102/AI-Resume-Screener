# 张博文 - AI 应用开发工程师

> ⚠️ 本文档为系统 demo 使用的**虚构候选人**,所有信息均为示例,
> 与任何真实人物无关,仅用于展示初筛 Agent 的匹配能力。

- 性别:男 | 年龄:27 | 现居:深圳
- 电话:138-0000-0000 | 邮箱:demo.candidate@example.com
- 工作年限:4 年

## 教育经历
- 2017.09 - 2021.06 | 中山大学 | 软件工程 | 本科

## 工作经历

### 2023.05 - 至今 | 某 AI 创业公司 | AI 应用工程师
- 负责公司 ToB 知识库产品从 0 到 1 的研发,服务 30+ 企业客户
- 主导多模型接入(GPT/Claude/DeepSeek/通义千问)与成本路由策略
- 搭建公司内部的 RAG 评估体系,持续监控召回精度

### 2021.07 - 2023.04 | 某互联网公司 | Python 后端工程师
- 负责广告投放系统的接口开发与 ETL 数据管道
- FastAPI + PostgreSQL 构建高并发后端,日均请求 500w+
- 参与 SQL 性能优化,慢查询 P95 从 800ms 降到 120ms

## 项目经验

### 项目一:企业级 RAG 知识库平台(2024.01 - 至今)
- **角色**:技术负责人
- **技术栈**:FastAPI、LangChain、BGE-M3、PostgreSQL + pgvector、Dify
- **背景**:多家 SaaS 客户需要快速搭建专属知识库,人工配置成本高
- **方案**:
  - 多租户架构,客户上传文档后自动分片、embedding、入库
  - 中文 embedding 调优:对比 BGE-M3 / m3e-base / text-embedding-3-large,
    最终选定 BGE-M3,top-5 召回率从 65% 提升至 87%
  - 加 Rerank 二次排序,top-3 命中率再提升 8 个百分点
- **成果**:服务 30+ 企业客户,平均部署时间从 3 天降至 4 小时

### 项目二:跨境电商商品爬虫与 AI 内容生成(2023.08 - 2023.12)
- **角色**:独立全栈开发
- **技术栈**:Scrapy、Playwright、Dify、GPT-4
- **背景**:某跨境电商客户需爬取海外竞品价格 + 自动生成营销文案
- **方案**:
  - Scrapy + Playwright 处理 JS 渲染电商站点
  - 代理 IP 池 + Cookie 池 + 频控随机化绕过反爬
  - LLM 抽取商品结构化字段 + 自动生成多语言营销文案(英/日/西)
- **成果**:日均爬取 20w+ SKU,营销文案 CTR 提升 18%

### 项目三:多模型成本路由网关(2024.06 - 2024.09)
- **角色**:核心开发
- **技术栈**:FastAPI、Redis、Prometheus
- **背景**:公司多 AI 应用直连模型 API,成本失控、缺监控
- **方案**:
  - 统一 OpenAI 协议网关,接入 6 个模型(GPT/Claude/DeepSeek/通义/Kimi/Ollama)
  - 按任务复杂度路由(简单分类走便宜模型,复杂推理走 GPT-4)
  - Prompt Cache + 上下文裁剪 + 接口级限流
- **成果**:整体模型调用成本下降 42%,可观测性显著提升

## 技能栈
- **语言**:Python(4 年)、JavaScript/Vue、SQL
- **后端**:FastAPI、PostgreSQL、pgvector、Redis、Docker
- **AI**:RAG、Embedding 调优、Agent 工具链、MCP 协议、
  Dify、LangChain、多模型路由(GPT/Claude/DeepSeek/通义/Ollama)
- **爬虫**:Scrapy、Playwright、反爬绕过(代理池/UA 轮换/Cookie 池)
- **工程**:Ruff、Black、pytest、pre-commit、GitHub Actions、Prometheus

## 个人亮点
- 完整 AI 应用链路经验(爬虫 → 数据处理 → RAG → Agent → 触达)
- 强 ROI 思维,做项目先问"为客户带来多少可量化的价值"
- 工程化能力扎实,熟悉测试、监控、CI/CD
- 学习能力强,Dify / MCP 协议出来后第一周就上手并产出 demo

## 作品集
- GitHub: github.com/example-candidate
- 技术博客: techblog.example.com
