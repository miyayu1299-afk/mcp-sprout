"""示范工具:写新工具照这个格式抄。

docstring 规范(重要,客户端 AI 靠它理解你的工具):
- 第一行:一句话说清做什么
- 中间:参数含义、返回什么、什么情况报错
"""
from mcp.server.fastmcp import FastMCP


def hello(name: str) -> str:
    """向指定的人问好。

    Args:
        name: 要问候的名字。

    Returns:
        问候语字符串。
    """
    return f"Hello, {name}!"


def add(a: int, b: int) -> int:
    """计算两个整数之和。

    纯函数示例:不碰协议、不碰 IO,单测直接测(见 tests/test_tools.py)。

    Args:
        a: 第一个加数。
        b: 第二个加数。

    Returns:
        a + b 的结果。
    """
    return a + b


def register(mcp: FastMCP) -> None:
    """把本模块的工具挂到 mcp 实例上(在 server.main() 里调用)。

    设计:工具是普通函数,注册与实现分离 —— 单测不用启动协议层。
    """
    mcp.tool()(hello)
    mcp.tool()(add)
