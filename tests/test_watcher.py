"""watcher 单测:变更过滤(目录事件/.pyc/忽略目录)+ 防抖取消旧任务。"""
import asyncio

from mcp_sprout.dev.watcher import ProjectWatcher, _ChangeHandler


class _Counter:
    def __init__(self) -> None:
        self.value = 0

    def trigger(self) -> None:
        self.value += 1


def _event(src_path: str, is_directory: bool = False):
    return type("FakeEvent", (), {"src_path": src_path, "is_directory": is_directory})()


def test_change_handler_ignores_directory_events() -> None:
    counter = _Counter()
    handler = _ChangeHandler(counter.trigger)
    handler.on_any_event(_event("F:/proj/server.py", is_directory=True))
    assert counter.value == 0


def test_change_handler_ignores_pyc_and_cache_dirs() -> None:
    counter = _Counter()
    handler = _ChangeHandler(counter.trigger)
    handler.on_any_event(_event("F:/proj/__pycache__/server.cpython-314.pyc"))
    handler.on_any_event(_event("F:/proj/.venv/lib/x.py"))
    handler.on_any_event(_event("F:/proj/.git/config"))
    assert counter.value == 0


def test_change_handler_triggers_on_source_change() -> None:
    counter = _Counter()
    handler = _ChangeHandler(counter.trigger)
    handler.on_any_event(_event("F:/proj/server.py"))
    assert counter.value == 1


def test_debounce_cancels_previous_task(tmp_path, monkeypatch) -> None:
    """编辑器保存会连发多个事件:第二次触发取消第一次的防抖任务,
    0.6s(测试里缩短)内只执行一次 on_change。

    注意两次触发之间必须 await 一下:task.cancel() 对"还没被调度
    启动"的任务不会把 CancelledError 投递进协程体——先让任务真正
    进入 sleep,取消才会走到 _debounced 里的 except(CancelledError)。
    """

    async def _fire_twice(watcher: ProjectWatcher) -> None:
        watcher._debounce()
        await asyncio.sleep(0.02)  # 让第一个防抖任务真正跑进 sleep
        watcher._debounce()  # 第二次:取消正在睡的任务(坑10 的 cancel 走自然退出)
        await asyncio.sleep(0.15)
        if watcher._debounce_task is not None:
            watcher._debounce_task.cancel()
            try:
                await watcher._debounce_task
            except asyncio.CancelledError:
                pass

    monkeypatch.setattr("mcp_sprout.dev.watcher.DEBOUNCE_SECONDS", 0.1)
    calls = 0

    async def on_change() -> None:
        nonlocal calls
        calls += 1

    async def run() -> None:
        watcher = ProjectWatcher(tmp_path, on_change)
        await _fire_twice(watcher)

    asyncio.run(run())
    assert calls == 1