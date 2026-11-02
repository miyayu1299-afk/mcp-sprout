"""项目文件监听:变更 → 防抖 → 触发 server 重启(PLAN §5 的自动重启)。

并发模型:
- watchdog 的回调在它自己的线程里跑 → 只做 call_soon_threadsafe,
  把所有逻辑调度进事件循环
- 防抖:编辑器保存文件会连发多个事件(modified/closed/...),
  0.6s 内只触发一次重启
"""
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# 这些目录/文件变化不该触发重启:虚拟环境、缓存、git 元数据
IGNORE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".uv"}
IGNORE_SUFFIXES = {".pyc"}

DEBOUNCE_SECONDS = 0.6


class ProjectWatcher:
    """监听项目目录;变更事件防抖后调用 on_change(async 回调,跑在事件循环里)。"""

    def __init__(
        self,
        project_dir: Path,
        on_change: Callable[[], Awaitable[None]],
    ) -> None:
        self._on_change = on_change
        self._loop = asyncio.get_running_loop()
        self._debounce_task: asyncio.Task | None = None
        self._observer = Observer()
        self._observer.schedule(_ChangeHandler(self._trigger), str(project_dir), recursive=True)

    def _trigger(self) -> None:
        """watchdog 线程 → 事件循环:只做线程安全调度,不碰任何任务状态。"""
        self._loop.call_soon_threadsafe(self._debounce)

    def _debounce(self) -> None:
        """事件循环里:取消旧的防抖任务,起新的。"""
        if self._debounce_task is not None:
            self._debounce_task.cancel()
        self._debounce_task = self._loop.create_task(self._debounced())

    async def _debounced(self) -> None:
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
            await self._on_change()
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        """停止监听。observer.stop() 会唤醒监听线程,join 能干净返回(坑10 教训:不靠 cancel)。"""
        if self._debounce_task is not None:
            self._debounce_task.cancel()
        self._observer.stop()
        self._observer.join(timeout=2)


class _ChangeHandler(FileSystemEventHandler):
    """所有事件(创建/修改/删除/移动)都算"变更",但忽略缓存/虚拟环境目录。"""

    def __init__(self, trigger: Callable[[], None]) -> None:
        self._trigger = trigger

    def on_any_event(self, event) -> None:  # noqa: ARG002 事件对象本身用不上
        if event.is_directory:
            return
        parts = Path(event.src_path).parts
        if Path(event.src_path).suffix in IGNORE_SUFFIXES:
            return
        if any(part in IGNORE_DIRS for part in parts):
            return
        self._trigger()
