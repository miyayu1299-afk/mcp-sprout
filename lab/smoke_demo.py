"""生成物验收冒烟:用官方 ClientSession 按 .mcp.json 的连接方式连生成的 demo。

用法:python smoke_demo.py <项目目录> <项目名> [basic|full]
- basic:检查 3 个工具(含 divide 错误路径)
- full:额外检查资源模板(list_resource_templates + read_resource)
"""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    demo_dir = sys.argv[1]
    proj = sys.argv[2]
    template = sys.argv[3] if len(sys.argv) > 3 else "basic"

    params = StdioServerParameters(command="uv", args=["run", "--directory", demo_dir, proj])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("tools/list →", names)
            assert names == ["add", "divide", "hello"], f"工具列表不对:{names}"

            result = await session.call_tool("hello", {"name": "MCP"})
            print("call hello →", result.content[0].text)
            assert result.content[0].text == "Hello, MCP!"

            result = await session.call_tool("add", {"a": 1, "b": 2})
            print("call add →", result.content[0].text)
            assert result.content[0].text == "3"

            result = await session.call_tool("divide", {"a": 10, "b": 2})
            print("call divide 10/2 →", result.content[0].text)
            assert result.content[0].text == "5"

            err = await session.call_tool("divide", {"a": 1, "b": 0})
            print("call divide 1/0 →", err.content[0].text, "| isError:", err.isError)
            assert err.isError  # 错误兜底:客户端拿到 isError,进程不崩(坑4)

            if template == "full":
                templates = await session.list_resource_templates()
                uris = sorted(t.uriTemplate for t in templates.resourceTemplates)
                print("resource_templates →", uris)
                assert "notes://{key}" in uris
                content = await session.read_resource("notes://welcome")
                print("read notes://welcome →", content.contents[0].text)
                assert "欢迎使用" in content.contents[0].text

            print(f"SMOKE-OK({template}):生成的项目跑通,协议层零报错")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError:
        sys.exit(1)