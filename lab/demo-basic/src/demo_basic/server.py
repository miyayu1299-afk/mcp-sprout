"""demo-basic —— MCP Server 入口。

stdio 模式的铁律(踩坑实录):
1. 标准输出是协议通道,严禁 print();日志一律走 stderr。
   小 print 会被缓冲吞掉、大 print 会污染协议,且污染时机不可预测。
2. FastMCP 1.x 构造只传名字 —— 不要照 2.x 教程抄 version= 参数,会直接 TypeError。
3. 工具函数抛异常进程不会崩(SDK 会包成 isError 响应),但堆栈不会自动落日志,
   所以 main() 外层做统一异常兜底;工具级兜底见 tools/example.py 的 with_error_logging。
"""
import logging
import sys

from mcp.server.fastmcp import FastMCP

from demo_basic.tools.example import register as register_example_tools

# 日志走 stderr:stdout 是 JSON-RPC 协议通道,碰了就坏
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("demo_basic")

mcp = FastMCP("Demo Basic")


def main() -> None:
    """入口:注册工具/资源 + 异常兜底,启动失败留日志不留黑盒。"""
    register_example_tools(mcp)
    try:
        mcp.run()
    except Exception:
        logger.exception("server 异常退出")
        raise


if __name__ == "__main__":
    main()