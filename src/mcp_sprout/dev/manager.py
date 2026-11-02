"""面板核心:发现启动配置、拉起用户 server、桥接 MCP 会话。

架构(PLAN §5):
    [浏览器] --HTTP/WS--> [FastAPI 面板进程] --ClientSession--> [用户 server stdio 管道]

进程管理交给官方 stdio_client:
- Windows 下用 Job Objects 管理进程树(面板退出不留孤儿 server 进程)
- errlog 参数接 LogSink:anyio 把子进程 stderr 灌进这个 TextIO,
  日志行经 EventBus 广播给前端的 /ws/logs

时间线:EventBus 记录「连接 / 调用请求 / 调用响应 / 错误」事件,
前端 /ws/events 订阅,实时排布(PLAN §5 的 JSON-RPC 时间线)。
"""
import asyncio
import json
import os
import time
import tomllib
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ServerError(RuntimeError):
    """面板业务错误:给前端看的清晰提示。"""


@dataclass(frozen=True)
class LaunchConfig:
    """用户 server 的启动方式(从 .mcp.json 或 pyproject.toml 里发现)。"""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str = "."
    source: str = ""


def discover_launch(project_dir: Path) -> LaunchConfig:
    """在项目目录里发现 server 启动命令。

    优先级:
    1. `.mcp.json` 的第一个 mcpServers 条目(mcp-sprout 生成的项目自带,
       里面就是 `uv run --directory . <name>`,连启动方式都不需要猜)
    2. `pyproject.toml` 的 [project.scripts] 第一个入口(用 uv run 起)
    """
    mcp_json = project_dir / ".mcp.json"
    if mcp_json.is_file():
        data = json.loads(mcp_json.read_text(encoding="utf-8"))
        for entry in (data.get("mcpServers") or {}).values():
            if "command" in entry:
                return LaunchConfig(
                    command=entry["command"],
                    args=entry.get("args", []),
                    env=entry.get("env"),
                    cwd=str(project_dir),
                    source=".mcp.json",
                )
    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = (data.get("project") or {}).get("scripts") or {}
        if scripts:
            name = next(iter(scripts))
            return LaunchConfig(
                command="uv",
                args=["run", "--directory", ".", name],
                cwd=str(project_dir),
                source=f"pyproject.toml → [project.scripts] {name}",
            )
    raise ServerError(
        f"目录 {project_dir} 里没找到 .mcp.json 或 pyproject.toml 的 [project.scripts]。"
        "请用 mcp-sprout new 生成一个项目,或在项目根目录下运行 mcp-sprout dev。"
    )


def _dump(obj: Any) -> Any:
    """把 pydantic 模型(或任意对象)转成可 JSON 化的 dict。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


class LogSink:
    """喂给 stdio_client(errlog=...) 的 TextIO:把子进程 stderr 收进 OS 管道。

    关键认知:subprocess.Popen 对 errlog 这类对象只认 **fileno()** ——
    它把子进程的 stderr 直接指向该句柄,从不调用 write()。
    所以 LogSink 是一个"持有管道写端 fd"的对象,读端由 EventBus 的
    drain 任务在事件循环里读(os.read 阻塞在线程里,经 to_thread 桥接)。
    """

    def __init__(self) -> None:
        self._read_fd, self._write_fd = os.pipe()

    def fileno(self) -> int:
        return self._write_fd

    @property
    def read_fd(self) -> int:
        return self._read_fd

    def write(self, text: str) -> int:  # 防御性兜底:subprocess 不会走这里
        return os.write(self._write_fd, text.encode("utf-8", "replace"))

    def flush(self) -> None:
        pass

    def close_write(self) -> None:
        try:
            os.close(self._write_fd)
        except OSError:
            pass

    def close_read(self) -> None:
        try:
            os.close(self._read_fd)
        except OSError:
            pass


class EventBus:
    """面板事件/日志总线:时间线事件 + stderr 日志行,WebSocket 订阅分发。

    两条来源:
    - 时间线事件:manager(async 上下文)直接发布
    - 日志行:LogSink(同步线程)→ 线程安全队列 → drain 任务转发布
    """

    def __init__(self, limit: int = 300) -> None:
        self._limit = limit
        self._events: list[dict] = []
        self._logs: list[dict] = []
        self._sink: LogSink | None = None
        self._drain_task: asyncio.Task | None = None
        self._event_subscribers: set[asyncio.Queue] = set()
        self._log_subscribers: set[asyncio.Queue] = set()

    def start(self) -> None:
        """必须在运行中的事件循环里调用(manager.start 里)。"""
        self._sink = LogSink()
        self._drain_task = asyncio.create_task(self._drain())

    def make_sink(self) -> LogSink:
        assert self._sink is not None, "EventBus.start() 要先于 make_sink()"
        return self._sink

    def _read_chunk(self) -> bytes | None:
        """阻塞读管道(跑在 to_thread 的线程里);EOF/读端被关 → None。"""
        try:
            return os.read(self._sink.read_fd, 65536)
        except OSError:
            return None

    async def _drain(self) -> None:
        """管道 → 行分割 → 发布。EOF 后自然退出(见 stop() 注释)。"""
        buf = ""
        while True:
            chunk = await asyncio.to_thread(self._read_chunk)
            if not chunk:  # EOF(b"")或异常(None)
                break
            buf += chunk.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line.strip():
                    self.add_log(line.rstrip("\r"))

    def add_log(self, line: str) -> None:
        entry = {"ts": _now(), "line": line}
        self._logs.append(entry)
        del self._logs[: -self._limit]
        self._broadcast(self._log_subscribers, {"type": "log", "log": entry})

    def event(self, **payload: Any) -> None:
        entry = {"ts": _now(), **payload}
        self._events.append(entry)
        del self._events[: -self._limit]
        self._broadcast(self._event_subscribers, {"type": "event", "event": entry})

    def history_events(self) -> list[dict]:
        return list(self._events)

    def history_logs(self) -> list[dict]:
        return list(self._logs)

    def subscribe_events(self) -> asyncio.Queue:
        subscriber: asyncio.Queue = asyncio.Queue()
        self._event_subscribers.add(subscriber)
        return subscriber

    def unsubscribe_events(self, subscriber: asyncio.Queue) -> None:
        self._event_subscribers.discard(subscriber)

    def subscribe_logs(self) -> asyncio.Queue:
        subscriber: asyncio.Queue = asyncio.Queue()
        self._log_subscribers.add(subscriber)
        return subscriber

    def unsubscribe_logs(self, subscriber: asyncio.Queue) -> None:
        self._log_subscribers.discard(subscriber)

    @staticmethod
    def _broadcast(subscribers: set[asyncio.Queue], msg: dict) -> None:
        for subscriber in subscribers:
            subscriber.put_nowait(msg)

    async def stop(self) -> None:
        if self._drain_task is not None:
            # Windows 上不能 cancel 阻塞在 os.read 里的线程(取消不唤醒线程,
            # 线程池 atexit join 会把进程挂死)。关掉本进程的写端:
            # 此时子进程已被 manager 终止 → reader 读到 EOF 自然退出;
            # 若超时,再关读端,让阻塞的 os.read 以 OSError 失败退出。
            self._sink.close_write()
            try:
                await asyncio.wait_for(self._drain_task, 3)
            except TimeoutError:
                self._sink.close_read()
                await asyncio.gather(self._drain_task, return_exceptions=True)
            finally:
                self._drain_task = None
                self._sink = None


class ServerManager:
    """管理一个用户 server 的完整生命周期:启动 → 会话 → 停止。

    并发模型:所有操作(start/stop/restart/call)都提交给专属 owner
    任务串行执行,不在调用者任务里直接跑。原因(坑12):anyio 的
    cancel scope 绑定任务身份 —— stdio_client 内部的 task group
    在哪个任务里进入,就必须在同一个任务里退出,否则抛
    "Attempted to exit cancel scope in a different task"。
    owner 串行化还顺带消灭了"防抖重启 vs lifespan 关停"的并发竞争。
    """

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir)
        self.launch: LaunchConfig | None = None
        self.session: ClientSession | None = None
        self.last_error: str | None = None
        self.bus = EventBus()
        self.generation = 0  # 每次成功启动 +1,前端据此感知"server 换过进程"
        self._stack: AsyncExitStack | None = None
        self._sink: LogSink | None = None
        self._ops: asyncio.Queue | None = None
        self._owner: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.session is not None

    # ---- owner 任务:操作队列 + 串行执行 ----

    def _spawn_owner(self) -> None:
        """必须在运行中的事件循环里调用(第一次 start 时自动触发)。"""
        self._ops = asyncio.Queue()
        self._owner = asyncio.create_task(self._owner_run())

    async def _owner_run(self) -> None:
        while True:
            fut, op = await self._ops.get()
            if op is None:  # close() 的哨兵
                fut.set_result(None)
                return
            try:
                fut.set_result(await op())
            except BaseException as exc:
                fut.set_exception(exc)

    def _submit(self, op: Callable[[], Awaitable]) -> asyncio.Future:
        """把操作交给 owner 任务执行;返回的 future 承载结果/异常。"""
        assert self._ops is not None, "要先 start() 一次以生成 owner"
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._ops.put_nowait((fut, op))
        return fut

    async def start(self) -> list[dict]:
        if self._owner is None:
            self._spawn_owner()
        return await self._submit(self._start)

    async def list_tools(self) -> list[dict]:
        return await self._submit(self._list_tools)

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._submit(lambda: self._call_tool(name, arguments))

    async def restart(self) -> list[dict]:
        return await self._submit(self._restart)

    async def stop(self) -> None:
        if self._owner is None:
            return
        await self._submit(self._stop)

    async def close(self) -> None:
        """停掉 owner 任务(lifespan 收尾时调用)。"""
        if self._owner is not None:
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._ops.put_nowait((fut, None))
            await fut
            self._owner = None

    # ---- 以下实现只在 owner 任务里运行 ----

    async def _start(self) -> list[dict]:
        """拉起用户 server 并建立会话;失败记 last_error 并抛 ServerError。"""
        self.last_error = None
        self.bus.start()
        try:
            self.launch = discover_launch(self.project_dir)
            params = StdioServerParameters(
                command=self.launch.command,
                args=self.launch.args,
                env=self.launch.env,
                cwd=self.launch.cwd,
            )
            self._stack = AsyncExitStack()
            self._sink = self.bus.make_sink()
            read, write = await self._stack.enter_async_context(
                stdio_client(params, errlog=self._sink)
            )
            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            command = f"{self.launch.command} {' '.join(self.launch.args)}"
            self.generation += 1
            self.bus.add_log(f"server 已启动:{command}")
            self.bus.event(kind="info", message=f"server 已连接:{command}")
            return await self._list_tools()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.bus.add_log(f"server 启动失败:{self.last_error}")
            self.bus.event(kind="error", message=self.last_error)
            await self._stop()  # 内部直接调:此刻就身处 owner 任务,不能再走 _submit(会死锁)
            raise ServerError(self.last_error) from exc

    async def _list_tools(self) -> list[dict]:
        assert self.session is not None, "server 未启动"
        tools = await self.session.list_tools()
        return [tool.model_dump(mode="json") for tool in tools.tools]

    async def _call_tool(self, name: str, arguments: dict) -> dict:
        assert self.session is not None, "server 未启动"
        started = time.monotonic()
        self.bus.event(kind="request", method="tools/call", name=name, arguments=arguments)
        try:
            result = await self.session.call_tool(name, arguments or {})
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 1)
            self.bus.event(
                kind="error",
                method="tools/call",
                name=name,
                message=f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed_ms,
            )
            raise
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        self.bus.event(
            kind="response",
            method="tools/call",
            name=name,
            is_error=result.isError,
            elapsed_ms=elapsed_ms,
        )
        return {
            "name": name,
            "isError": result.isError,
            "content": [_dump(item) for item in result.content],
            "structuredContent": _dump(result.structuredContent),
            "elapsedMs": elapsed_ms,
        }

    async def _restart(self) -> list[dict]:
        """停旧进程、起新进程(文件变更自动重启用)。"""
        await self._stop()
        return await self._start()

    async def _stop(self) -> None:
        """关会话 + 终止进程(stdio_client 退出时会走 MCP 关停序列)。"""
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self.session = None
        self._sink = None
        await self.bus.stop()
