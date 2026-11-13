# 高升（GaoSheng）AI 接口自动化测试框架

---

## 一、项目简介

本项目是针对 **高升AI 智能助手接口** 的自动化测试框架，严格遵循用户偏好的**四层自动化架构**：

```
gs_api/
├── base/      # 公共基础层：配置、HTTP 客户端、Selenium 基类、日志、断言、数据加载
├── page/      # 接口 / UI 操作层：会话、聊天、历史会话、知识库、Web UI
├── script/    # pytest 测试脚本层：7 套测试脚本 + conftest 共享 fixtures
└── report/    # 报告层：Allure 报告管理 + Ragas AI 回答质量评估
```

### 设计理念

| 特性 | 说明 |
|---|---|
| **四层架构** | base → page → script → report 清晰分层，便于维护与扩展 |
| **数据驱动** | 采用 **YAML + CSV** 双格式管理测试数据，符合用户数据驱动偏好 |
| **流式健壮性** | 流式接口量化 **首包延迟 TTFT**，并在 **超时 / 断网** 场景自动重试（次数可配），覆盖数据分片完整性 |
| **AI 容错** | 大模型输出不稳定时，**嵌套对象等畸形报文** 经宽容解析（`flexible_text`）拍平为字符串，保证断言可用、前端渲染不崩溃 |
| **AI 质量评估** | 深度集成项目原有的 **Ragas** 框架，对高升AI回答做 Faithfulness / AnswerRelevancy / ContextRecall 多维度评估 |
| **品牌一致性** | 所有用例统一断言「高升」品牌词 |
| **Allure 报告** | 自动生成环境信息、缺陷分类、Ragas 评估明细、截图等富媒体附件 |
| **Selenium 辅助** | base 层提供完整的 Selenium 公共方法，支撑后续 Web UI 冒烟测试 |

---

## 二、目录结构

```
gstest/
├── gs_api/                              # ★ 高升AI测试框架根目录
│   ├── __init__.py                      #   框架元信息 + 各层统一导出
│   ├── base/                            #   base 层：公共基础封装
│   │   ├── config.py                    #     全局配置管理（默认值 → YAML → 环境变量）
│   │   ├── http_client.py               #     HTTP 客户端 + 流式 SSE（1001/1002/1003）解析
│   │   │                                #       └ StreamMetrics：TTFT 首包延迟 / 超时与断网重试
│   │   ├── selenium_base.py             #     ★ Selenium 公共方法基类
│   │   ├── logger.py                    #     统一日志（控制台 + 文件 + Allure 挂载）
│   │   ├── assertions.py                #     通用断言集合 + Ragas 阈值断言
│   │   ├── data_loader.py               #     ★ YAML / CSV 数据驱动加载器
│   │   ├── deserializer.py              #     ★ 宽容文本反序列化（嵌套对象拍平，AI 输出兜底）
│   │   └── __init__.py
│   ├── page/                            #   page 层：接口与 UI 操作封装
│   │   ├── session_page.py              #     会话接口（新建 / 热门问题）
│   │   ├── chat_page.py                 #     聊天接口（流式 / 停止 / 文本 / 模版）
│   │   ├── history_page.py              #     历史会话（详情 / 列表 / 更新标题 / 删除）
│   │   ├── embedding_page.py            #     知识库向量（embedding CRUD / 搜索）
│   │   ├── web_page.py                  #     ★ 高升AI Web UI 辅助操作
│   │   └── __init__.py
│   ├── report/                          #   report 层：报告 + AI 质量评估
│   │   ├── allure_manager.py            #     Allure 环境、分类、HTML 报告生成
│   │   ├── ragas_evaluator.py           #     ★ Ragas 多维度评估（阈值断言 + DataFrame 输出）
│   │   └── __init__.py
│   ├── script/                          #   script 层：pytest 自动化脚本
│   │   ├── conftest.py                  #     ★ 共享 fixtures + pytest 生命周期钩子
│   │   ├── test_01_session.py           #     一、会话接口测试
│   │   ├── test_02_chat.py              #     二、聊天接口测试（流式 TTFT/重试 + 容错 + Ragas）
│   │   ├── test_03_history.py           #     三、历史会话测试（CRUD 闭环）
│   │   ├── test_04_embedding.py         #     四、知识库向量接口测试
│   │   ├── test_05_ragas_quality.py     #     ★ 五、Ragas AI 质量评估套件（含长文档检索 ContextRecall）
│   │   ├── test_06_web_ui_smoke.py      #     六、Web UI 冒烟（显式等待，无 sleep，默认跳过）
│   │   ├── test_07_mock_performance.py  #     ★ 七、Mock 大模型并发性能（TPS / 平均 TTFT / 限流 429）
│   │   └── __init__.py
│   ├── config/
│   │   └── config.yaml                  # 全局配置文件（可被环境变量覆盖）
│   └── data/
│       ├── test_data.yaml               # ★ YAML 测试数据（会话 / 课程咨询 / FAQ / 向量）
│       └── qa_data.csv                  # ★ CSV 问答对（数据驱动 + Ragas 批量评估）
│
├── src/                                 # 原有 RAG 系统（被 Ragas 复用为上下文检索）
│   ├── rag_system.py
│   ├── llm.py
│   ├── embeddings.py
│   └── vector_store.py
├── data/sample_docs/                    # 原有知识库文档（Ragas Context 使用）
├── pytest.ini                           # pytest markers / addopts 配置（含 --clean-alluredir）
├── requirements.txt                     # 项目依赖（新增 allure-pytest / selenium / pyyaml / pytest-xdist 等）
├── Jenkinsfile                          # ★ Jenkins 声明式流水线（CI 闭环）
├── .env.example                         # 环境变量示例
├── run_gs_api_tests.ps1                 # Windows PowerShell 一键运行
└── run_gs_api_tests.sh                  # macOS / Linux bash 一键运行
```

---

## 三、接口覆盖清单

对照 **aitj v1.0.0 接口文档**，当前 gs_api 脚本层已覆盖 15 个接口：

| 编号 | 模块 | 方法 · 路径 | 测试脚本 |
|---|---|---|---|
| 1  | 会话 | `POST /ais/session` 新建会话 | [test_01_session.py](gs_api/script/test_01_session.py) |
| 2  | 会话 | `GET  /ais/session/hot` 热门问题 | [test_01_session.py](gs_api/script/test_01_session.py) |
| 3  | 聊天 | `POST /ais/chat` 流式聊天（SSE 1001/1002/1003） | [test_02_chat.py](gs_api/script/test_02_chat.py) |
| 4  | 聊天 | `POST /ais/chat/stop` 停止生成 | [test_02_chat.py](gs_api/script/test_02_chat.py) |
| 5  | 聊天 | `POST /ais/chat/text` 文本聊天（不保存） | [test_02_chat.py](gs_api/script/test_02_chat.py) |
| 6  | 聊天 | `GET  /ais/chat/templates` 模版列表 | [test_02_chat.py](gs_api/script/test_02_chat.py) |
| 7  | 历史 | `GET  /ais/session/{sessionId}` 会话详情 | [test_03_history.py](gs_api/script/test_03_history.py) |
| 8  | 历史 | `GET  /ais/session/history` 历史会话列表 | [test_03_history.py](gs_api/script/test_03_history.py) |
| 9  | 历史 | `PUT  /ais/session/history` 更新标题 | [test_03_history.py](gs_api/script/test_03_history.py) |
| 10 | 历史 | `DELETE /ais/session/history` 删除会话 | [test_03_history.py](gs_api/script/test_03_history.py) |
| 11 | 知识库 | `GET    /ais/embedding` 文本转向量 | [test_04_embedding.py](gs_api/script/test_04_embedding.py) |
| 12 | 知识库 | `POST   /ais/embedding` 保存文本 | [test_04_embedding.py](gs_api/script/test_04_embedding.py) |
| 13 | 知识库 | `DELETE /ais/embedding` 删除文本 | [test_04_embedding.py](gs_api/script/test_04_embedding.py) |
| 14 | 知识库 | `GET    /ais/embedding/search` 内容搜索 | [test_04_embedding.py](gs_api/script/test_04_embedding.py) |
| 15 | 知识库 | `GET    /ais/embedding/search/all` 搜索全部 | [test_04_embedding.py](gs_api/script/test_04_embedding.py) |

---

## 四、快速开始

### 4.1 环境准备

```bash
# 1. 进入项目目录
cd gstest

# 2. 推荐使用 Python 3.10+ 创建虚拟环境
python -m venv .venv

# 3. Windows 激活
.venv\Scripts\Activate.ps1
#    或 macOS/Linux
source .venv/bin/activate

# 4. 安装依赖（新增 allure-pytest / selenium / pyyaml / pandas / pytest-xdist 等）
pip install -r requirements.txt
```

### 4.2 环境变量配置

复制 `.env.example` 为 `.env` 并填写：

| 变量 | 必须 | 说明 |
|---|---|---|
| `AIS_TOKEN` | 部分接口需要 | 高升AI登录 token，通过 `Authorization` header 传递 |
| `DEEPSEEK_API_KEY` | **Ragas 需要** | 评估 LLM 的 DeepSeek API Key（用于 Faithfulness 等指标） |
| `DEEPSEEK_BASE_URL` | 可选 | 默认 `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 可选 | 默认 `deepseek-chat` |
| `EMBEDDING_API_KEY` | Ragas 推荐 | 硅基流动/SiliconFlow Embedding Key（用于 AnswerRelevancy 语义相似度） |
| `EMBEDDING_BASE_URL` | 可选 | 默认 `https://api.siliconflow.cn/v1` |
| `EMBEDDING_MODEL` | 可选 | 默认 `Qwen/Qwen3-Embedding-0.6B` |

或直接修改 [gs_api/config/config.yaml](gs_api/config/config.yaml)（YAML 优先级低于环境变量）。

### 4.3 Allure 命令行安装（可选，用于生成 HTML 报告）

- Windows：`scoop install allure` 或从 <https://allurereport.org/docs/getting-started-installation/> 下载
- macOS：`brew install allure`
- Linux：`sudo apt-get install allure`

---

## 五、运行测试

### 5.1 一键运行（推荐）

**Windows PowerShell：**
```powershell
# 冒烟用例（会话+聊天+历史+Ragas），默认生成 Allure 结果
.\run_gs_api_tests.ps1

# 全量用例（含向量 / Web UI）
.\run_gs_api_tests.ps1 -All

# 运行后自动用浏览器打开 Allure HTML
.\run_gs_api_tests.ps1 -OpenReport

# 自定义 markers
.\run_gs_api_tests.ps1 -Markers "session and chat"
```

**macOS / Linux bash：**
```bash
bash run_gs_api_tests.sh         # 冒烟
bash run_gs_api_tests.sh all     # 全量
MARKERS="ragas" bash run_gs_api_tests.sh   # 仅跑 Ragas
```

### 5.2 直接使用 pytest

```bash
# 冒烟（含 Ragas AI 质量评估）
pytest gs_api/script -m smoke -v \
       --alluredir gs_api/report/output/allure_results \
       --clean-alluredir

# 仅跑会话接口
pytest gs_api/script/test_01_session.py -v

# 仅跑聊天接口（含流式 TTFT / 断网重试用例）
pytest gs_api/script/test_02_chat.py -v

# 仅跑 Ragas AI 质量评估（需要 DEEPSEEK_API_KEY）
pytest gs_api/script/test_05_ragas_quality.py -v -s

# 跑全量（不做任何过滤）
pytest gs_api/script -v

# 仅跑 Web UI 用例（无头模式，CI 默认）
pytest gs_api/script -m ui --headless -v

# 仅跑 Mock 并发性能 / 限流用例（离线、零 Token 成本）
pytest gs_api/script -m performance -v -s

# 冒烟用例并发加速（需 pytest-xdist）
pytest gs_api/script -m smoke -n auto -v

# 生成 Allure HTML 报告
allure generate gs_api/report/output/allure_results \
       -o gs_api/report/output/allure_html --clean

# 直接用浏览器打开 Allure 报告
allure open gs_api/report/output/allure_html
```

> 自定义参数：`--headless` 强制无头运行、`--no-headless` 强制显示浏览器（本地调试）。

### 5.3 pytest markers 清单

| marker | 说明 | 覆盖脚本 |
|---|---|---|
| `smoke` | 冒烟测试（核心必跑） | test_01 / test_02 / test_03 / test_05 |
| `api` | 接口测试（HTTP / SSE，全部接口脚本） | test_01 ~ test_05 / test_07 |
| `ui` | Web UI 测试（Selenium，CI 流水线使用） | test_06_web_ui_smoke.py |
| `session` | 会话接口 | test_01_session.py |
| `chat` | 聊天接口 | test_02_chat.py |
| `history` | 历史会话接口 | test_03_history.py |
| `embedding` | 知识库向量接口 | test_04_embedding.py |
| `ragas` | **Ragas AI 回答质量评估** | test_02 / test_05_ragas_quality.py |
| `performance` | 并发性能与限流（Mock 大模型） | test_07_mock_performance.py |
| `webui` | Web UI 冒烟（默认跳过） | test_06_web_ui_smoke.py |

### 5.4 流式接口健壮性测试（首包延迟 + 超时重试）

针对大模型流式响应的不确定性，`test_02_chat.py` 提供两条专项用例：

| 用例 | 场景 | 断言要点 |
|---|---|---|
| `test_chat_stream_ttft_below_threshold` | 真实流式请求 | **首包延迟 TTFT < 3000ms**（阈值可配），同时校验事件非空、拼接回答非空 |
| `test_chat_stream_retry_on_connection_error` | Mock 断网（`ConnectionError`） | 重试 2 次共 3 次请求、每次失败打印 WARNING、重试后仍采集到 TTFT、**跨分片拼接内容完整无丢失** |

指标采集由 base 层的 `StreamMetrics` 统一完成，可通过 `ChatPage.last_stream_metrics` 读取：

```python
full_text, events = chat_page.chat_stream_full("解释什么是RAG", session_id)
m = chat_page.last_stream_metrics
print(m.ttft_ms, m.first_chunk_ms, m.total_ms, m.attempts, m.event_count)
```

相关配置（[gs_api/config/config.yaml](gs_api/config/config.yaml) → `api`）：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `stream_retries` | `2` | 首包前（Timeout / 断网）的重试次数 |
| `stream_retry_delay` | `0.5` | 重试间隔基数（秒），实际等待 = 基数 × 第 n 次 |
| `ttft_threshold_ms` | `3000` | 首包延迟阈值（毫秒），用于用例断言 |

> 说明：仅在「尚未产出任何事件」时触发重试；若流中已推送部分内容再中断，直接抛出异常，
> 避免重复推送造成前端渲染重复。TTFT 与重试指标会自动挂载到 Allure 用例附件。

### 5.5 AI 容错与边界测试（异常反序列化兜底）

大模型输出不稳定，「本该是字符串」的 `content` / `eventData` 可能变成嵌套对象或数组。
base 层提供宽容解析器 [gs_api/base/deserializer.py](gs_api/base/deserializer.py)：

```python
from gs_api.base import flexible_text

flexible_text("纯文本")                                  # -> "纯文本"（幂等，正常报文零影响）
flexible_text({"text": "高升", "meta": {"n": "AI"}})      # -> "高升AI"（嵌套对象递归拍平）
flexible_text(["高升", {"n": "AI"}])                     # -> "高升AI"（数组按顺序拍平）
flexible_text(None)                                      # -> ""
```

对流式分片与文本聊天回答均走该兜底逻辑，对应两条用例（均在 `test_02_chat.py`）：

| 用例 | 畸形 Mock 报文 | 断言要点 |
|---|---|---|
| `test_chat_text_tolerant_deserialization` | `data` = `{"text":"高升","meta":{"brand":{"name":"AI"}}}`（嵌套字典） | 拦截 `requests.Session.request` 注入报文；`code == 200`；拍平结果为 `str` 且等于 `高升AI`；无结构符号残留（前端不崩溃）；`chat_text_get_answer` 端到端返回纯字符串；字符串输入拍平幂等 |
| `test_chat_stream_tolerant_deserialization` | 分片 `eventData` 为嵌套字典 | 分片全部拍平为 `str`，事件序列 `1001/1001/1002` 完整，拼接内容为 `高升AI流式` |

> 拦截点说明：非流式请求统一走 `requests.Session.request`，流式请求走 `requests.Session.post`，
> 因此 mock 分别 patch 这两个方法，直接以 `unittest.mock.patch` 在真实 HTTP 边界注入报文。

### 5.6 流式 UI 自动化（弃用 time.sleep，改用显式等待）

Web UI 用例全面弃用 `time.sleep`，改用 `WebDriverWait` + 自定义 `expected_conditions`
（位于 [gs_api/base/selenium_base.py](gs_api/base/selenium_base.py)），从根本上消除「等待时长拍脑袋」带来的偶发失败：

| 自定义条件 | 判定逻辑 |
|---|---|
| `AnswerRenderComplete` | 回答气泡文本非空，且「停止生成」按钮消失 **或**「复制」按钮出现 → 视为渲染完成，返回最终文本 |

核心用例 `test_chat_bubble_render_complete`（`test_06_web_ui_smoke.py`）流程：

```python
web_page.ui_new_session()                       # 新建会话（内部为 wait_present，无 sleep）
answer = web_page.ui_send_question(question)    # 发送后等待 AnswerRenderComplete
answer = answer.strip()                         # 提取「最终的全部文本」再断言
```

断言要点：最终文本非空、Allure 挂载回答文本与失败截图。

### 5.7 Mock 大模型并发性能测试（TPS / 平均 TTFT / 限流 429）

`test_07_mock_performance.py` 用 `unittest.mock` 在 HTTP 边界拦截「第三方大模型」调用，
直接返回瞬间响应的假 SSE 数据，使压测**可离线、可重复、零 Token 成本**；
再用 `concurrent.futures.ThreadPoolExecutor` 模拟并发：

| 用例 | 场景 | 断言要点 |
|---|---|---|
| `test_concurrent_stream_throughput` | 10 并发 / 40 请求，Mock 秒回 | 分片拼接完整、事件数一致；**TPS ≥ 20 req/s**；**平均 TTFT ≤ `api.ttft_threshold_ms`** |
| `test_concurrent_rate_limit_429` | 上游网关并发在途上限 `limit=2`，30 并发 | **限流被触发**（`rejected > 0`）；客户端感知 429 次数 == 网关拒绝次数；成功数 == 总数 − 被限流数；异常含 `429` |

指标（总耗时 / TPS / 平均与最大 TTFT）会以文本附件挂载到 Allure 报告。

> 拦截点：并发流式请求走 `requests.Session.post`，故 patch 该方法；
> 每个并发任务使用独立 `HttpClient` 实例，避免共享 Session 与 `last_stream_metrics` 竞争。

---

## 六、Ragas AI 回答质量评估

本框架深度集成项目原有的 **Ragas** 评估机制，核心逻辑位于 [gs_api/report/ragas_evaluator.py](gs_api/report/ragas_evaluator.py)。

### 6.1 评估指标

| 指标 | 说明 | 阈值 |
|---|---|---|
| **Faithfulness** | 回答忠实度：基于上下文不编造事实 | ≥ 0.6 |
| **AnswerRelevancy** | 回答与问题的语义相关性 | ≥ 0.6 |
| **ContextRecall** | 上下文召回：回答是否充分覆盖参考答案 | ≥ 0.6 |
| ContextRelevance | 检索到的上下文是否与问题相关 | 可选 |

阈值可在 [gs_api/config/config.yaml](gs_api/config/config.yaml) → `ragas.threshold` 中调整。

### 6.2 评估场景（test_05_ragas_quality.py）

| 场景 | 说明 | 数据来源 |
|---|---|---|
| **通用问答** | 自我介绍 / 能力介绍 / RAG 概念 | 内置 3 条 |
| **课程咨询** | 价格 / 课时 / 学习路径 / 就业推荐 | `data/sample_docs/*.txt` 向量检索作为上下文 |
| **平台 FAQ** | 试听退款 / 结业证书 / 视频下载 | 内置 3 条 + RAG 上下文 |
| **CSV 批量** | 最多 12 条 Q&A 对 | [gs_api/data/qa_data.csv](gs_api/data/qa_data.csv) |
| **多轮记忆** | 第 2 轮用「这门课」指代 + 指代消解 | 流式会话串联 |
| **长文档检索** | 长文档切片/向量化 + **ContextRecall 上下文召回率达标** | 样例文档拼接成长文档 → 临时向量库 |

### 6.3 上下文复用项目原有 RAG 系统

为了让 Faithfulness 得分准确，Ragas 需要 retrieved_contexts。框架自动复用 `src.rag_system.RAGSystem` 的向量库：

```python
# 伪代码示意（真实实现位于 test_05_ragas_quality.py）
from src.rag_system import RAGSystem
rag = RAGSystem(...)
rag.load_and_index("data/sample_docs/")
contexts = rag._retrieve_documents(question)  # 作为 Ragas 的 retrieved_contexts
```

**长文档检索用例**（`test_long_document_retrieval_context_recall`）额外验证「切片 + 向量化」效果：

1. 把样例知识库文档拼接复制成长文档，写入临时目录（并用 `assert_len_greater` 校验字符数）；
2. 构建向量索引，**以 chunk 数量断言 `split_documents` 切片生效**；
3. 对长文档内的事实型问题做向量检索，断言召回上下文非空且命中关键词；
4. 用 Ragas 计算 **ContextRecall** 并断言达标（阈值取自 `ragas.threshold.context_recall`）。

### 6.4 Allure 报告中的 Ragas 结果

每个 Ragas 用例（含长文档检索）都会自动挂载以下附件，由 `evaluate_items` → `AllureManager.attach_ragas_table` 完成：
- **Ragas评估明细-CSV**：每个问题的每个指标的得分表格（DataFrame → CSV）
- **Ragas评估明细-HTML**：同一 DataFrame 的 HTML 表格（便于在报告中直接查看）
- **Ragas评估汇总**：每个指标的均值 + 样本数

---

## 七、四层架构详解

### 7.1 base 层：公共基础

| 模块 | 关键方法 / 能力 |
|---|---|
| [config.py](gs_api/base/config.py) | `config.base_url` / `config.token` / `config.get("ragas.threshold.faithfulness")` 三层优先级 |
| [http_client.py](gs_api/base/http_client.py) | `get / post / put / delete` + `post_stream()` 流式 SSE 逐行解析 → `StreamEvent(1001/1002/1003)`；`StreamMetrics` 量化 **TTFT 首包延迟** 并支持 **超时 / 断网重试**（`stream_retries` 可配，失败打印 WARNING） |
| [selenium_base.py](gs_api/base/selenium_base.py) | 8 种定位方式 + `wait_visible / wait_clickable` + 截图 + iframe + Alert + JS 滚动 |
| [assertions.py](gs_api/base/assertions.py) | `assert_api_success()` + 字段类型断言 + `assert_ragas_score()` |
| [data_loader.py](gs_api/base/data_loader.py) | `load_yaml("test_data.yaml")` / `load_csv("qa_data.csv")` / `load_qa_pairs()` |
| [deserializer.py](gs_api/base/deserializer.py) | `flexible_text()` 宽容拍平：把嵌套对象 / 数组 / 数字兜底为字符串（对应后端 `FlexibleTextDeserializer` 契约），供流式分片与文本回答做容错解析 |
| [logger.py](gs_api/base/logger.py) | INFO 级控制台 + DEBUG 级文件输出 |

### 7.2 page 层：接口封装（示例：聊天流式）

```python
# 示例：聊天接口 page 使用
from gs_api.page import ChatPage

chat = ChatPage()

# ① 文本聊天（不保存记录）
resp = chat.chat_text("你好高升AI")
answer = chat.chat_text_get_answer("《Java高级架构与微服务》学到什么？")

# ② 流式聊天 → 拼接成完整回答 + 事件列表
full_text, events = chat.chat_stream_full(
    question="解释微服务和单体的区别",
    session_id="xxx-session-id",
)
for ev in events:
    if ev.is_data:       # eventType == 1001
        print(ev.event_data, end="")
    elif ev.is_stop:     # eventType == 1002
        print("\n[停止]")

# ③ 读取流式指标（首包延迟 / 重试次数 / 总耗时）
m = chat.last_stream_metrics
if m.ttft_ms is not None and m.ttft_ms > 3000:
    print(f"首包延迟告警: TTFT={m.ttft_ms:.0f}ms, 重试={m.attempts - 1} 次")
```

### 7.3 script 层：conftest fixtures 一览

在 [gs_api/script/conftest.py](gs_api/script/conftest.py) 中提供以下共享 fixtures：

| fixture | scope | 说明 |
|---|---|---|
| `http_client` | session | 共享 `HttpClient` 实例（连接池） |
| `session_page` / `chat_page` / `history_page` / `embedding_page` | session | 4 大接口 Page 实例 |
| `web_page` | function | 每个用例独立 Selenium 浏览器，自动 quit |
| `shared_session_id` | module | 模块级共享会话 ID：模块开始新建一次会话，供所有接口串联 |
| `evaluator_llm` / `evaluator_embeddings` | session | 复用项目原有的 DeepSeek LLM + 硅基流动 Embeddings（Ragas 评估） |
| `ragas_evaluator` | session | 构造好的 `GaoShengRagasEvaluator` 实例 |
| `gs_test_data` | session | `test_data.yaml` 顶层 dict |
| `gs_qa_pairs` | session | `qa_data.csv` Q&A 对列表 |
| `sample_docs_dir` | session | 预制知识库文档目录，供长文档切片 / 向量检索 / Ragas 上下文复用 |
| `gao_sheng_expected_keyword` | function | 固定值 `"高升"`，用于断言 |

生命周期钩子：
- `pytest_configure`：启动时自动清空 Allure 结果、写入 `environment.properties` + `categories.json`
- markers 注册：共 12 种（`smoke / api / ui / session / chat / history / embedding / ragas / performance / webui / slow / requires_llm`）

### 7.4 report 层：Allure + Ragas 协同

```
pytest --alluredir → 生成 JSON/TXT/附件
        ↓
AllureManager.write_environment() → 环境信息
AllureManager.write_categories()  → 缺陷分类
AllureManager.attach_ragas_table(df) → Ragas DataFrame → CSV + HTML
        ↓
allure generate → 生成 HTML 报告（可 allure open 打开）
```

---

## 八、数据驱动（YAML + CSV）

### 8.1 YAML：复杂结构数据

[gs_api/data/test_data.yaml](gs_api/data/test_data.yaml) 按模块组织：

```yaml
sessions:
  default_n: 3
  expected_title_keyword: "高升"

questions:
  course_consultation:
    - question: "Python 编程入门课的价格是多少？"
      reference: "高升Python编程入门课（PY-101）价格199元..."
      type: "course"

history:
  update_titles: ["高升AI-自动化测试-会话A", "高升AI-自动化测试-会话B"]

embedding:
  save_messages:
    - "高升Python编程入门课..."
    - "高升Web前端开发实战..."
```

### 8.2 CSV：扁平 Q&A 列表

[gs_api/data/qa_data.csv](gs_api/data/qa_data.csv) 格式：

```csv
question,contexts,reference,type
"高升Python编程入门课的价格是多少？","PY-101|199元|40课时","价格199元，共40课时。",course
```

`data_loader.load_qa_pairs()` 会自动清洗并返回 list[dict]，直接喂给 Ragas 批量评估。

---

## 九、常见问题

**Q1：运行报错缺少 `DEEPSEEK_API_KEY`？**
A：没有 Key 时，标记 `@requires_llm` 的用例会自动 skip。若只想跑接口功能（不含 Ragas），请用 `-m "smoke and not ragas"`。

**Q2：流式聊天接口返回的每行 JSON 格式不同？**
A：`http_client.post_stream()` 已做容错，解析失败的行会被跳过并继续，不会抛出异常。可通过返回的 `events` 列表查看所有解析到的事件。跨网络分片的 JSON 会被自动拼接后再解析，保证数据分片完整性。

**Q2-1：如何定位「首包延迟」和「断网重试」问题？**
A：流式请求结束后读取 `ChatPage.last_stream_metrics`（或客户端 `last_stream_metrics`）：`ttft_ms` 为首包延迟、`attempts` 为实际请求次数（>1 表示发生过重试）、`total_ms` 为整条流耗时。重试次数/间隔/阈值分别在 `api.stream_retries`、`api.stream_retry_delay`、`api.ttft_threshold_ms` 调整；Allure 报告中会挂载 `首包延迟TTFT` 与 `流式请求指标` 附件。

**Q3：Web UI 用例（test_06_web_ui_smoke.py）为什么不报错却显示跳过？**
A：该类用例在页面不可达或元素选择器未匹配时会主动 `pytest.skip` 而非 fail，避免无浏览器/无前端环境时产生误报；选择器为占位实现，需按实际前端 DOM 调整。

**Q4：如何调整 Ragas 的通过阈值？**
A：编辑 `gs_api/config/config.yaml` 中 `ragas.threshold.*` 字段，或者直接用环境变量对应配置。

**Q5：Allure 报告中文显示乱码？**
A：请确保系统安装 `allure 2.20+`，并使用 PowerShell 7+ 或新版终端，UTF-8 编码已在所有写入中强制启用。

---

## 十、扩展指南

### 新增接口测试

1. 在对应 `page/*.py` 中添加接口方法，使用 `@allure.step` 标注
2. 在 `script/test_*.py` 中新增用例类，使用 `assertions` 断言
3. 在 `pytest.ini` + `conftest.py` 中注册 marker（如果是新模块）

### 新增 Ragas 自定义指标

```python
from ragas.metrics.base import Metric
class MyMetric(Metric):
    name = "my_custom_score"
    def score(self, ...): return 0.95

# 在 conftest 中注入 GaoShengRagasEvaluator
evaluator = GaoShengRagasEvaluator(metric_names=["faithfulness", "my_custom_score"])
```

---

## 十一、Jenkins 持续集成（CI 流水线）

仓库根目录提供声明式流水线 [Jenkinsfile](Jenkinsfile)，实现「提交即测」的工程化闭环。

### 11.1 流水线阶段

| 阶段 | 执行内容 |
|---|---|
| `Checkout` | 拉取当前分支代码，记录提交短哈希 |
| `环境准备` | 创建虚拟环境并 `pip install -r requirements.txt`，校验核心依赖可用 |
| `Run API Tests` | `pytest -m "smoke and not ui" -n auto` 并发执行接口冒烟（含 Ragas 质量评估） |
| `Run UI Tests` | `pytest -m ui --headless` 无头执行 Web UI 用例（串行，保证浏览器稳定） |
| `Generate Allure Report` | `allure generate` 生成 HTML 报告，并在 `post` 阶段由 Allure 插件发布 |
| `post` | 归档 UI 失败截图与 HTML 报告，清理无头 Chrome 临时文件 |

> 说明：`Run API Tests` / `Run UI Tests` 均显式传 `-o addopts=""` 关闭 `pytest.ini` 默认的
> `--clean-alluredir`，改由流水线在 API 阶段统一清理，避免清掉后续 UI 阶段的 Allure 结果。

### 11.2 Jenkins 侧准备（重要）

**① 安装 Allure 插件**

`系统管理 → 插件管理 → 可选插件` 搜索并安装 **Allure Jenkins Plugin**；
安装后到 `系统管理 → 全局工具配置 → Allure Commandline` 新增一个安装项
（勾选自动下载并指定版本，如 `2.27.0`）。未安装时 `post` 阶段的 `allure` 步骤会失败。

**② 配置凭证（Credentials）**

`系统管理 → 凭证管理 → 全局凭证` 新增以下 **Secret text** 类型凭证，ID 需与 `Jenkinsfile`
中 `environment` 段完全一致（否则变量注入为空导致用例跳过）：

| 凭证 ID | 用途 | 是否必须 |
|---|---|---|
| `gaosheng-ais-token` | 高升AI 登录 token（鉴权接口） | 部分接口需要 |
| `gaosheng-deepseek-key` | Ragas 评估 LLM 的 DeepSeek Key | Ragas 用例必须 |
| `gaosheng-embedding-key` | Ragas 评估 Embedding 的 Key（硅基流动） | 推荐 |

**③ 节点环境**

- Python 3.10+ 已加入 `PATH`；
- 已安装 Google Chrome（UI 用例以 `--headless` 无头运行，无需图形界面）；
- 若使用容器化 Agent，镜像需预装 Chrome 与中文字体，避免截图中文乱码。

**④ 创建流水线任务**

新建 `Pipeline` 类型任务 → `Pipeline script from SCM` → 选择 Git → 填写仓库地址与凭证
（`Credentials` 下拉选择已配置的 Git 账号，支持用户名密码或 SSH Key）→
`Script Path` 保持 `Jenkinsfile` → 保存并构建。

### 11.3 本地等价命令

流水线各阶段在本地可直接用等价命令复现：

```bash
# 环境准备
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# API 冒烟（并发）
pytest gs_api/script -m "smoke and not ui" -n auto -o addopts="" \
       --alluredir=gs_api/report/output/allure_results

# UI 无头
pytest gs_api/script -m ui --headless -o addopts="" \
       --alluredir=gs_api/report/output/allure_results

# 生成并打开报告
allure generate gs_api/report/output/allure_results \
       -o gs_api/report/output/allure_html --clean
allure open gs_api/report/output/allure_html
```

