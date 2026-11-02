"""资源示例:MCP 的 Resource 概念(客户端按 URI 读取的数据,与工具互补)。

- 工具 = 客户端"调用执行"(有参数、有返回值)
- 资源 = 客户端"按 URI 读取"(内容可静态可动态,这里示范带参数的 URI 模板)

写新资源照这个格式抄:纯函数 + register() 挂载。
"""
from mcp.server.fastmcp import FastMCP

# 静态数据源(字典)。真实项目里可以是数据库、文件、外部 API
NOTES = {
    "welcome": "欢迎使用 demo-full,这是一个 MCP 资源示例。",
    "usage": "URI 模板 notes://{key} 里的 {key} 是参数,调用时替换成真实键。",
}


def get_note(key: str) -> str:
    """按 key 读取便签。

    Args:
        key: 便签键(见 NOTES 字典)。

    Returns:
        便签内容;key 不存在时返回提示文本。
    """
    return NOTES.get(key, f"(未找到便签 {key})")


def register(mcp: FastMCP) -> None:
    """把资源挂到 mcp 实例上(在 server.main() 里调用)。

    URI 模板 notes://{key}:花括号部分是参数,函数签名要一一对应。
    """
    mcp.resource("notes://{key}")(get_note)