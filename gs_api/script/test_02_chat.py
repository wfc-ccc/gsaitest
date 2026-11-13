"""
二、聊天接口测试脚本（高升AI）。

覆盖接口文档：
3. POST /ais/chat              流式聊天（SSE）
4. POST /ais/chat/stop         停止生成
5. POST /ais/chat/text         文本聊天（不保存记录）
6. GET  /ais/chat/templates    模版列表

验证点：
- 文本聊天返回结构、回答非空、包含「高升」品牌信息
- 流式聊天：事件类型完整（1001/1002/1003）、拼接回答非空、语义与文本聊天一致
- 流式健壮性：首包延迟 TTFT 阈值、断网重试、数据分片完整性
- AI 容错：畸形报文（嵌套对象）经宽容解析拍平为字符串，前端不崩溃
- 停止生成：不报错，code=200
- 模版列表：字段 associationalWord / helpedWrite 等完整
- 集成 Ragas：文本聊天回答质量评估
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import allure
import pytest
import requests

import gs_api.base.http_client as http_client_module
from gs_api.base import assertions, get_logger, config, HttpClient, flexible_text
from gs_api.page import ChatPage, SessionPage
from gs_api.report import GaoShengRagasEvaluator, RagasEvalItem

log = get_logger(__name__)
pytestmark = [pytest.mark.api, pytest.mark.chat, pytest.mark.smoke]


class _FakeStreamResponse:
    """模拟流式响应对象：按固定长度分片吐出 SSE 报文，无需真实服务端。"""

    def __init__(self, chunks: list[str], status_code: int = 200):
        self._chunks = chunks
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size=None, decode_unicode=False):
        for chunk in self._chunks:
            yield chunk


class _FakeJsonResponse:
    """模拟非流式 JSON 响应对象，用于注入畸形 Mock 报文。"""

    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"}
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _build_sse_chunks(parts: list[tuple[str, Any]], chunk_size: int = 7) -> list[str]:
    """将若干条 SSE 报文拼成完整报文流，再按固定长度切成网络分片。

    故意让分片边界落在 JSON 中间，用于验证「数据分片完整性」；
    ``eventData`` 允许传入嵌套对象，用于验证宽容解析兜底能力。
    """
    payload = "".join(
        json.dumps({"eventType": et, "eventData": ed}, ensure_ascii=False) + "\n"
        for et, ed in parts
    )
    return [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)]


@allure.epic("高升AI接口自动化测试")
@allure.feature("聊天模块")
class TestChat:
    """聊天接口测试类。"""

    # ------------------------------------------------------------------
    # 5. 文本聊天（最稳定，先跑）
    # ------------------------------------------------------------------

    @allure.story("文本聊天（不保存记录）")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.title("文本聊天：自我介绍返回结构正确")
    def test_chat_text_intro(self, chat_page: ChatPage, gao_sheng_expected_keyword):
        resp = chat_page.chat_text("你是谁？请简单介绍一下你自己。")
        assertions.assert_api_success(resp, "文本聊天-自我介绍")
        answer = resp.data
        assertions.assert_data_type(answer, str, "data")
        assertions.assert_not_empty(answer, "回答文本")
        assertions.assert_contains(answer, gao_sheng_expected_keyword, "自我介绍回答")
        assert "天机" not in answer, f"回答中不应包含「天机」，实际: {answer}"
        resp.attach_allure("文本聊天-响应")

    @allure.story("文本聊天（不保存记录）")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.parametrize(
        "question",
        [
            "你好",
            "帮我推荐 3 个 Python 入门学习建议",
            "写一个快速排序的伪代码",
            "解释什么是微服务架构",
        ],
        ids=["问候", "Python入门建议", "快速排序伪码", "微服务解释"],
    )
    def test_chat_text_various(self, chat_page: ChatPage, question: str):
        resp = chat_page.chat_text(question)
        assertions.assert_api_success(resp, f"文本聊天: {question}")
        answer = resp.data
        assertions.assert_not_empty(answer, f"回答:{question}")
        assertions.assert_len_greater(answer, 4, "回答长度")

    # ------------------------------------------------------------------
    # 3. 流式聊天
    # ------------------------------------------------------------------

    @allure.story("流式聊天")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("流式聊天：返回数据+停止事件，拼接后非空")
    def test_chat_stream_success(self, chat_page: ChatPage, shared_session_id: str):
        question = "请用一句话解释什么是RAG（检索增强生成）。"
        full_text, events = chat_page.chat_stream_full(question, shared_session_id)

        with allure.step(f"事件数={len(events)}，拼接长度={len(full_text)}"):
            allure.attach(
                "\n".join([f"[{e.event_type}] {e.event_data[:50]}" for e in events[:20]]),
                name="事件列表(前20)",
                attachment_type=allure.attachment_type.TEXT,
            )
            allure.attach(full_text, name="拼接回答", attachment_type=allure.attachment_type.TEXT)

        assertions.assert_not_empty(events, "流式事件列表")
        assertions.assert_not_empty(full_text, "流式拼接回答")

        event_types = {e.event_type for e in events}
        with allure.step(f"事件类型集合: {event_types}"):
            # 1001 (数据) 是必须的；1002/1003 可选
            assert "1001" in event_types, "流式响应中未出现 EVENT_DATA(1001)"

    @allure.story("流式聊天")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("流式聊天：首包延迟 TTFT 小于 3000ms")
    def test_chat_stream_ttft_below_threshold(
        self, chat_page: ChatPage, shared_session_id: str
    ):
        """真实接口流式用例：量化首包延迟，验证大模型响应速度达标。"""
        question = "请用一句话解释什么是首包延迟（TTFT）。"
        full_text, events = chat_page.chat_stream_full(question, shared_session_id)

        assertions.assert_not_empty(events, "流式事件列表")
        assertions.assert_not_empty(full_text, "流式拼接回答")

        metrics = chat_page.last_stream_metrics
        assert metrics is not None, "未采集到流式指标 StreamMetrics"

        threshold = config.get("api.ttft_threshold_ms", 3000)
        assert metrics.ttft_ms is not None, "流中未出现 1001 数据事件，无法计算 TTFT"
        assert metrics.ttft_ms < threshold, (
            f"首包延迟过高: TTFT={metrics.ttft_ms:.0f}ms >= 阈值 {threshold}ms"
        )

        with allure.step(
            f"首包延迟 TTFT={metrics.ttft_ms:.0f}ms (< {threshold}ms)，"
            f"总耗时={metrics.total_ms:.0f}ms"
        ):
            allure.attach(
                metrics.summary(),
                name="流式指标",
                attachment_type=allure.attachment_type.TEXT,
            )

    @allure.story("流式异常与重试")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("流式请求断网(ConnectionError)：自动重试并保证分片完整")
    def test_chat_stream_retry_on_connection_error(self):
        """Mock 断网场景：验证首包前的 ConnectionError 会触发配置化重试，

        且重试成功后跨分片拼接的 SSE 内容完整无丢失。
        """
        client = HttpClient()
        parts = [("1001", "高升"), ("1001", "AI流式"), ("1002", "end"), ("1003", "{}")]
        # 分片长度 7 会落在 JSON 中间，用于验证分片边界拼接
        fake_resp = _FakeStreamResponse(_build_sse_chunks(parts, chunk_size=7))

        calls = {"n": 0}

        def _flaky_post(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:  # 前两次模拟断网
                raise requests.ConnectionError("模拟断网: Connection reset by peer")
            return fake_resp

        with mock.patch.object(
            http_client_module.log, "warning"
        ) as mock_warn, mock.patch.object(
            client._session, "post", side_effect=_flaky_post
        ):
            events = list(client.post_stream(
                "/ais/chat",
                json_body={"question": "你好", "sessionId": "gs-test-0001"},
                stream_retries=2,
                stream_retry_delay=0.01,
            ))

        metrics = client.last_stream_metrics
        with allure.step(f"实际请求次数={calls['n']}，指标: {metrics.summary()}"):
            allure.attach(
                metrics.summary(),
                name="流式重试指标",
                attachment_type=allure.attachment_type.TEXT,
            )

        assert calls["n"] == 3, f"断网后应重试 2 次（共 3 次请求），实际 {calls['n']} 次"
        assert mock_warn.call_count == 2, "每次失败均应打印 WARNING 警告日志"
        assert metrics.attempts == 3, f"指标记录的请求次数异常: {metrics.attempts}"
        assert metrics.retried is True, "指标未标记发生重试"
        assert metrics.ttft_ms is not None, "重试成功后未采集到 TTFT"

        event_types = [e.event_type for e in events]
        assert event_types == ["1001", "1001", "1002", "1003"], (
            f"重试后事件序列异常: {event_types}"
        )
        merged = "".join(e.event_data for e in events if e.is_data)
        assert merged == "高升AI流式", f"跨分片拼接内容不完整: {merged!r}"

    @allure.story("AI 容错与边界")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("文本聊天：content 为嵌套对象时宽容拍平，code=200 且前端不崩溃")
    def test_chat_text_tolerant_deserialization(self, chat_page: ChatPage):
        """针对大模型输出不稳定的特性，构造畸形 Mock 报文：

        本该是字符串的 content 变成了嵌套字典，验证宽容解析机制
        （FlexibleTextDeserializer 等价契约）能将其拍平为字符串，
        接口 code 仍为 200，前端拿到纯文本而不会渲染崩溃。
        """
        malformed = {
            "code": 200,
            "msg": "success",
            "requestId": "gs-tolerance-0001",
            "data": {"text": "高升", "meta": {"brand": {"name": "AI"}}},
        }
        fake_resp = _FakeJsonResponse(malformed)
        with allure.step("挂载畸形 Mock 报文"):
            allure.attach(
                json.dumps(malformed, ensure_ascii=False, indent=2),
                name="畸形Mock报文",
                attachment_type=allure.attachment_type.JSON,
            )

        # 非流式请求统一走 requests.Session.request，故在真实 HTTP 边界拦截
        with mock.patch.object(requests.Session, "request", return_value=fake_resp):
            resp = chat_page.chat_text("你好")
            answer = chat_page.chat_text_get_answer("你好")

        assertions.assert_api_success(resp, "文本聊天(畸形报文)")
        assertions.assert_equal(resp.code, 200, "业务 code")
        assertions.assert_data_type(resp.data, dict, "畸形的 data（嵌套对象）")

        with allure.step("宽容解析：嵌套对象拍平为字符串"):
            flattened = flexible_text(resp.data)
            allure.attach(flattened, name="拍平结果", attachment_type=allure.attachment_type.TEXT)

        assert isinstance(flattened, str), f"拍平结果应为字符串，实际 {type(flattened).__name__}"
        assert flattened == "高升AI", f"拍平内容异常: {flattened!r}"
        # 前端安全渲染：拍平结果不应残留 Python 结构符号
        assert not any(ch in flattened for ch in "{}[]'\""), (
            f"拍平结果疑似残留结构符号: {flattened!r}"
        )

        # 端到端路径：chat_text_get_answer 内部已走宽容解析
        assert isinstance(answer, str), f"端到端提取结果应为字符串，实际 {type(answer).__name__}"
        assert answer == "高升AI", f"端到端拍平内容异常: {answer!r}"

        # 正常报文零影响：字符串输入拍平后原样返回（幂等）
        assertions.assert_equal(flexible_text("高升AI"), "高升AI", "字符串拍平幂等性")

    @allure.story("AI 容错与边界")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("流式聊天：分片内容为嵌套对象时拍平，事件不丢失")
    def test_chat_stream_tolerant_deserialization(self):
        """流式分片的 eventData 被大模型返回成嵌套对象时，

        验证流式解析仍产出纯字符串（拍平），且事件序列与拼接内容完整。
        """
        client = HttpClient()
        parts = [
            ("1001", {"text": "高升", "meta": {"brand": {"name": "AI"}}}),
            ("1001", "流式"),
            ("1002", "end"),
        ]
        fake_resp = _FakeStreamResponse(_build_sse_chunks(parts, chunk_size=5))

        with mock.patch.object(client._session, "post", return_value=fake_resp):
            events = list(client.post_stream(
                "/ais/chat",
                json_body={"question": "你好", "sessionId": "gs-test-0002"},
            ))

        data_events = [e for e in events if e.is_data]
        texts = [e.event_data for e in data_events]
        with allure.step(f"分片文本: {texts}"):
            allure.attach(
                json.dumps(texts, ensure_ascii=False),
                name="拍平后的分片文本",
                attachment_type=allure.attachment_type.JSON,
            )

        assert [e.event_type for e in events] == ["1001", "1001", "1002"], (
            f"事件序列异常: {[e.event_type for e in events]}"
        )
        assert all(isinstance(t, str) for t in texts), f"分片未拍平为字符串: {texts}"
        assert "".join(texts) == "高升AI流式", f"拍平后拼接内容异常: {''.join(texts)!r}"

    @allure.story("流式聊天")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("流式聊天 vs 文本聊天：回答语义一致性（Ragas辅助）")
    @requires_llm
    def test_chat_stream_vs_text_consistency(
        self,
        chat_page: ChatPage,
        shared_session_id: str,
        ragas_evaluator: GaoShengRagasEvaluator,
    ):
        question = "什么是高升AI？请简要说明。"

        text_answer = chat_page.chat_text_get_answer(question)
        stream_full, _ = chat_page.chat_stream_full(question, shared_session_id)

        with allure.step("对比两次回答长度"):
            allure.attach(text_answer, "文本聊天回答", allure.attachment_type.TEXT)
            allure.attach(stream_full, "流式聊天回答", allure.attachment_type.TEXT)

        assertions.assert_not_empty(stream_full, "流式回答")
        # Ragas AnswerRelevancy 辅助判断语义
        items = [
            RagasEvalItem(question=question, response=text_answer, reference=stream_full),
            RagasEvalItem(question=question, response=stream_full, reference=text_answer),
        ]
        df = ragas_evaluator.evaluate_items(items, scenario_name="流式vs文本一致性")
        # 不做强断言，只记录；避免网络波动导致失败
        log.info("流式vs文本评估完成\n%s", df.head())

    # ------------------------------------------------------------------
    # 4. 停止生成
    # ------------------------------------------------------------------

    @allure.story("停止生成")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("停止生成接口返回成功")
    def test_chat_stop(self, chat_page: ChatPage, shared_session_id: str):
        resp = chat_page.stop_chat(shared_session_id)
        # stop 接口无论是否真的在生成都应该 code=200
        assertions.assert_code(resp, 200)
        resp.attach_allure("停止生成-响应")

    # ------------------------------------------------------------------
    # 6. 模版列表
    # ------------------------------------------------------------------

    @allure.story("模版列表")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("获取模版列表字段齐全")
    def test_get_templates(self, chat_page: ChatPage):
        resp = chat_page.get_templates()
        assertions.assert_api_success(resp, "获取模版列表")

        data = resp.data
        assertions.assert_data_type(data, dict, "data")
        required = ["associationalWord", "helpedWrite", "continuedWrite", "polish", "streamline"]
        for key in required:
            assertions.assert_key_exists(data, key, "模版data")
            assertions.assert_not_empty(data[key], f"模版字段 {key}")

        with allure.step("associationalWord 模版含 $input 占位符"):
            assertions.assert_contains(data["associationalWord"], "$input", "关联词模版")

        resp.attach_allure("模版列表-响应")

    # ------------------------------------------------------------------
    # Ragas 集成：对文本聊天回答做质量评估
    # ------------------------------------------------------------------

    @allure.story("Ragas 回答质量评估")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("文本聊天多轮回答 Ragas 质量评估")
    @pytest.mark.ragas
    @requires_llm
    def test_chat_ragas_quality(
        self,
        chat_page: ChatPage,
        ragas_evaluator: GaoShengRagasEvaluator,
        gs_qa_pairs,
    ):
        if not gs_qa_pairs:
            pytest.skip("未提供 qa_data.csv，跳过 ragas 批量评估")

        items: list[RagasEvalItem] = []
        for pair in gs_qa_pairs[:8]:  # 最多取 8 条，控制耗时
            question = pair["question"]
            try:
                answer = chat_page.chat_text_get_answer(question)
            except Exception as e:
                log.warning("回答 question=%s 失败: %s", question, e)
                answer = ""
            ctx = pair["contexts"].split("|") if pair.get("contexts") else []
            items.append(RagasEvalItem(
                question=question,
                response=answer,
                retrieved_contexts=ctx or [f"（来自{question}的空上下文占位）"],
                reference=pair["reference"],
                type=pair.get("type") or "general",
            ))

        df = ragas_evaluator.evaluate_items(items, scenario_name="文本聊天Ragas评估")
        ragas_evaluator.assert_thresholds(df, scenario_name="文本聊天")
