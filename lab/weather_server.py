"""最小 MCP Server —— M0 实验:接入 Claude Code。

重要(这就是 proto 协议的第一个坑):
- stdio 传输下,标准输出是协议通道,绝对不要用 print()
- 调试日志统一走 stderr
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Weather")


@mcp.tool()
def get_weather(city: str) -> str:
    """查询指定城市今天的天气。"""
    return f"{city} 今天 23°C,晴"


if __name__ == "__main__":
    mcp.run()