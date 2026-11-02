"""示范工具:写新工具照这个格式抄。

docstring 规范(重要,客户端 AI 靠它理解你的工具):
- 第一行:一句话说清做什么
- 中间:参数含义、返回什么、什么情况报错
"""
import functools
import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("demo_full")


def with_error_logging(fn):
    """错误兜底装饰器(坑4 对策)。

    工具抛异常时 SDK 只把消息包进 isError 响应,**服务端堆栈不落日志**。
    这个装饰器先 logger.exception 留堆栈,再原样抛出,由 SDK 转客户端错误。
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("工具 %s 执行失败", fn.__name__)
            raise

    return wrapper


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


def divide(a: int, b: int) -> int:
    """计算 a 整除 b(错误处理示范工具)。

    Args:
        a: 被除数。
        b: 除数,不能为 0。

    Returns:
        a // b 的结果。

    Raises:
        ValueError: b 为 0 时抛出 —— 客户端会收到 isError 响应(进程不会崩),
            服务端堆栈由 with_error_logging 落日志。
    """
    if b == 0:
        raise ValueError("除数不能为 0")
    return a // b


def register(mcp: FastMCP) -> None:
    """把本模块的工具挂到 mcp 实例上(在 server.main() 里调用)。

    设计:工具是普通函数,注册与实现分离 —— 单测不用启动协议层;
    所有工具统一套 with_error_logging:客户端友好(isError 响应)+ 服务端可查(堆栈日志)。
    """
    for fn in (hello, add, divide):
        mcp.tool()(with_error_logging(fn))