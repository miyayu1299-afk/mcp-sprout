"""直接测工具函数 —— 不碰协议层,纯函数最容易测。"""
import pytest

from demo_full.tools.example import add, divide, hello


def test_hello() -> None:
    assert hello("MCP") == "Hello, MCP!"


def test_add() -> None:
    assert add(1, 2) == 3


def test_divide() -> None:
    assert divide(10, 2) == 5


def test_divide_by_zero() -> None:
    with pytest.raises(ValueError, match="除数不能为 0"):
        divide(1, 0)