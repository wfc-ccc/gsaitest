"""
宽容文本反序列化工具（对应后端 FlexibleTextDeserializer 的测试侧契约）。

大模型输出不稳定，「本该是字符串」的字段可能被返回成嵌套对象 / 数组 / 数字，
后端需要把它拍平成字符串，避免前端渲染时因类型异常而崩溃。
本模块在测试框架侧实现同一套拍平契约，用于：

1. 流式分片内容与响应数据的兜底解析；
2. 对畸形 Mock 报文做契约断言（嵌套对象应被拍平为字符串）。
"""

from typing import Any

_SEPARATOR = ""


def flexible_text(value: Any) -> str:
    """将任意 JSON 值宽容地拍平成字符串（嵌套结构内容不丢失）。

    拍平规则：

    - ``str``        -> 原样返回（幂等，不影响正常响应）
    - ``None``       -> ``""``
    - ``bool``       -> ``"true"`` / ``"false"``
    - ``int/float``  -> ``str(value)``
    - ``dict``       -> 按插入顺序递归拍平各 value 并拼接
    - ``list/tuple`` -> 按顺序递归拍平各元素并拼接
    - 其它类型       -> ``str(value)``
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return _SEPARATOR.join(flexible_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return _SEPARATOR.join(flexible_text(item) for item in value)
    return str(value)
