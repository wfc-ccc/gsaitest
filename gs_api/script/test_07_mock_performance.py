"""
七、联调与性能测试（Mock 大模型控成本）。

设计要点：
- 用 ``unittest.mock`` 在 HTTP 边界拦截「第三方大模型 / 后端接口」的真实调用，
  直接返回瞬间响应的假数据，使压测可离线、可重复、且零 Token 成本；
- 用 ``concurrent.futures.ThreadPoolExecutor`` 模拟并发，统计总耗时 / TPS / 平均 TTFT；
- 用 mock 模拟网关限流（并发在途超过上限即返回 429），验证框架能正确感知限流。

注意：
- 非流式请求走 ``requests.Session.request``，流式请求走 ``requests.Session.post``，
  二者拦截点不同，本文件针对流式场景拦截 ``Session.post``；
- 每个并发任务使用独立的 ``HttpClient``，避免共享 Session 与 ``last_stream_metrics`` 竞争。
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import allure
import pytest
import requests

from gs_api.base import HttpClient, config, get_logger
from gs_api.page import ChatPage

log = get_logger(__name__)
pytestmark = [pytest.mark.api, pytest.mark.performance]


# ======================================================================
# 假数据与 Mock 替身
# ======================================================================

FAKE_ANSWER = "高升AI：这是一条用于并发压测的模拟回答，由 mock 大模型瞬间返回，无需真实调用。"


def _build_sse_lines(text: str, chunk_size: int = 8) -> list[str]:
    """把回答文本切成多片 1001 事件，末尾追加 1002 结束事件（模拟真实 SSE 报文）。"""
    lines: list[str] = []
    for i in range(0, len(text), chunk_size):
        lines.append(json.dumps(
            {"eventType": "1001", "eventData": text[i:i + chunk_size]},
            ensure_ascii=False,
        ))
    lines.append(json.dumps({"eventType": "1002", "eventData": ""}, ensure_ascii=False))
    return lines


class _FakeResponse:
    """``requests.Response`` 的最小替身，支持 raise_for_status / iter_content。"""

    def __init__(self, lines=None, status_code: int = 200, json_body=None):
        self.status_code = status_code
        self.headers = {"Content-Type": "text/event-stream"}
        self._lines = lines or []
        self._json = json_body or {}
        self.text = json.dumps(self._json, ensure_ascii=False)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=None, decode_unicode=False):
        for line in self._lines:
            yield line + "\n"


class _RateLimitedGateway:
    """模拟「后端网关 + 第三方大模型」：并发在途超过 ``limit`` 时返回 429。

    以一个微小的 ``process_sec`` 模拟上游大模型处理耗时，制造稳定的并发窗口。
    """

    def __init__(self, limit: int, process_sec: float = 0.05):
        self.limit = limit
        self.process_sec = process_sec
        self._inflight = 0
        self._lock = threading.Lock()
        self.rejected = 0   # 被限流（429）的请求数
        self.accepted = 0   # 被放行的请求数

    def post(self, *args, **kwargs):
        with self._lock:
            if self._inflight >= self.limit:
                self.rejected += 1
                return _FakeResponse(
                    status_code=429,
                    json_body={"code": 429, "msg": "Too Many Requests"},
                )
            self._inflight += 1
            self.accepted += 1
        try:
            time.sleep(self.process_sec)
            return _FakeResponse(lines=_build_sse_lines(FAKE_ANSWER))
        finally:
            with self._lock:
                self._inflight -= 1


@allure.epic("高升AI接口自动化测试")
@allure.feature("联调与性能测试（Mock大模型）")
class TestMockPerformance:
    """Mock 大模型下的并发性能与限流验证。"""

    CONCURRENCY = 10          # 并发线程数
    REQUESTS = 40             # 总请求数
    TPS_THRESHOLD = 20.0      # TPS 下限（req/s）

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _run_one(index: int) -> dict:
        """单个并发任务：独立 client 发起一次流式请求，返回指标与最终文本。"""
        client = HttpClient()
        page = ChatPage(client=client)
        text_parts: list[str] = []
        events = 0
        for ev in page.chat_stream(f"并发压测问题-{index}", session_id="perf-session"):
            events += 1
            if ev.is_data:
                text_parts.append(ev.event_data)
        metrics = client.last_stream_metrics
        return {
            "ttft_ms": metrics.ttft_ms if metrics else None,
            "total_ms": metrics.total_ms if metrics else None,
            "events": events,
            "text": "".join(text_parts),
        }

    # ------------------------------------------------------------------
    # 场景1：并发吞吐 + 首包延迟
    # ------------------------------------------------------------------

    @allure.story("并发吞吐与首包延迟")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("Mock大模型并发压测：TPS 与平均 TTFT")
    @pytest.mark.slow
    def test_concurrent_stream_throughput(self):
        """mock 掉大模型后并发压测，断言 TPS、平均 TTFT 与分片完整性。"""
        fake = lambda *a, **k: _FakeResponse(lines=_build_sse_lines(FAKE_ANSWER))  # noqa: E731

        with mock.patch.object(requests.Session, "post", side_effect=fake):
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=self.CONCURRENCY) as pool:
                results = list(pool.map(self._run_one, range(self.REQUESTS)))
            elapsed = time.perf_counter() - start

        tps = self.REQUESTS / elapsed if elapsed > 0 else float("inf")
        ttfts = [r["ttft_ms"] for r in results if r["ttft_ms"] is not None]
        avg_ttft = statistics.fmean(ttfts) if ttfts else 0.0
        max_ttft = max(ttfts) if ttfts else 0.0
        ttft_threshold = config.get("api.ttft_threshold_ms", 3000)

        summary = (
            f"并发数={self.CONCURRENCY}  总请求数={self.REQUESTS}\n"
            f"总耗时={elapsed * 1000:.1f}ms\n"
            f"TPS={tps:.2f} req/s\n"
            f"平均TTFT={avg_ttft:.1f}ms  最大TTFT={max_ttft:.1f}ms（阈值 {ttft_threshold}ms）\n"
            f"样本数={len(ttfts)}"
        )
        log.info("并发压测结果:\n%s", summary)
        allure.attach(summary, name="并发性能汇总", attachment_type=allure.attachment_type.TEXT)

        with allure.step("断言所有并发请求返回完整分片"):
            assert len(results) == self.REQUESTS, "并发请求数不足"
            assert all(r["text"] == FAKE_ANSWER for r in results), "存在分片丢失/拼接错误"
            assert all(r["events"] == len(_build_sse_lines(FAKE_ANSWER)) for r in results), (
                "事件数与预期不符，流式解析存在丢包"
            )

        with allure.step(f"断言 TPS >= {self.TPS_THRESHOLD}"):
            assert tps >= self.TPS_THRESHOLD, (
                f"TPS 低于阈值: {tps:.2f} < {self.TPS_THRESHOLD}（总耗时 {elapsed * 1000:.1f}ms）"
            )

        with allure.step(f"断言 平均TTFT <= {ttft_threshold}ms"):
            assert avg_ttft <= ttft_threshold, (
                f"平均首包延迟超阈值: {avg_ttft:.1f}ms > {ttft_threshold}ms"
            )

    # ------------------------------------------------------------------
    # 场景2：并发触发网关限流（429）
    # ------------------------------------------------------------------

    @allure.story("网关限流验证")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("并发压测触发网关限流并断言 429 Too Many Requests")
    def test_concurrent_rate_limit_429(self):
        """并发数远大于网关并发上限时，断言限流策略被触发并返回 429。"""
        limit = 2      # 网关允许的并发在途上限
        total = 30     # 并发总请求数
        gateway = _RateLimitedGateway(limit=limit, process_sec=0.05)

        rejected: list[requests.HTTPError] = []
        succeeded = 0
        with mock.patch.object(requests.Session, "post", side_effect=gateway.post):
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(self._run_one, i) for i in range(total)]
                for fut in futures:
                    try:
                        fut.result()
                        succeeded += 1
                    except requests.HTTPError as e:
                        rejected.append(e)

        log.info(
            "限流结果: 成功=%d 被限流=%d 网关拒绝计数=%d",
            succeeded, len(rejected), gateway.rejected,
        )

        with allure.step("断言并发场景触发了网关限流（429 Too Many Requests）"):
            assert gateway.rejected > 0, (
                f"并发请求数({total})远大于网关并发上限({limit})，但未触发限流(429)"
            )
            assert len(rejected) == gateway.rejected, (
                f"客户端感知的 429 次数({len(rejected)})与网关拒绝次数({gateway.rejected})不一致"
            )
            assert succeeded == total - gateway.rejected, (
                f"成功数({succeeded}) != 总数({total}) - 被限流数({gateway.rejected})"
            )
            assert all("429" in str(e) for e in rejected), "限流异常未携带 429 状态码"

        allure.attach(
            f"网关并发上限={limit}\n并发总请求数={total}\n"
            f"成功={succeeded}\n被限流(429)={len(rejected)}\n"
            f"示例异常: {rejected[0] if rejected else '无'}",
            name="网关限流验证汇总",
            attachment_type=allure.attachment_type.TEXT,
        )
