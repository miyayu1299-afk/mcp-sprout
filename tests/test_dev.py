"""dev 面板单测:启动配置发现 + ServerManager 拉起真 server + Web API 全链路。"""
import asyncio
import json
import os
import sys
import textwrap
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mcp_sprout.cli import app
from mcp_sprout.dev.manager import EventBus, LogSink, ServerError, ServerManager, discover_launch
from mcp_sprout.dev.web import _add_command, _forward, create_app

# 测试用最小 MCP server:由 manager 拉起的子进程执行(用测试进程自己的 python)
ECHO_SERVER = textwrap.dedent('''
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("echo-test")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """两数相加。"""
        return a + b

    @mcp.tool()
    def greet(name: str = "MCP") -> str:
        """问好。"""
        return f"Hello, {name}!"

    if __name__ == "__main__":
        mcp.run()
''')


@pytest.fixture
def echo_project(tmp_path) -> Path:
    """一个带 .mcp.json 的最小项目目录(等价于 mcp-sprout 生成的项目)。"""
    project = tmp_path / "echo"
    project.mkdir()
    (project / "server.py").write_text(ECHO_SERVER, encoding="utf-8")
    (project / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"echo": {"command": sys.executable, "args": ["server.py"]}}}),
        encoding="utf-8",
    )
    return project


def test_discover_from_mcp_json(echo_project) -> None:
    launch = discover_launch(echo_project)
    assert launch.command == sys.executable
    assert launch.args == ["server.py"]
    assert launch.cwd == str(echo_project)
    assert launch.source == ".mcp.json"


def test_discover_from_pyproject(tmp_path) -> None:
    project = tmp_path / "no-mcp-json"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        textwrap.dedent("""\
            [project]
            name = "x"
            version = "0.1.0"
            [project.scripts]
            x-server = "x.server:main"
        """),
        encoding="utf-8",
    )
    launch = discover_launch(project)
    assert launch.command == "uv"
    assert launch.args == ["run", "--directory", ".", "x-server"]
    assert launch.source.endswith("x-server")


def test_discover_nothing(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ServerError):
        discover_launch(empty)


def test_dev_command_bad_project(tmp_path) -> None:
    """CLI 层:dev 指向没有启动配置的目录 → [FAIL] + exit 1。"""
    empty = tmp_path / "nothing"
    empty.mkdir()
    result = CliRunner().invoke(app, ["dev", "--project", str(empty), "--no-open"])
    assert result.exit_code == 1
    assert "[FAIL]" in result.stdout


def test_dev_command_launches_uvicorn(echo_project, monkeypatch) -> None:
    """CLI 层:dev 命令体 = 发现配置 → 报启动信息 → 拉起 uvicorn。

    uvicorn 在函数体内 import(dev() 每次调用时读 sys.modules),
    所以用假模块替身拦截 run(),不真起服务器;webbrowser 同理,
    故意让 open 抛异常,验证"打不开浏览器不影响面板"的兜底。
    """
    calls = {}

    def fake_run(_app, **kwargs) -> None:
        calls.update(kwargs)

    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = fake_run
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    def fake_webbrowser_open(*_args, **_kwargs) -> None:
        raise OSError("no browser")

    fake_webbrowser = types.ModuleType("webbrowser")
    fake_webbrowser.open = fake_webbrowser_open
    monkeypatch.setitem(sys.modules, "webbrowser", fake_webbrowser)

    result = CliRunner().invoke(
        app, ["dev", "--project", str(echo_project), "--port", "9878"]
    )
    assert result.exit_code == 0
    assert "将启动" in result.stdout
    assert calls == {"host": "127.0.0.1", "port": 9878, "log_level": "warning"}


def test_manager_lifecycle(echo_project) -> None:
    """拉起真 server:list_tools / call_tool / 错误工具 / 停止。"""

    async def run() -> None:
        manager = ServerManager(echo_project)
        tools = await manager.start()
        assert manager.running
        assert [t["name"] for t in tools] == ["add", "greet"]
        add_schema = next(t for t in tools if t["name"] == "add")["inputSchema"]
        assert add_schema["required"] == ["a", "b"]
        greet_schema = next(t for t in tools if t["name"] == "greet")["inputSchema"]
        assert "required" not in greet_schema  # 有默认值的参数不进 required

        result = await manager.call_tool("add", {"a": 1, "b": 2})
        assert result["isError"] is False
        assert result["content"][0]["text"] == "3"
        assert result["elapsedMs"] >= 0

        greet = await manager.call_tool("greet", {})
        assert greet["content"][0]["text"] == "Hello, MCP!"

        await manager.stop()
        assert not manager.running

    asyncio.run(run())


def test_bus_timeline_and_logs(echo_project) -> None:
    """时间线埋点 + stderr 日志经 LogSink 进总线。"""

    async def run() -> None:
        manager = ServerManager(echo_project)
        await manager.start()
        await manager.call_tool("add", {"a": 1, "b": 2})
        # 时间线:连接 info + 调用请求 + 调用响应
        events = manager.bus.history_events()
        kinds = [(e["kind"], e.get("name")) for e in events]
        assert ("request", "add") in kinds
        assert ("response", "add") in kinds
        response = next(e for e in events if e["kind"] == "response")
        assert response["is_error"] is False
        assert response["elapsed_ms"] >= 0
        # 日志:合成启动行 + echo server 自己的 stderr 日志(经 LogSink 线程队列)
        for _ in range(50):  # 最多等 1s,给 stderr 拷贝线程时间
            if any("已启动" in log["line"] for log in manager.bus.history_logs()):
                break
            await asyncio.sleep(0.02)
        lines = [log["line"] for log in manager.bus.history_logs()]
        assert any("已启动" in line for line in lines)
        assert any("Processing request" in line for line in lines)
        await manager.stop()

    asyncio.run(run())


def test_ws_streams(echo_project) -> None:
    """WS 先推历史,调用后实时收到请求/响应事件与日志行。"""
    with TestClient(create_app(echo_project)) as client:
        with client.websocket_connect("/ws/events") as ws:
            first = ws.receive_json()
            assert first["type"] == "history"
            assert any(e["kind"] == "info" for e in first["events"])

            client.post("/api/call", json={"name": "add", "arguments": {"a": 3, "b": 4}}).json()
            got = {}
            for _ in range(10):
                msg = ws.receive_json()
                assert msg["type"] == "event"
                event = msg["event"]
                if event["kind"] in ("request", "response") and event.get("name") == "add":
                    got[event["kind"]] = event
                    if len(got) == 2:
                        break
            assert got["request"]["arguments"] == {"a": 3, "b": 4}
            assert got["response"]["is_error"] is False

        with client.websocket_connect("/ws/logs") as ws:
            first = ws.receive_json()
            assert first["type"] == "history"
            assert any("已启动" in log["line"] for log in first["logs"])


def test_manager_restart(echo_project) -> None:
    """停旧起新:generation 递增,新进程可正常调用。

    restart/stop 故意从另一个任务发起(等价于 watcher 防抖任务调用):
    anyio 的 cancel scope 绑定任务身份(坑12),真正的停/起必须
    在 manager 的 owner 任务里执行,而不是调用者任务。
    """

    async def run() -> None:
        manager = ServerManager(echo_project)
        await manager.start()
        assert manager.generation == 1
        await asyncio.create_task(manager.restart())
        assert manager.generation == 2
        assert manager.running
        result = await manager.call_tool("add", {"a": 5, "b": 6})
        assert result["content"][0]["text"] == "11"
        await asyncio.create_task(manager.stop())

    asyncio.run(run())


def test_watcher_auto_restart(echo_project) -> None:
    """改文件 → 防抖重启 → generation 增加,新进程可调用。"""
    import time as time_mod

    with TestClient(create_app(echo_project)) as client:
        assert client.get("/api/state").json()["generation"] == 1
        with (echo_project / "server.py").open("a", encoding="utf-8") as fh:
            fh.write("\n# touch\n")
        deadline = time_mod.monotonic() + 15
        generation = 1
        while time_mod.monotonic() < deadline:
            generation = client.get("/api/state").json()["generation"]
            if generation > 1:
                break
            time_mod.sleep(0.3)
        assert generation > 1, "文件变更未触发自动重启"
        result = client.post(
            "/api/call", json={"name": "add", "arguments": {"a": 2, "b": 3}}
        ).json()
        assert result["content"][0]["text"] == "5"


def test_web_api(echo_project) -> None:
    """面板 HTTP 全链路:状态 → 工具列表 → 表单参数 → 调用结果。"""
    with TestClient(create_app(echo_project)) as client:
        state = client.get("/api/state").json()
        assert state["running"] is True
        assert state["error"] is None
        assert [t["name"] for t in state["tools"]] == ["add", "greet"]
        assert "claude mcp add echo --scope user" in state["add_command"]

        page = client.get("/")
        assert page.status_code == 200
        assert "调试面板" in page.text

        result = client.post(
            "/api/call", json={"name": "add", "arguments": {"a": 1, "b": 2}}
        ).json()
        assert result["isError"] is False
        assert result["content"][0]["text"] == "3"

        bad = client.post("/api/call", json={"name": "no-such-tool", "arguments": {}})
        assert bad.status_code == 200  # 未知工具不是协议错误:server 返回 isError 响应(坑4)
        assert bad.json()["isError"] is True
        assert "Unknown tool" in bad.json()["content"][0]["text"]


# ---- M4 覆盖率补漏:错误路径与防御分支 ----


class _BoomManager(ServerManager):
    """list_tools / call_tool 直接抛异常:验证 API 层的降级兜底。"""

    async def list_tools(self) -> list[dict]:
        raise RuntimeError("list boom")

    async def call_tool(self, name: str, arguments: dict) -> dict:
        raise RuntimeError("call boom")


def test_logsink_write_flush_roundtrip() -> None:
    """LogSink 的 write/flush 是防御兜底(subprocess 只认 fileno 不认 write,坑11)。"""
    sink = LogSink()
    assert sink.write("hello\n") == 6
    assert sink.flush() is None
    assert os.read(sink.read_fd, 100) == b"hello\n"
    sink.close_write()
    sink.close_read()


def test_logsink_double_close_no_crash() -> None:
    sink = LogSink()
    sink.close_write()
    sink.close_write()  # 第二次:fd 已关,OSError 被吞(幂等关停)
    sink.close_read()
    sink.close_read()


def test_read_chunk_returns_none_on_oserror() -> None:
    """读端已关 → os.read 抛 OSError → 返回 None(drain 任务以 EOF 形式退出)。"""
    bus = EventBus()
    sink = LogSink()
    bus._sink = sink
    sink.close_read()
    assert bus._read_chunk() is None
    sink.close_write()


def test_eventbus_stop_timeout_path(monkeypatch) -> None:
    """坑10 超时分支的**控制流**(跨平台,CI 可跑):close_read 被调用、drain 收尸。

    真实"关读端唤醒阻塞 os.read"是 Windows 平台语义,在测试
    test_eventbus_stop_timeout_closes_read_end_windows 里单独验证;
    这里用假 sink + 可控 drain 任务测分支本身,Linux CI 也能过。
    """

    async def fake_wait_for(_task, _timeout):
        raise TimeoutError

    async def run() -> None:
        closed = []

        class _FakeSink:
            def close_write(self) -> None:
                closed.append("write")

            def close_read(self) -> None:
                closed.append("read")

        bus = EventBus()
        bus._sink = _FakeSink()
        bus._drain_task = asyncio.create_task(asyncio.sleep(0.02))  # 收尸时自然结束

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        await bus.stop()
        assert closed == ["write", "read"]
        assert bus._drain_task is None
        assert bus._sink is None

    asyncio.run(run())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 特有的 fd 语义:Linux 上 close 不打断已阻塞的 read")
def test_eventbus_stop_timeout_closes_read_end_windows(monkeypatch) -> None:
    """坑10 真实机制(仅 Windows):读端迟迟不 EOF → 3s 超时 → 关读端,
    阻塞的 os.read 以 OSError 失败退出。dup 写端模拟"别人还持有着"。

    Linux 上 close(fd) 不会唤醒另一个线程里已阻塞的 read()(file
    description 被 read 引用着),同样的代码会永远挂死 —— 所以这个
    真实机制只在 Windows 验证,CI 的分支逻辑见上面那个测试。
    """

    async def run() -> None:
        bus = EventBus()
        bus.start()
        keep_open = os.dup(bus._sink._write_fd)  # 写端仍被持有,EOF 永远不会来

        async def fake_wait_for(_task, _timeout):
            raise TimeoutError

        monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)
        await bus.stop()
        assert bus._drain_task is None
        assert bus._sink is None
        os.close(keep_open)

    asyncio.run(run())


def test_manager_stop_before_start_noop(echo_project) -> None:
    """从没 start 过就 stop:直接返回,不该报错。"""

    async def run() -> None:
        manager = ServerManager(echo_project)
        await manager.stop()

    asyncio.run(run())


def test_manager_start_failure(tmp_path) -> None:
    """启动失败:last_error 记录 + 时间线 error 事件 + 抛 ServerError;
    owner 任务不受影响,第二次 start 同样干净失败。"""
    empty = tmp_path / "empty"
    empty.mkdir()

    async def run() -> None:
        manager = ServerManager(empty)
        with pytest.raises(ServerError):
            await manager.start()
        assert not manager.running
        assert manager.last_error
        assert any(e["kind"] == "error" for e in manager.bus.history_events())
        with pytest.raises(ServerError):
            await manager.start()  # owner 还活着,不是一炸就死

    asyncio.run(run())


def test_call_tool_transport_error(echo_project, monkeypatch) -> None:
    """调用中途传输断开:时间线记 error 事件(含工具名与耗时),异常照抛。"""

    async def run() -> None:
        manager = ServerManager(echo_project)
        await manager.start()

        async def boom(_name, _arguments=None):
            raise RuntimeError("transport gone")

        monkeypatch.setattr(manager.session, "call_tool", boom)
        with pytest.raises(RuntimeError, match="transport gone"):
            await manager.call_tool("add", {"a": 1, "b": 2})
        errors = [e for e in manager.bus.history_events() if e["kind"] == "error"]
        assert errors and errors[-1]["name"] == "add"
        assert errors[-1]["elapsed_ms"] >= 0
        await manager.stop()

    asyncio.run(run())


def test_add_command_none_before_launch(tmp_path) -> None:
    assert _add_command(ServerManager(tmp_path)) is None


def test_forward_returns_on_send_error() -> None:
    """WS 发送失败(客户端断开)→ _forward 静默退出,不抛。"""

    class _FakeWS:
        async def send_json(self, _msg):
            raise RuntimeError("client gone")

    async def run() -> None:
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait({"type": "event"})
        await _forward(queue, _FakeWS())

    asyncio.run(run())


def test_restart_failure_records_event(echo_project) -> None:
    """server 起不来时文件变更:重启失败也进时间线(66-67),面板不崩。"""
    import time as _time

    with TestClient(create_app(echo_project)) as client:
        assert client.get("/api/state").json()["running"] is True
        (echo_project / ".mcp.json").unlink()  # 删掉启动配置 → 重启必然失败
        deadline = _time.monotonic() + 10
        while _time.monotonic() < deadline:
            if client.get("/api/state").json()["error"]:
                break
            _time.sleep(0.3)
        with client.websocket_connect("/ws/events") as ws:
            history = ws.receive_json()
            restarts = [e for e in history["events"] if e["kind"] == "restart"]
            assert restarts and "重启失败" in restarts[-1]["message"]


def test_lifespan_tolerates_start_failure(tmp_path) -> None:
    """server 起不来面板照常服务:state 报 running=False + error。"""
    empty = tmp_path / "nothing"
    empty.mkdir()
    with TestClient(create_app(empty)) as client:
        state = client.get("/api/state").json()
        assert state["running"] is False
        assert state["error"]


def test_call_not_running_returns_503(tmp_path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    with TestClient(create_app(empty), raise_server_exceptions=False) as client:
        resp = client.post("/api/call", json={"name": "add", "arguments": {}})
        assert resp.status_code == 503
        assert "detail" in resp.json()


def test_state_and_call_fallbacks(echo_project, monkeypatch) -> None:
    """list_tools 炸 → 工具列表降级空;call_tool 炸 → 500 + 类型化 detail。"""
    monkeypatch.setattr("mcp_sprout.dev.web.ServerManager", _BoomManager)
    with TestClient(create_app(echo_project), raise_server_exceptions=False) as client:
        state = client.get("/api/state").json()
        assert state["running"] is True
        assert state["tools"] == []
        resp = client.post("/api/call", json={"name": "add", "arguments": {"a": 1, "b": 2}})
        assert resp.status_code == 500
        assert "call boom" in resp.json()["detail"]
