"""直接测工具函数 —— 不碰协议层,纯函数最容易测。"""
from demo_server.tools.example import add, hello


def test_hello() -> None:
    assert hello("MCP") == "Hello, MCP!"


def test_add() -> None:
    assert add(1, 2) == 3
