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

# Phase4 Enhancement 

> 对照进度：[`progress.md`](progress.md)  
> 主线 Phase1–Phase4 与 Enhancement Step1–Step4 已完成；**Phase5 Evaluation 已完成**。  
> 其余见 **Future Work**（含 Phase6）。  
> 规则：一次只做一个 Step/Phase 切片；完成后停止，等待用户下一步指令。

## 当前进度快照

| Step / Phase           | 内容                                                         | 状态            |
| ---------------------- | ------------------------------------------------------------ | --------------- |
| Step1–Step4            | Enhancement（UI/Loader/Memory/Rewrite/Hybrid/OCR/Session 本地模型） | **完成**        |
| Phase5                 | Evaluation（Recall / RAGAS-style / 测试集）                  | **完成**        |
| UI 会话开关 / 侧栏体验 | Dense                                                        | BM25            |
| Phase6                 | DashScope 云 LLM + 云 Embedding + Session API Key            | **Future Work** |




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


## Step4 — Session 模型配置管理（已完成）

### 目标

UI 可改 LLM / Embedding / Reranker；**仅影响当前 session**，不写回 `.env`。

### 约束

- 配置来源仍是 `.env` + Settings 作为默认
- 禁止在业务代码硬编码 Key；禁止 UI 持久化密钥到仓库文件

### 验收

- Session 覆盖生效；刷新/Clear 策略与用户确认一致
- 完成后进入 **Phase5 Evaluation**（再后为 Phase6 云模型）；由用户指定是否先做展示优化



---

# Phase 5 Evaluation


目标：

证明系统有效。


增加：

- Recall测试
- RAGAS评估（本仓库：RAGAS-style 轻量指标，见 `src/eval/ragas_lite.py`）
- 典型问题测试集（`data/eval/questions.json`）

## 如何运行

见 [`docs/eval.md`](eval.md)。

```bash
python -m apps.cli.main ingest-dir data/samples
python -m apps.cli.main eval
```

报告输出：`evaluation/phase5_report.md` / `evaluation/phase5_report.json`


---



# Phase 6 Cloud Models & Session API Key（DashScope）

> 来源：Step4 验收后的产品缺口（仅能切本地 Ollama；无 UI 配 Key）。  
> **排在 Phase5 Evaluation 之后 · 当前 = Future Work。**  
> 规则：完成 Phase5 并由用户确认后，再开始本 Phase；一次只做一个可验收切片（实现时再拆 Step）。  
> 同属 Future Work 的还有：多语言回答一致性、Query 改写策略优化（与 Memory 叙事独立）、chunk 切分策略对比、置信度计算与展示优化（详见上方 Future Work 列表与 README §11）。




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



## 目标

在保留本地 Ollama 路径的前提下，支持 **DashScope 云端 LLM + 云端 Embedding**，并提供 **Session 级 API Key 配置入口**（内存，不写 `.env` / 不进仓库）。

## 已确认产品决策

| 项               | 决策                                                         |
| ---------------- | ------------------------------------------------------------ |
| 排期             | **Phase6**，放在 **Phase5 Evaluation 之后**                  |
| 云厂商           | **优先 DashScope**                                           |
| 范围             | **包含云 Embedding**（不仅云 LLM）                           |
| Clear chat × Key | **A：Clear chat 保留 session Key**（与「Clear 保留模型覆盖」一致） |
| 浏览器刷新       | Session Key 与 session 模型覆盖一并丢失（回 `.env` 默认）    |
| Key 持久化       | **禁止**写入 `.env`、仓库文件、长期磁盘（仅当前浏览器 session 内存；服务端仅请求级使用） |

## 计划能力

1. UI：Provider 切换（本地 Ollama ↔ DashScope）；模型名；**API Key 输入框**（不明文写回磁盘）
2. Session：云 LLM 用于生成 /（按需）Rewrite；云 Embedding 用于本 session 入库与检索绑定
3. Key 解析顺序（建议）：请求/session Key → 否则 `.env` 中已有 `DASHSCOPE_API_KEY` → 否则明确失败提示（不静默编造）
4. 换云 Embedding 后：**提示并要求重新上传/入库**（与 Step4 embed 限制一致）
5. Trace / 响应：展示 provider + 模型；**不回显完整 API Key**
6. 测试 + 更新 `progress.md`；不做 Agent / Web Search / SQL / 知识图谱

## 约束

- 不破坏现有 Ollama RAG 主链；默认仍可纯本地运行
- 禁止业务代码硬编码 Key；禁止 UI 把 Key 写入仓库
- 小步修改；实现前可再拆 Step（如 6.1 Key+LLM，6.2 Embedding）

## 验收

- UI 可选 DashScope LLM，填 session Key（或使用 `.env` Key）后能完成问答
- UI 可选 DashScope Embedding，重新入库后检索可用
- Clear chat：**保留** session Key 与模型覆盖；浏览器刷新后 Key 丢失
- Key 不出现在 git 跟踪文件、日志明文、Trace 明文
- 完成后停止

# Future Work

1. **Phase6**：云端 LLM / Embedding + Session API Key（Clear chat 保留 Key）  
2. **减少不同语言语料的回答差异**  
3. **优化 Query 改写策略**，并在产品叙事与 UI 上与 Memory 进一步独立  
4. **尝试使用并对比不同的 chunk 切分策略**  
5. **优化置信度的计算与展示**，使其更合理  
6. **高级**：Agent / Multi-Agent / Web Search / SQL Agent / 知识图谱。
