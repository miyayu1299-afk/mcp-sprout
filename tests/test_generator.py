"""generator 单测:名字校验 + 两种模板的生成结果抽查。"""
import pytest

from mcp_sprout.generator import (
    GenerationError,
    ProjectSpec,
    generate_project,
    validate_name,
)


def test_validate_name_ok() -> None:
    validate_name("my-server")  # 合法,不抛异常


@pytest.mark.parametrize(
    "bad",
    ["MyServer", "1server", "-server", "server_", "my.server", "a b", "class"],
)
def test_validate_name_bad(bad: str) -> None:
    with pytest.raises(GenerationError):
        validate_name(bad)


def test_spec_derived_names() -> None:
    spec = ProjectSpec(name="my-server", desc="", template="full")
    assert spec.package == "my_server"
    assert spec.title == "My Server"


def test_generate_project_basic(tmp_path) -> None:
    paths = generate_project(name="demo-server", desc="测试项目", base_dir=tmp_path)
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in paths)
    assert rel == [
        "demo-server/.github/workflows/ci.yml",
        "demo-server/.gitignore",
        "demo-server/.mcp.json",
        "demo-server/README.md",
        "demo-server/pyproject.toml",
        "demo-server/src/demo_server/__init__.py",
        "demo-server/src/demo_server/server.py",
        "demo-server/src/demo_server/tools/__init__.py",
        "demo-server/src/demo_server/tools/example.py",
        "demo-server/tests/test_tools.py",
    ]
    pyproject = (tmp_path / "demo-server" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "demo-server"' in pyproject
    assert "mcp<2" in pyproject  # 锁版防坑设计必须进模板
    server_path = tmp_path / "demo-server" / "src" / "demo_server" / "server.py"
    server = server_path.read_text(encoding="utf-8")
    assert 'FastMCP("Demo Server")' in server
    assert "sys.stderr" in server  # 日志走 stderr
    assert "等待 MCP 客户端连接" in server  # 坑8:启动提示怎么连接
    assert "register_example_resources" not in server  # 基础模板没有资源
    tools_path = tmp_path / "demo-server" / "src" / "demo_server" / "tools" / "example.py"
    tools = tools_path.read_text(encoding="utf-8")
    assert "with_error_logging" in tools  # 错误兜底进基础模板
    assert "def divide" in tools


def test_generate_project_full(tmp_path) -> None:
    paths = generate_project(name="demo-full", desc="", base_dir=tmp_path, template="full")
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in paths)
    assert len(rel) == 13  # 基础 10 个 + 资源 3 个
    assert "demo-full/src/demo_full/resources/__init__.py" in rel
    assert "demo-full/src/demo_full/resources/example.py" in rel
    assert "demo-full/tests/test_resources.py" in rel
    server_path = tmp_path / "demo-full" / "src" / "demo_full" / "server.py"
    server = server_path.read_text(encoding="utf-8")
    assert "register_example_resources" in server


def test_generate_project_bad_template(tmp_path) -> None:
    with pytest.raises(GenerationError):
        generate_project(name="demo-x", desc="", base_dir=tmp_path, template="nope")


def test_generate_project_dir_exists(tmp_path) -> None:
    (tmp_path / "demo-server").mkdir()
    with pytest.raises(GenerationError):
        generate_project(name="demo-server", desc="", base_dir=tmp_path)