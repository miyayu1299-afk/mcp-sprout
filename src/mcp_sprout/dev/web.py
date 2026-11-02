"""面板 Web 层:FastAPI 路由 + WebSocket + 静态页。

路由:
- GET  /          面板页面(static/index.html)
- GET  /api/state 连接状态 + 工具列表(含 inputSchema,前端据此自动渲染表单)
- POST /api/call  调用工具,返回 content/structuredContent/isError/耗时
- WS   /ws/events JSON-RPC 时间线:先推历史,再实时推事件(PLAN §5)
- WS   /ws/logs   server stderr 日志流:先推历史,再实时推行
"""
import asyncio
from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mcp_sprout.dev.manager import ServerError, ServerManager
from mcp_sprout.dev.watcher import ProjectWatcher


class CallRequest(BaseModel):
    name: str
    arguments: dict = {}


def _add_command(manager: ServerManager) -> str | None:
    """构造"接入 Claude Code"的命令(宿主配置块,PLAN §5 的一键复制)。

    .mcp.json 里的启动参数是相对路径(`--directory .`),这里把 `.`
    替换成项目绝对路径,命令在任何目录下粘贴都能用。
    """
    if manager.launch is None:
        return None
    args = []
    for arg in manager.launch.args:
        text = str(manager.project_dir) if arg == "." else arg
        args.append(f'"{text}"' if " " in text else text)
    return (
        f"claude mcp add {manager.project_dir.name} --scope user"
        f" -- {manager.launch.command} {' '.join(args)}"
    )


async def _forward(subscriber: asyncio.Queue, websocket: WebSocket) -> None:
    """把订阅队列里的消息转发到 WebSocket;发送失败(断开)就退出。"""
    while True:
        msg = await subscriber.get()
        try:
            await websocket.send_json(msg)
        except Exception:
            return


def create_app(project_dir: Path) -> FastAPI:
    manager = ServerManager(project_dir)

    async def _restart_from_change() -> None:
        """文件变更回调:重启并写时间线;失败也记事件(改好文件会再次触发)。"""
        try:
            tools = await manager.restart()
            manager.bus.event(
                kind="restart", message=f"文件变更 → server 已重启({len(tools)} 个工具)"
            )
        except ServerError as exc:
            manager.bus.event(kind="restart", message=f"文件变更 → 重启失败:{exc}")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # watcher 先于 manager 启动:即使 server 起不来,改好文件也能自动重试
        watcher = ProjectWatcher(project_dir, _restart_from_change)
        watcher.start()
        try:
            await manager.start()
        except ServerError:
            pass  # 失败信息在 /api/state 里报给前端,面板本身照常服务
        yield
        watcher.stop()
        try:
            await manager.stop()
        finally:
            await manager.close()

    app = FastAPI(title="mcp-sprout dev", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = resources.files("mcp_sprout.dev").joinpath("static", "index.html")
        return page.read_text(encoding="utf-8")

    @app.get("/api/state")
    async def state() -> dict:
        try:
            tools = await manager.list_tools() if manager.running else []
        except Exception:
            tools = []
        command = None
        if manager.launch is not None:
            command = f"{manager.launch.command} {' '.join(manager.launch.args)}"
        return {
            "running": manager.running,
            "error": manager.last_error,
            "project": str(manager.project_dir),
            "command": command,
            "generation": manager.generation,
            "add_command": _add_command(manager),
            "tools": tools,
        }

    @app.post("/api/call")
    async def call(req: CallRequest) -> dict:
        if not manager.running:
            raise HTTPException(status_code=503, detail=manager.last_error or "server 未运行")
        try:
            return await manager.call_tool(req.name, req.arguments)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc

    async def _ws_stream(websocket: WebSocket, history: dict, subscribe, unsubscribe) -> None:
        """WS 通用流程:accept → 推历史 → 订阅转发 → 断开清理。

        receive_text() 循环是断开检测:客户端会定时发 keepalive;
        sender 任务负责转发,发送失败自己退出,receive 抛异常后收尾。
        """
        await websocket.accept()
        await websocket.send_json(history)
        subscriber = subscribe(manager.bus)
        sender = asyncio.create_task(_forward(subscriber, websocket))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass
            unsubscribe(manager.bus, subscriber)

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await _ws_stream(
            websocket,
            {"type": "history", "events": manager.bus.history_events()},
            lambda bus: bus.subscribe_events(),
            lambda bus, q: bus.unsubscribe_events(q),
        )

    @app.websocket("/ws/logs")
    async def ws_logs(websocket: WebSocket) -> None:
        await _ws_stream(
            websocket,
            {"type": "history", "logs": manager.bus.history_logs()},
            lambda bus: bus.subscribe_logs(),
            lambda bus, q: bus.unsubscribe_logs(q),
        )

    return app
