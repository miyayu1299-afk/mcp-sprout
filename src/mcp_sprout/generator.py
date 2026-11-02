"""模板渲染核心:名字校验 → 变量准备 → 逐个文件渲染。

设计取舍:文件清单显式列在 BASE_FILES / VARIANT_FILES 里,而不是遍历模板目录——
每个生成文件对应 PLAN §5 里的一项"防坑设计",清单即文档;
以后新增模板变体,往 VARIANT_FILES 加一个键 + 一组文件即可。
"""
import keyword
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, PackageLoader


class GenerationError(Exception):
    """生成失败:名字不合法 / 模板类型不存在 / 目标目录已存在。"""


# PyPI 风格项目名:小写字母开头,字母/数字,分隔用连字符
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# 模板变体:basic(工具 + 错误兜底)/ full(再加资源示例)
TEMPLATES = ("basic", "full")

# 所有变体共享的文件:(模板文件名, 目标路径模板)。{package} 会被替换成下划线包名。
BASE_FILES: list[tuple[str, str]] = [
    ("pyproject.toml.j2", "pyproject.toml"),
    ("README.md.j2", "README.md"),
    (".mcp.json.j2", ".mcp.json"),
    (".gitignore.j2", ".gitignore"),
    ("ci.yml.j2", ".github/workflows/ci.yml"),
    ("server.py.j2", "src/{package}/server.py"),
    ("__init__.py.j2", "src/{package}/__init__.py"),
    ("tools_init.py.j2", "src/{package}/tools/__init__.py"),
    ("example.py.j2", "src/{package}/tools/example.py"),
    ("test_tools.py.j2", "tests/test_tools.py"),
]

# 各变体追加的文件(字典:变体名 → 文件清单)
VARIANT_FILES: dict[str, list[tuple[str, str]]] = {
    "basic": [],
    "full": [
        ("resources_init.py.j2", "src/{package}/resources/__init__.py"),
        ("example_resource.py.j2", "src/{package}/resources/example.py"),
        ("test_resources.py.j2", "tests/test_resources.py"),
    ],
}


def default_description(name: str) -> str:
    """--desc 缺省时的默认描述。"""
    return f"{name}:一个由 mcp-sprout 生成的 MCP Server"


@dataclass(frozen=True)
class ProjectSpec:
    """一次生成的全部变量:项目名 → 包名/显示名都是它的派生。"""

    name: str  # 项目名:my-server
    desc: str  # 一句话描述
    template: str = "basic"  # 模板变体

    @property
    def package(self) -> str:
        """Python 包名(连字符转下划线):my-server → my_server。"""
        return self.name.replace("-", "_")

    @property
    def title(self) -> str:
        """给 FastMCP 的显示名:my-server → My Server。"""
        return self.name.replace("-", " ").title()


def validate_name(name: str) -> None:
    """项目名要同时满足 PyPI 规范与 Python 标识符规则。"""
    if not _NAME_RE.match(name):
        raise GenerationError(
            f"项目名 {name!r} 不合法:只允许小写字母/数字/连字符,且不能以数字或连字符开头"
        )
    if keyword.iskeyword(name.replace("-", "_")):
        raise GenerationError(f"项目名 {name!r} 转成包名后是 Python 关键字,不能用")


def generate_project(
    name: str, desc: str, base_dir: Path, template: str = "basic"
) -> list[Path]:
    """在 base_dir 下生成 <name>/ 项目,返回生成的文件列表。"""
    validate_name(name)
    if template not in TEMPLATES:
        raise GenerationError(f"模板类型 {template!r} 不存在,可选:{'/'.join(TEMPLATES)}")
    spec = ProjectSpec(name=name, desc=desc or default_description(name), template=template)
    dest_root = base_dir / name
    if dest_root.exists():
        raise GenerationError(f"目标目录已存在:{dest_root}(换一个名字,或先删除旧目录)")

    env = Environment(
        loader=PackageLoader("mcp_sprout", "templates/default"),
        autoescape=False,  # 生成的是代码/配置文件,不需要 HTML 转义
        keep_trailing_newline=True,
    )
    created: list[Path] = []
    for tpl_name, dest_tpl in BASE_FILES + VARIANT_FILES[spec.template]:
        rel = dest_tpl.format(package=spec.package)
        content = env.get_template(tpl_name).render(
            name=spec.name,
            package=spec.package,
            title=spec.title,
            desc=spec.desc,
            template=spec.template,
        )
        path = dest_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")  # 强制 LF,CI/Linux 友好
        created.append(path)
    return created
