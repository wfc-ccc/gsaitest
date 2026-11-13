"""
HTTP 请求客户端封装。

基于 requests 库封装统一的 HTTP 请求方法，
支持自动重试、鉴权、日志记录、流式响应解析。
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Generator, Optional

import requests
import allure

from .config import config
from .deserializer import flexible_text
from .logger import get_logger

log = get_logger(__name__)


def _attach_allure_text(content: str, name: str) -> None:
    """挂载文本附件到 Allure（无报告上下文时静默忽略）。"""
    try:
        allure.attach(content, name=name, attachment_type=allure.attachment_type.TEXT)
    except Exception:
        pass


def _default_headers(token: Optional[str] = None) -> dict:
    """构造默认请求头。"""
    headers = {
        "Accept": "application/json, text/event-stream",
        "User-Agent": "GaoSheng-AI-Test-Framework/1.0.0",
    }
    auth_token = token if token is not None else config.token
    if auth_token:
        headers["Authorization"] = auth_token
    return headers


class ApiResponse:
    """统一 API 响应封装。"""

    def __init__(self, raw: requests.Response):
        self.raw = raw
        self.status_code: int = raw.status_code
        self.headers: dict = dict(raw.headers)
        self.text: str = raw.text
        self._json: Optional[dict] = None

    @property
    def json(self) -> dict:
        if self._json is None:
            try:
                self._json = self.raw.json()
            except (json.JSONDecodeError, ValueError):
                self._json = {}
        return self._json

    @property
    def code(self) -> Optional[int]:
        return self.json.get("code")

    @property
    def msg(self) -> Optional[str]:
        return self.json.get("msg")

    @property
    def data(self) -> Any:
        return self.json.get("data")

    @property
    def request_id(self) -> Optional[str]:
        return self.json.get("requestId")

    @property
    def is_success(self) -> bool:
        return self.status_code == 200 and self.code == 200

    def attach_allure(self, name: str = "API响应") -> None:
        allure.attach(
            json.dumps(self.json, ensure_ascii=False, indent=2),
            name=name,
            attachment_type=allure.attachment_type.JSON,
        )


class StreamEvent:
    """流式聊天事件封装。"""

    EVENT_DATA = "1001"
    EVENT_STOP = "1002"
    EVENT_PARAM = "1003"

    def __init__(self, event_type: str, event_data: str):
        self.event_type = event_type
        self.event_data = event_data

    @property
    def is_data(self) -> bool:
        return self.event_type == self.EVENT_DATA

    @property
    def is_stop(self) -> bool:
        return self.event_type == self.EVENT_STOP

    @property
    def is_param(self) -> bool:
        return self.event_type == self.EVENT_PARAM


@dataclass
class StreamMetrics:
    """流式请求关键指标。

    用于首包延迟（TTFT）、断网重试次数等异常场景的量化断言。
    """

    ttft_ms: Optional[float] = None          # 首包延迟: 请求发出 -> 首个 1001 数据事件
    first_chunk_ms: Optional[float] = None   # 首个网络分片延迟
    total_ms: Optional[float] = None         # 整条流总耗时
    event_count: int = 0                     # 累计收到的事件数
    attempts: int = 1                        # 实际请求次数（含重试）

    @property
    def retried(self) -> bool:
        """是否发生过重试。"""
        return self.attempts > 1

    def summary(self) -> str:
        """指标单行摘要，便于日志与 Allure 展示。"""
        def _fmt(value: Optional[float]) -> str:
            return "N/A" if value is None else f"{value:.1f}ms"

        return (
            f"请求次数={self.attempts} 事件数={self.event_count} "
            f"首分片={_fmt(self.first_chunk_ms)} "
            f"TTFT={_fmt(self.ttft_ms)} 总耗时={_fmt(self.total_ms)}"
        )


class HttpClient:
    """高升AI接口 HTTP 客户端。"""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = base_url or config.base_url
        self.timeout = timeout or config.timeout
        self.retries = config.get("api.retries", 3)
        self.retry_delay = config.get("api.retry_delay", 1)
        # 最近一次流式请求的指标（TTFT / 重试次数 / 总耗时）
        self.last_stream_metrics: Optional[StreamMetrics] = None
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        data: Any = None,
        json_body: Any = None,
        headers: Optional[dict] = None,
        files: Any = None,
        token: Optional[str] = None,
        timeout: Optional[int] = None,
        stream: bool = False,
    ) -> ApiResponse:
        """通用请求方法，含自动重试。"""
        url = self._url(path)
        merged_headers = _default_headers(token)
        if headers:
            merged_headers.update(headers)

        _timeout = timeout or self.timeout
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                with allure.step(f"HTTP {method} {path} (第{attempt}次)"):
                    resp = self._session.request(
                        method=method,
                        url=url,
                        params=params,
                        data=data,
                        json=json_body,
                        headers=merged_headers,
                        files=files,
                        timeout=_timeout,
                        stream=stream,
                    )
                    api_resp = ApiResponse(resp)
                    allure.attach(
                        f"{method} {url}\nStatus: {resp.status_code}",
                        name="请求概要",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                    return api_resp
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < self.retries:
                    time.sleep(self.retry_delay * attempt)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("请求失败")

    def get(
        self,
        path: str,
        params: Optional[dict] = None,
        **kwargs,
    ) -> ApiResponse:
        return self._request("GET", path, params=params, **kwargs)

    def post(
        self,
        path: str,
        json_body: Any = None,
        data: Any = None,
        params: Optional[dict] = None,
        files: Any = None,
        **kwargs,
    ) -> ApiResponse:
        return self._request(
            "POST", path, json_body=json_body, data=data, params=params, files=files, **kwargs
        )

    def put(
        self,
        path: str,
        json_body: Any = None,
        params: Optional[dict] = None,
        **kwargs,
    ) -> ApiResponse:
        return self._request("PUT", path, json_body=json_body, params=params, **kwargs)

    def delete(
        self,
        path: str,
        params: Optional[dict] = None,
        **kwargs,
    ) -> ApiResponse:
        return self._request("DELETE", path, params=params, **kwargs)

    def post_stream(
        self,
        path: str,
        json_body: Any = None,
        **kwargs,
    ) -> Generator[StreamEvent, None, None]:
        """发送流式 POST 请求，逐行解析 SSE 事件。

        增量能力：
        - 首包延迟 TTFT：请求发出 -> 首个 EVENT_DATA(1001) 数据事件，单位毫秒，
          结果记录在 ``self.last_stream_metrics`` 并挂载到 Allure；
        - 超时/断网重试：捕获 Timeout / ConnectionError，重试次数可配
          （``stream_retries`` 或 config ``api.stream_retries``），失败时打印 WARNING。
          仅当「尚未产出任何事件」时才重试，避免已推送内容被重复输出。
        """
        url = self._url(path)
        merged_headers = _default_headers(kwargs.pop("token", None))
        extra_headers = kwargs.pop("headers", None)
        if extra_headers:
            merged_headers.update(extra_headers)

        timeout = kwargs.get("timeout") or self.timeout
        max_retries = kwargs.get("stream_retries")
        if max_retries is None:
            max_retries = config.get("api.stream_retries", 2)
        retry_delay = kwargs.get("stream_retry_delay")
        if retry_delay is None:
            retry_delay = config.get("api.stream_retry_delay", 0.5)

        metrics = StreamMetrics()
        self.last_stream_metrics = metrics
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_retries + 2):
            metrics.attempts = attempt
            start_ts = time.perf_counter()
            try:
                with allure.step(f"流式 POST {path} (第{attempt}次)"):
                    resp = self._session.post(
                        url,
                        json=json_body,
                        headers=merged_headers,
                        stream=True,
                        timeout=timeout,
                    )
                    resp.raise_for_status()
                    yield from self._iter_sse(resp, metrics, start_ts)
                return
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                if metrics.event_count > 0:
                    # 已产出部分内容，重试会重复推送，直接抛出让上层感知
                    raise
                if attempt <= max_retries:
                    wait = retry_delay * attempt
                    log.warning(
                        "流式请求失败(第%d/%d次) %s: %s，%.2fs 后重试",
                        attempt, max_retries, type(e).__name__, e, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("流式请求失败")

    @staticmethod
    def _iter_sse(
        resp: Any,
        metrics: StreamMetrics,
        start_ts: float,
    ) -> Generator[StreamEvent, None, None]:
        """解析 SSE 数据行，同时记录首分片 / TTFT / 总耗时等指标。"""
        buffer = ""
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            if metrics.first_chunk_ms is None:
                metrics.first_chunk_ms = (time.perf_counter() - start_ts) * 1000
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                et = str(obj.get("eventType", ""))
                # 兜底解析：大模型可能把本该是字符串的分片内容返回成嵌套对象
                ed = flexible_text(obj.get("eventData", ""))
                metrics.event_count += 1
                if metrics.ttft_ms is None and et == StreamEvent.EVENT_DATA:
                    metrics.ttft_ms = (time.perf_counter() - start_ts) * 1000
                    log.info("流式首包延迟 TTFT=%.1fms", metrics.ttft_ms)
                    _attach_allure_text(
                        f"TTFT={metrics.ttft_ms:.1f}ms\n{metrics.summary()}",
                        name="首包延迟TTFT",
                    )
                yield StreamEvent(event_type=et, event_data=ed)

        metrics.total_ms = (time.perf_counter() - start_ts) * 1000
        log.info("流式请求完成: %s", metrics.summary())
        _attach_allure_text(metrics.summary(), name="流式请求指标")


http_client = HttpClient()
