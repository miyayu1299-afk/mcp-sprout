"""CLI 冒烟:typer CliRunner 走一遍 new 命令(参数式与交互式)。"""
from typer.testing import CliRunner

from mcp_sprout.cli import app

runner = CliRunner()


def test_new_creates_project(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "demo-server", "--desc", "冒烟测试"])
    assert result.exit_code == 0
    assert "已生成" in result.stdout
    assert (tmp_path / "demo-server" / "pyproject.toml").exists()
    assert (tmp_path / "demo-server" / ".mcp.json").exists()


def test_new_bad_name(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "Bad_Name"])
    assert result.exit_code == 1
    assert "不合法" in result.stdout


def test_new_template_full(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "demo-full", "--desc", "d", "--template", "full"])
    assert result.exit_code == 0
    assert (tmp_path / "demo-full" / "src" / "demo_full" / "resources" / "example.py").exists()


def test_new_bad_template(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "demo-x", "--desc", "d", "--template", "nope"])
    assert result.exit_code == 1
    assert "不存在" in result.stdout


class _FakeStdin:
    def isatty(self) -> bool:
        return True


class _FakeSys:
    """假 sys 模块:带 stdin 和 platform。CliRunner 会替换全局 sys.stdin,
    所以交互测试要把 cli 模块里的 sys 整体换掉,才能让 isatty 生效。"""

    platform = "win32"

    def __init__(self) -> None:
        self.stdin = _FakeStdin()


class _FakePrompt:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    def ask(self) -> str:
        return self._answer


class _FakeQuestionary:
    def __init__(self, desc_answer: str, template_answer: str) -> None:
        self._desc = desc_answer
        self._template = template_answer

    def text(self, *_args, **_kwargs) -> _FakePrompt:
        return _FakePrompt(self._desc)

    def select(self, *_args, **_kwargs) -> _FakePrompt:
        return _FakePrompt(self._template)


class _NoAskQuestionary:
    """如果被调用就失败:断言交互路径被正确跳过。"""

    def text(self, *_args, **_kwargs):
        raise AssertionError("不该发起终端问答")

    def select(self, *_args, **_kwargs):
        raise AssertionError("不该发起终端问答")


class _BoomQuestionary:
    """问答直接抛异常:验证降级兜底(交互炸了不许炸掉生成主流程,坑7 机制)。"""

    def text(self, *_args, **_kwargs):
        raise AssertionError("desc 已传,不该发起描述问答")

    def select(self, *_args, **_kwargs):
        raise RuntimeError("console boom")


def test_new_interactive(monkeypatch, tmp_path) -> None:
    """交互路径:isatty=True 且不是伪终端时,会走 questionary 问答。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mcp_sprout.cli.sys", _FakeSys())
    monkeypatch.delenv("TERM", raising=False)  # 清掉 Git Bash 的 TERM,模拟真 Windows 终端
    monkeypatch.setattr(
        "mcp_sprout.cli.questionary", _FakeQuestionary("交互测试", "full")
    )
    result = runner.invoke(app, ["new", "demo-it"])
    assert result.exit_code == 0
    pyproject = (tmp_path / "demo-it" / "pyproject.toml").read_text(encoding="utf-8")
    assert "交互测试" in pyproject
    assert (tmp_path / "demo-it" / "src" / "demo_it" / "resources" / "example.py").exists()


def test_new_skips_interactive_in_mintty(monkeypatch, tmp_path) -> None:
    """坑7 回归:Git Bash(mintty)下 isatty 为真但 TERM=xterm,
    必须降级参数式,不能把 questionary 拉起来。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mcp_sprout.cli.sys", _FakeSys())
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr("mcp_sprout.cli.questionary", _NoAskQuestionary())
    result = runner.invoke(app, ["new", "demo-mintty"])
    assert result.exit_code == 0
    assert (tmp_path / "demo-mintty" / "pyproject.toml").exists()
    assert not (tmp_path / "demo-mintty" / "src" / "demo_mintty" / "resources").exists()


def test_ask_missing_fallback_when_questionary_crashes(monkeypatch, tmp_path) -> None:
    """问答异常 → 降级默认值 + 警告,生成照常完成(不因终端问题炸掉主流程)。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("mcp_sprout.cli.sys", _FakeSys())
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr("mcp_sprout.cli.questionary", _BoomQuestionary())
    result = runner.invoke(app, ["new", "demo-boom", "--desc", "d"])
    assert result.exit_code == 0
    assert "改用默认值" in result.stdout
    assert (tmp_path / "demo-boom" / "pyproject.toml").exists()
    # 降级到 basic:不生成 full 专属的资源模板
    assert not (tmp_path / "demo-boom" / "src" / "demo_boom" / "resources").exists()


def test_version_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "mcp-sprout" in result.stdout