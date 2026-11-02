# mcp-sprout

从生成到调试:MCP Server 开发一条龙。脚手架为入口,调试面板为核心。

## 安装(开发中)

```bash
uv venv
uv pip install -e . --group dev
```

## 使用

```bash
mcp-sprout new my-server                    # 交互问答:描述 + 模板类型
mcp-sprout new my-server -d "..." -t full   # 参数式:直接按参数生成
```

模板变体:`basic`(工具示例 + 错误兜底)/ `full`(再加资源示例)。
生成的模板自带:日志走 stderr、异常兜底、`mcp<2` 锁版、pytest + ruff CI。

路线图与设计决策见 `PLAN.md`。
