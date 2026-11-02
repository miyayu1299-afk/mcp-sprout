"""mcp-sprout 命令行入口。

v1(M2):
- new 支持交互问答(Questionary):缺 --desc / --template 时在终端里问
- 模板变体:basic(工具示例 + 错误兜底)/ full(再加资源示例)
"""
import os
import sys
from pathlib import Path

import questionary
import typer
from questionary import Choice
from rich.console import Console
from rich.tree import Tree

from mcp_sprout.generator import GenerationError, default_description, generate_project

app = typer.Typer(
    name="mcp-sprout",
    help="从生成到调试:MCP Server 开发一条龙",
    no_args_is_help=True,
)
console = Console()


def _terminal_ok() -> bool:
    """判断当前终端能不能跑 questionary 问答。

    坑7:Git Bash(mintty)里 isatty() 为真,但 prompt_toolkit 拿不到
    Windows console handle,直接 NoConsoleScreenBufferError——
    isatty() 只能测"是不是终端",测不出"是什么终端"。
    这类环境(管道/CI/Git Bash)一律降级参数式,不做交互。
    """
    if not sys.stdin.isatty():
        return False
    if sys.platform == "win32" and os.environ.get("TERM", "").startswith("xterm"):
        return False  # mintty/Cygwin 类伪终端,不是真 Windows console
    return True


def _ask_missing(
    name: str, desc: str | None, template: str | None
) -> tuple[str | None, str]:
    """交互问答(v1):只在真实终端里问;其他环境降级走默认值。

    返回的 template 保证非 None:描述缺省由 generator 兜底,
    但模板类型必须在进 generator 前落到 concrete 值(否则生成时报"模板类型 None")。
    """
    if _terminal_ok():
        try:
            if desc is None:
                desc = questionary.text("项目描述?", default=default_description(name)).ask()
            if template is None:
                template = questionary.select(
                    "模板类型?",
                    choices=[
                        Choice("基础 —— 工具示例 + 错误兜底", "basic"),
                        Choice("完整 —— 再加资源(resources)示例", "full"),
                    ],
                ).ask()
        except Exception as exc:  # 任何终端问题都不许炸掉生成主流程:降级 + 提示
            console.print(f"[yellow][!][/yellow] 交互问答不可用({exc!r}),改用默认值")
    return desc, template or "basic"


def _print_created(dest_root: Path, files: list[Path], template: str) -> None:
    """把生成的文件按目录树打出来(rich.Tree)。

    注意:标记用 ASCII —— 中文 Windows 控制台是 GBK 编码,
    ✔/✗ 等非 GBK 字符写出时直接 UnicodeEncodeError(坑6)
    """
    tree = Tree(
        f"[bold green][OK][/bold green] 已生成 [bold]{dest_root.name}/[/bold]"
        f"(模板 {template}),共 {len(files)} 个文件"
    )
    nodes: dict[str, Tree] = {}
    for path in sorted(files):
        parts = path.relative_to(dest_root).parts
        node, current_dir = tree, dest_root
        for part in parts[:-1]:
            current_dir = current_dir / part
            key = str(current_dir)
            if key not in nodes:
                nodes[key] = node.add(f"[blue]{part}/[/blue]")
            node = nodes[key]
        node.add(parts[-1])
    console.print(tree)


@app.command()
def new(
    name: str = typer.Argument(..., help="项目名,如 my-server(小写字母/数字/连字符)"),
    desc: str = typer.Option(None, "--desc", "-d", help="一句话描述;不传则交互询问"),
    template: str = typer.Option(
        None, "--template", "-t", help="模板类型:basic(默认)/full;不传则交互选择"
    ),
) -> None:
    """生成一个规范的 MCP Server 项目:日志/异常兜底/测试/CI 全内置。"""
    desc, template = _ask_missing(name, desc, template)
    try:
        created = generate_project(name=name, desc=desc, template=template, base_dir=Path.cwd())
    except GenerationError as exc:
        console.print(f"[bold red][FAIL][/bold red] {exc}")
        raise typer.Exit(code=1) from None

    _print_created(Path.cwd() / name, created, template or "basic")
    console.print()
    console.print("[bold]下一步:[/bold]")
    console.print(f"  cd {name}")
    console.print("  uv sync          # 装依赖,自动建 .venv")
    console.print(f"  uv run {name}     # stdio 模式启动,等待 MCP 客户端")
    console.print("  接 Claude Code:项目自带 .mcp.json,宿主直接读;或见 README 两行命令")


@app.command()
def version() -> None:
    """打印 mcp-sprout 版本。

    注:它还有一个隐藏职责 —— 让 app 拥有第二个命令,
    否则 Typer 会把唯一的命令扁平化到 app 层(坑5,见 pitfalls.md)。
    """
    from mcp_sprout import __version__

    console.print(f"mcp-sprout {__version__}")


@app.command()
def dev(
    project: Path = typer.Option(
        ".", "--project", "-p", help="项目目录(含 .mcp.json 或 pyproject.toml)"
    ),
    port: int = typer.Option(8668, "--port", help="面板端口"),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="启动后自动打开浏览器"
    ),
) -> None:
    """起调试面板:工具列表 + 按 inputSchema 自动渲染表单 + 调用结果。

    浏览器访问 http://127.0.0.1:<port>;面板是官方 ClientSession 客户端,
    通过 stdio 管道拉起并驱动项目里的 MCP server。
    """
    import webbrowser

    import uvicorn

    from mcp_sprout.dev.manager import ServerError, discover_launch
    from mcp_sprout.dev.web import create_app

    project_dir = project.resolve()
    try:
        launch = discover_launch(project_dir)
    except ServerError as exc:
        console.print(f"[bold red][FAIL][/bold red] {exc}")
        raise typer.Exit(code=1) from None

    url = f"http://127.0.0.1:{port}"
    console.print(f"[OK] 面板: {url}  (项目: {project_dir})")
    console.print(f"[OK] 将启动: {launch.command} {' '.join(launch.args)}")
    console.print("[OK] Ctrl+C 停止面板(server 进程会一并结束,不会留孤儿)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # 打不开浏览器不影响面板本身
    uvicorn.run(create_app(project_dir), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    app()  # pragma: no cover - 入口守卫,仅直接运行时执行
