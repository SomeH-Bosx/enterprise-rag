# Enterprise RAG Agent Development Plan


## 项目目标

一句话说明：

基于 LangChain + Ollama 构建企业级知识库问答系统，
融合 Router、Hybrid Retrieval、Reranker，
提升复杂场景下的检索准确性。


---

# Phase 0 项目初始化

目标：

建立可维护工程结构。


## Tasks

- 创建项目目录
- 配置Python环境
- 创建requirements.txt
- 配置.env
- 添加日志系统


## 输出

完成：


src/
config/
logs/
requirements.txt


## 验收标准

- 项目可以启动
- 配置可以读取
- 日志正常输出



---

# Phase 1 基础RAG MVP


目标：

跑通完整RAG闭环。


## 数据流

PDF
↓
Loader
↓
Splitter
↓
Embedding
↓
Vector DB
↓
Retriever
↓
LLM
↓
Answer



## Tasks

### 1. 文档处理

实现：

- PDF上传
- 文档解析
- chunk切分


### 2. 向量化

实现：

- embedding模型调用
- 向量保存


### 3. 检索问答

实现：

- similarity search
- context拼接
- Ollama生成回答


## 验收标准

用户上传一个PDF：

可以回答PDF中的问题。


---

# Phase 2 RAG增强


目标：

提升检索质量。


## 增加Reranker


原因：

向量检索召回存在噪声。


实现：


Query
↓
Vector Search(top20)
↓
Reranker
↓
Top5
↓
LLM



验收：

对比加入reranker前后的回答质量。



---

# Phase 3 Query Router


目标：

支持不同类型问题处理。


设计：


User Query

↓

Router

↓

知识查询
数据分析
闲聊

↓

不同Chain



验收：

不同问题进入不同流程。



---

# Phase 4 工程化


目标：

形成可展示项目。


增加：

- FastAPI
- 前端界面
- Docker
- README
- Demo截图



---

# Phase 5 Evaluation


目标：

证明系统有效。


增加：

- Recall测试
- RAGAS评估
- 典型问题测试集


---

# Phase4 Enhancement — 续作路线图（未完成 Steps）

> 对照进度：[`progress.md`](progress.md)  
> 主线 Phase1–Phase4 已完成；以下为 **Phase4 Enhancement** 剩余工作。  
> 规则：一次只做一个 Step；完成后停止，等待用户下一步指令。

## 当前进度快照

| Step | 内容 | 状态 |
| --- | --- | --- |
| Step1 | Knowledge Workspace UI + Trace + UI 打磨 | **完成** |
| Step2 | 多格式 Document Loader（含 .ppt/.doc 显式 Office 转换） | **完成** |
| Step3 | Conversation Memory | **完成** |
| Step3.5 | Query Rewrite / Hybrid | **完成** |
| **Step3.6** | 表格序列化 + OCR | **完成** |
| Step4 | Session 模型配置管理 | **未开始 ← 下一个** |
| （之后） | Phase5 Evaluation | 未开始 |

**禁止越界：** 不实现 Agent / Multi-Agent / Web Search / SQL Agent / 知识图谱（除非用户明确要求）。


## Step3.5 — Query Rewrite / Hybrid（已完成）

### 目标

提升「换问法仍能召回」的鲁棒性；不破坏现有 Router → Retriever → Reranker → LLM 主链。

### 已确认产品决策

- **Hybrid（BM25）：本 Step 要实现，但默认关闭**（`USE_BM25=false` 或等价开关）；演示时可手动开启。
- Query Rewrite：检索用改写问；**回答仍用用户原问**（+ Memory 历史）。
- 完整 LLM Query Rewrite 放本 Step；Step3 已有的「近期用户问拼接」可保留为 rewrite 失败时的轻量回退。

### 计划实现

1. 独立 Query Rewrite 模块（规则 / 轻量 LLM；失败回退原问）
2. Hybrid：Dense + BM25 合并候选 → 再 Reranker（默认关）
3. 接线：`Current Query (+ Memory) → Rewrite → Dense[/Hybrid] → Rerank → Prompt(原问) → LLM`
4. Trace 展示：原问、改写问、是否 Hybrid
5. `.env` 开关 + 测试 + 更新 `progress.md`

### 验收

- 换问法场景检索更稳（相对仅 dense + 原问）
- Hybrid 默认关；打开后链路可跑通
- 未改坏 Memory / Upload / Trace
- 完成后停止，不自动进入 Step3.6


## Step3.6 — 表格序列化 + OCR（已完成）

### 目标

增强文档解析：结构化表格文本化；扫描件/图片页 OCR（按需触发）。

### 约束

- 不替代现有 Loader 架构，以扩展点接入
- OCR 依赖可选用，避免默认强绑超重模型（实现时与用户确认引擎）

### 验收

- 含表 PDF/Office 抽到可用文本结构（如 Markdown 表）
- 无文本页可走 OCR 或明确跳过并打日志
- 完成后停止


## Step4 — Session 模型配置管理（下一个）

### 目标

UI 可改 LLM / Embedding / Reranker；**仅影响当前 session**，不写回 `.env`。

### 约束

- 配置来源仍是 `.env` + Settings 作为默认
- 禁止在业务代码硬编码 Key；禁止 UI 持久化密钥到仓库文件

### 验收

- Session 覆盖生效；刷新/Clear 策略与用户确认一致
- 完成后可进入 Phase5 或项目展示优化（由用户指定）


## 新对话续作 Prompt（复制到新 Chat 使用）

将下面整段作为新对话的第一条用户消息：

```text
你接手仓库 enterprise-rag（企业级 RAG）。先不要改代码。

请先阅读并核对：
1) docs/development_plan.md — 尤其是「Phase4 Enhancement — 续作路线图」
2) docs/progress.md — 当前已完成 / 未完成状态
3) README.md 与关键代码：apps/api/main.py、apps/web/streamlit_app.py、src/services/qa_service.py、src/memory/、src/ingestion/、src/reranker/、src/router/

然后输出简短的 Current Status：
- 已完成到哪一步
- 下一个该做的 Step 是什么（以 development_plan.md 为准）
- 该 Step 的目标、约束、验收（复述计划，勿擅自扩大范围）

开发规则：
- 一次只做 development_plan.md 中「下一个」未完成 Step
- Hybrid（BM25）在 Step3.5：要实现但默认关闭，演示可手动开（已确认）
- 不破坏已有 RAG Pipeline；小步修改；不做 Agent/Web Search/SQL/知识图谱
- 完成后更新 docs/progress.md，然后停止，等待我的下一步指令

现在：先做状态 review。等我确认「可以开始 StepX」之后再改代码。
```
