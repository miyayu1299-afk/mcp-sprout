"""直接测资源函数(与工具同理:先测纯函数,不碰协议层)。"""
from demo_full.resources.example import get_note


def test_get_note_hit() -> None:
    assert "欢迎使用" in get_note("welcome")


def test_get_note_miss() -> None:
    assert "未找到" in get_note("nope")