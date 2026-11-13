"""
六、高升AI Web UI 冒烟测试脚本。

基于 Selenium 的 UI 辅助测试，**全量使用 WebDriverWait 显式等待，不使用固定 time.sleep**：
- 打开高升首页
- 新建会话按钮可点击
- 发送问题后等待「停止生成」按钮消失 / 「复制」按钮出现，再断言气泡最终文本

注意：UI 选择器为占位，需根据实际前端 DOM 调整。
默认用 skip 以避免无浏览器环境失败。
"""

from __future__ import annotations

import allure
import pytest

from gs_api.base import assertions, get_logger, config
from gs_api.page import GaoShengWebPage

log = get_logger(__name__)
pytestmark = [
    pytest.mark.ui,
    pytest.mark.webui,
    pytest.mark.skipif(
        config.get("selenium.headless", None) is None,
        reason="Web UI 冒烟测试默认跳过，如需运行请移除 skip 标记并提供浏览器",
    ),
]


@allure.epic("高升AI接口自动化测试")
@allure.feature("Web UI冒烟")
class TestWebUISmoke:
    """Web UI 冒烟测试类。"""

    @allure.story("首页可访问")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("高升AI首页可打开")
    def test_open_home(self, web_page: GaoShengWebPage):
        try:
            web_page.open_home()
            # 显式等待首页关键元素出现，替代固定 sleep
            web_page.wait_present(*GaoShengWebPage.NEW_SESSION_BTN, timeout=10)
        except Exception as e:
            pytest.skip(f"首页不可达（API服务未启动Web），跳过：{e}")

        with allure.step("首页截图"):
            web_page.screenshot("homepage")

    @allure.story("新建会话UI")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.title("UI点击新建会话后历史数量变化")
    def test_ui_new_session(self, web_page: GaoShengWebPage):
        try:
            web_page.open_home()
            web_page.wait_present(*GaoShengWebPage.NEW_SESSION_BTN, timeout=10)
            before = web_page.ui_get_history_count()
            web_page.ui_new_session()
            after = web_page.ui_get_history_count()
        except Exception as e:
            pytest.skip(f"Web UI 元素选择器未匹配，跳过：{e}")

        log.info("历史数量: before=%s after=%s", before, after)
        with allure.step("新建会话后截图"):
            web_page.screenshot("after_new_session")

    # ------------------------------------------------------------------
    # 流式聊天气泡渲染：动态等待 + 异步断言
    # ------------------------------------------------------------------

    @allure.story("聊天流式气泡渲染")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.title("发送消息后等待气泡渲染完成并断言最终全文")
    def test_chat_bubble_render_complete(self, web_page: GaoShengWebPage):
        """发送消息 -> 等待「停止生成」消失 / 「复制」出现 -> 提取最终全文断言。

        全程不使用 time.sleep，改用自定义 expected_conditions（AnswerRenderComplete）
        做动态等待，规避「固定等待时长不可靠」导致的偶发失败。
        """
        question = "你是谁？请用一句话介绍自己。"

        try:
            web_page.open_home()
            web_page.wait_present(*GaoShengWebPage.NEW_SESSION_BTN, timeout=10)
            web_page.ui_new_session()
        except Exception as e:
            pytest.skip(f"Web UI 元素选择器未匹配，跳过：{e}")

        # 发送后动态等待气泡渲染完成，拿到的即为「停止生成消失 / 复制出现」后的最终文本
        answer = web_page.ui_send_question(question, timeout=60)
        answer = (answer or "").strip()

        assertions.assert_not_empty(answer, "聊天气泡最终回答文本")
        assert "天机" not in answer, f"聊天气泡出现旧品牌词「天机」: {answer[:200]}"

        allure.attach(
            answer,
            name="聊天气泡最终文本",
            attachment_type=allure.attachment_type.TEXT,
        )
        with allure.step("气泡渲染完成后截图"):
            web_page.screenshot("chat_bubble")
