# mcp-sprout · 进度存档(每次收工更新,下次从"下一步"继续)

## 2026-11-02(白天档 → **M4 第 1 步完成 ✅:覆盖率 86% → 100%**)

### 已完成 ✅
1. **覆盖率基建**:pytest-cov 入 dev 组;pyproject 加 `--cov=mcp_sprout --cov-report=term-missing --cov-fail-under=80`(档 B 标准 >70%,门槛定 80 留缓冲);入口守卫标 `pragma: no cover`
2. **86% → 100%**(503 语句):28 → **49 单测全绿**,新增 21 个,全部"钉行为不钉数字":
   - CLI 层:version 命令、交互问答异常降级(坑7 机制)、dev 成功路径(假 uvicorn 拦截 assert 参数 + 假 webbrowser 验证"打不开浏览器不炸面板")
   - 错误路径:start 失败(时间线 error 事件 + owner 不炸、可重复失败)、call_tool 传输错误(时间线记工具名/耗时)、**重启失败进时间线**、lifespan 容忍启动失败、/api/state list_tools 兜底、/api/call 503/500、WS 发送失败静默退出
   - 防御分支:LogSink 写读闭环、双 close 幂等、读端关闭 OSError 退出、**EventBus.stop 3s 超时兜底 —— 实测 Windows 下关读端能唤醒阻塞的 os.read(坑10 设计被验证)**
   - watcher:目录事件/.pyc/忽略目录三个过滤 + 防抖取消(坑14)
3. **PLAN 面试语料补充**(用户提议):§10 新增「三种传输区别」(Streamable HTTP 以 v2 规划口径出现)与「面板双传输不冲突」两条问答;§4 v2 行补面板按传输类型分支的边界设计

### 认知存档
- 坑14:task.cancel() 对未启动任务不投递 CancelledError(进 pitfalls)
- 覆盖率正确用法:每行 missing 都有说法——错误路径补测试、测不动的标 pragma、死代码删掉;单跑一个测试文件时会因门槛失败,调试用 `--no-cov`
- 小尾巴:`fastapi.testclient` 有 StarletteDeprecationWarning(官方建议 httpx2),无碍,CI 时再处理

### 待用户实测
自己跑:`.venv\Scripts\python.exe -m pytest`(末行会打印 100.00% 与门槛行)。可故意改错一个断言,看 `--cov-fail-under=80` 门禁怎么拦(红-绿体验)。

### 下一步(M4 第 2 步)
**GitHub CI**:项目还没 git init + 推到 GitHub(需要你的 GitHub 账号)。CI 跑 ruff + pytest(覆盖率门槛随行)→ 之后 PyPI 发布。

## 2026-11-01(晚间档 → **M3 开工,第 1 步完成 ✅**)

### 已完成 ✅
1. **`mcp-sprout dev` 面板 v0(最小可 demo)**:
   - `dev` 命令:自动发现启动配置(`.mcp.json` → `pyproject [project.scripts]` 兜底),起 FastAPI(默认端口 8668),默认自动开浏览器
   - 核心链路:面板进程 --官方 ClientSession--> 用户 server stdio 管道;进程管理交给 stdio_client(Windows Job Objects,面板退出不留孤儿进程)
   - 前端:工具列表 + **inputSchema 自动渲染表单**(递归:string/integer/number/boolean/enum/嵌套 object/数组)+ 结果区(isError 徽标 / 耗时 / 文本 / 图片 / structuredContent / 完整 JSON)
   - 错误透明:server 端 isError、参数校验错误原样展示(坑4 机制复用,面板不写错误分类)
2. 依赖:主依赖加 `mcp<2`(面板本身就是一个 MCP 客户端)+ fastapi + uvicorn;pywin32 由 mcp 的 win32 marker 自动带上(Job Objects 需要)
3. 质量:24 单测全绿(dev 新增 5:启动发现 3 + 生命周期 1 + API 全链路 1)+ ruff 干净
4. 真机验收:面板连 demo-full → 3 工具列出 → add 1+2=3(4.5ms)→ divide 1/0 isError 清晰

### 认知存档
- `stdio_client(errlog=)` 是日志流的正规接线口:subprocess 对 errlog 只认 `fileno()`(坑11)——正确做法是传一个持有 `os.pipe()` 写端 fd 的对象,子进程 stderr 直入管道,事件循环线程读读端
- mcp 1.30.0 调未注册工具**不是协议错误**:server 返回 isError 响应("Unknown tool: x"),面板 200 + 红色徽标即可
- FastAPI lifespan 里 start 失败不崩面板:状态经 /api/state 报给前端
- 测试策略:测试 server 是写入 tmp 的极小 FastMCP 脚本,由 manager 用 `sys.executable` 拉起——零外部依赖,不走 lab 路径

### 待用户实测 → ✅ 已通过(2026-11-01)
用户在浏览器里验收了面板:工具列表 → 表单填参 → 调用 → 结果/错误展示全流程通过。
自己跑:`F:\MCP项目\mcp-sprout\.venv\Scripts\mcp-sprout.exe dev`(会自动开浏览器)。

## 2026-11-01(夜档 → **M3 第 2 步完成 ✅**)

### 已完成 ✅
1. **JSON-RPC 时间线**(`/ws/events`):EventBus 记录「连接 / 调用请求 → / 调用响应 / 错误」,前端先收历史再实时追加;请求显示参数、响应显示耗时与 isError 状态
2. **stderr 日志流**(`/ws/logs`):LogSink 持 OS 管道写端 fd 传给 `stdio_client(errlog=)` → 子进程 stderr 直入管道 → 事件循环线程读读端、行分割发布(坑10/坑11 的教训都进了设计)
3. 前端底部面板:时间线/日志双 tab;WS 断线 2s 自动重连 + 25s keepalive(后端靠 receive_text 检测断开,为第 3 步自动重启铺路)
4. 质量:26 单测全绿(新增总线埋点 1 + WS 双流 1)+ ruff 干净;真机验证:面板连 demo-full 启动 + add 7+8=15 正常
5. 新坑入档:坑10(to_thread 取消不唤醒线程 → pytest 挂死)、坑11(subprocess 只认 fileno),共 11 条

### 认知存档
- `asyncio.to_thread` 里阻塞的系统调用,任务 cancel 不会唤醒线程;停止路径必须设计自然退出(关 fd 触发 EOF/OSError),否则线程池 atexit join 挂死进程
- `subprocess.Popen` 的 stdin/stdout/stderr 文件对象参数只调用 `fileno()`,从不调用 `write()`——纯 Python TextIO 过不去
- EventBus 按消息类型分订阅通道(events/logs),不然两类 WS 互相收到对方的消息
- `os.pipe()` 的 fd 非继承,Popen 自己 dup 成继承句柄——不用手动处理继承性

### 待用户实测
浏览器打开 http://127.0.0.1:8668(或自己跑 `mcp-sprout dev`):底部「时间线」看 add/divide 调用的 →/← 与耗时,「日志」tab 看 server 的 stderr(uv 启动行 + FastMCP 日志)。

### 下一步(M3 第 3 步)
文件变更自动重启(watchdog)+ 一键复制宿主配置块。重启 = manager.stop → 重新 start,时间线发 info 事件;前端 WS 断线重连已就绪,重启后状态自动恢复。

## 2026-11-02(凌晨档 → **M3 第 3 步完成 ✅,M3 全功能就绪**)

### 已完成 ✅
1. **文件变更自动重启**:watchdog 递归监听项目目录,0.6s 防抖;变更 → manager.restart() → generation 递增 → 时间线发「文件变更 → server 已重启(N 个工具)」;忽略 .venv/.git/__pycache__ 等目录与 .pyc 后缀
2. **一键复制宿主配置块**:`/api/state.add_command` 构造 `claude mcp add <name> --scope user -- <command> <args>`(.mcp.json 里的相对路径替换成绝对路径,任意目录粘贴可用);前端复制按钮 + toast
3. **坑12 修复(owner 任务模式)**:anyio cancel scope 绑定任务身份,跨任务 stop 直接 RuntimeError(重启失败 + 事件循环收尾挂死)→ ServerManager 加专属 owner 任务,所有操作(start/stop/restart/call)经操作队列串行执行 —— 顺带消灭"防抖重启 vs lifespan 关停"的并发竞争
4. 质量:28 单测全绿(新增:跨任务 restart 1 + watcher 自动重启 1 + add_command 断言)+ ruff 干净
5. 真机验证:面板连 demo-ask → 改 server.py → gen 2→3 自动重启 → add(10,20)=30 正常;停面板后零孤儿进程(Job Objects 生效);复制命令格式正确

### 认知存档
- anyio 的 CancelScope 记录**进入时的任务**,必须在同一任务里退出 —— 跨任务 start/stop 生命周期要用 owner 任务串行化(坑12);owner 模式 = 操作队列 + future 回传
- 启动时 uv 写 uv.lock 会触发一次"多余"的自愈重启(gen 变 2)——无害;防"无关文件触发"的三层过滤:忽略目录 + 后缀 + 防抖
- 挂死排查顺序:先 faulthandler 拿全线程栈,再看事件循环异常处理器输出 —— 被吞的任务异常才是真凶

### 待用户实测 → ✅ 已通过(2026-11-02)
用户浏览器实测两项全过:(1) 改 server.py 两次(加/删注释)→ 时间线各出现一条「文件变更 → server 已重启(3 个工具)」;(2) 复制接入命令 → `claude mcp list` 显示 `demo-ask: uv run ... - √ Connected`。
**M3 全部完成 ✅**

### 验收中暴露的坑(坑13)
浏览器时间线空白 → 面板日志 `No supported WebSocket library detected`:纯 uvicorn 不带 WS 支持,补依赖 `websockets>=12` 解决。TestClient 直连 ASGI 应用、不走真实 uvicorn,单测绿 ≠ 服务器层能跑 —— 已补真 WS 客户端冒烟验证(时间线历史 + 日志流均通)。

### 下一步
M3 收尾(用户录屏)→ M4 启动:测试覆盖率报告、GitHub CI、PyPI 发布、求职文章。

## 2026-11-01(傍晚档 → **M2 完成 ✅,下一步 M3**)

### 已完成 ✅
1. **模板变体 basic / full**:
   - basic(10 文件):工具示例 + **错误兜底**(`with_error_logging` 装饰器 + `divide` 错误示范工具,坑4 对策进模板)
   - full(13 文件):basic + **资源示例**(`notes://{key}` URI 模板资源 + 纯函数单测)
2. **交互问答(Questionary)**:缺 `--desc`/`--template` 时交互询问;`--template` 支持参数式非交互;管道/CI/mintty 环境自动降级默认值
3. **坑7 修复**:终端能力预检(`isatty` + win32/TERM 判 mintty)+ 问答块 try/except 兜底;新增 mintty 降级回归测试
4. mcp-sprout 自身质量:19 个单测全绿 + ruff 干净
5. **M2 验收链双绿**(`lab/demo-basic` + `lab/demo-full`):生成 → uv sync → pytest(4/6 通过)→ ruff → ClientSession 冒烟:
   - 两变体共通:3 工具全通;`divide 1/0` → 客户端 isError:true **且服务端堆栈落日志**(错误兜底端到端验证)
   - full 专属:`resource_templates=[notes://{key}]` + `read_resource("notes://welcome")` 成功
6. 生成物支持 Jinja 条件块(server.py 按变体条件注册资源、README 条件段落)

### 认知存档
- Jinja 条件块行内写法:`{% if x %}body{% endif %}` 标签与内容同行,false 不留空行;缩进写在 body 里
- questionary 强依赖真实 Windows console;`win32 + TERM=xterm` 即判定 mintty 伪终端
- 交互测试:CliRunner 会替换全局 sys.stdin → 要 monkeypatch 模块级 `mcp_sprout.cli.sys`
- 资源 URI 模板出现在 `list_resource_templates`(不在 `list_resources`),`read_resource` 用具体化后的 URI
- `isatty()` 只能测"是不是终端",测不出"是什么终端"(坑7)
- **范围裁剪**:传输方式(Streamable HTTP)与依赖管理(pip)问答按 PLAN §4 归 v2,不进 M2

7. **坑8(用户实测反馈)**:新用户在终端裸跑 stdio server、敲回车触发 Invalid JSON → 模板 server.py.j2 增加"如何连接"启动提示(stderr),测试加回归断言
8. **坑9(第二次踩中)**:用户注册 `claude mcp add demo-ask` 后 /mcp 只有 weather —— 默认 local scope 写进当前目录 `.mcp.json`,会话 /mcp 读 user 级配置(M0 上午档同一坑)。修复:改 `--scope user` 注册 + `claude mcp list` 验证

### 待用户实测 → 交互问答 ✅ 已通过(2026-11-01)
用户在真实 PowerShell 跑 `new demo-ask`,交互问答(描述 + 模板)正常,项目生成于 `C:\Users\yu\demo-ask`(home 目录)。坑8 也在同一轮实测踩中并已修复(启动提示进模板)。

⚠️ 剩余收尾 → ✅ 已解决(2026-11-01):demo-ask 之前被注册成"项目级且挂在 `C:/Users/yu/demo-ask` 下"(在该目录跑的 `claude mcp add`),所以 /mcp 永远看不到。已改 user 级注册并验证:`claude mcp list` → demo-ask ✔ Connected。用户已在 /mcp 连接;demo-ask 是 **full 模板**,协议冒烟全绿(`SMOKE-OK(full)`:hello/add/divide/错误兜底/资源读写)。✅ 重启会话后真机提问"帮我算一下 1 加 2"→ demo-ask 的 add 工具被真实调用,回答 1+2=3。**M2 完整闭环:交互生成的项目接 Claude Code 零报错。**
```
claude mcp list   # 已确认:weather ✔ + demo-ask ✔ Connected
```
可选:注册 demo-full 让 AI 读 `notes://welcome` 资源(**同样要 --scope user**):
```
claude mcp add --scope user demo-full -- uv run --directory "F:/MCP项目/mcp-sprout/lab/demo-full" demo-full
```

### 下一步(M3,11 月第 3~4 周)
`mcp-sprout dev` 面板 v1:工具列表 + inputSchema 表单自动渲染 + JSON-RPC 时间线 + 文件变更自动重启。按 PLAN §5 架构(FastAPI + WebSocket 推 stderr,官方 ClientSession 连用户 server stdio)。

## 2026-11-01(下午档 → M1 完成 ✅,下一步 M2)

### 已完成 ✅
1. **mcp-sprout 包骨架**:pyproject(hatchling + src layout,deps Typer/Rich/Jinja2,entry point `mcp-sprout`)+ 独立 `.venv`(CPython 3.14.5)+ editable 安装
2. **10 个模板文件**(`src/mcp_sprout/templates/default/`),每个对应一项防坑设计:
   - `pyproject.toml`:锁 `mcp<2` + uv 依赖组(dev:pytest/ruff)
   - `server.py`:日志强制 stderr + `main()` 异常兜底 + 坑2/坑3/坑4 注释
   - `.mcp.json`:`uv run --directory .` 相对路径(防坑1 的绝对路径问题)
   - `tools/example.py`:纯函数 + `register()` 分离,docstring 规范
   - `README.md`:英文,两行接入 Claude Code + "为什么锁 mcp<2"
   - `ci.yml`:setup-uv + ruff + pytest
3. **`new` 命令**:名字校验(PyPI 正则 + Python 关键字防撞)+ Jinja2 渲染 + Rich 目录树输出;另加 `version` 命令
4. **mcp-sprout 自身质量**:13 个单测全绿,ruff 干净
5. **M1 验收链全绿**(`lab/demo-server`):生成 10 文件 → `uv sync`(mcp 1.30.0,锁版生效)→ `uv run pytest` 2 通过 → `uv run ruff check` 干净 → **官方 ClientSession 冒烟**(tools/list = [add, hello] + 两次 call 零报错,见 `lab/smoke_demo.py`)
6. 新坑入档:`lab/pitfalls.md` 坑5(Typer 单命令扁平化)、坑6(GBK 控制台 UnicodeEncodeError),共 6 条

### 认知存档
- Typer 0.27.3:单命令 app 会把唯一命令扁平化到 app 层(`new xxx` 变 unexpected extra argument)→ `version` 命令让 app 恢复子命令结构
- 中文 Windows 控制台 GBK:CLI 输出只用 ASCII 标记([OK]/[FAIL]);CliRunner 测不出真实控制台编码问题
- 生成物验收套路:`生成 → uv sync → pytest → ruff → ClientSession 冒烟`,四关全过才算"跑通"

### 待用户实测 → ✅ 已通过(2026-11-01)
用户已在 /mcp 把 demo-server 接进 Claude Code,提问后 `add` 工具被真实调用,回答 1 + 2 = 3。**M1 验收闭环:生成的项目接 Claude Code 零报错。**

### 下一步(M2,11 月第 2 周)
交互问答(Questionary)+ 模板变体(资源模板、错误兜底)。`new` 能出 2 种模板。按 PLAN §5/§8 执行。

## 2026-11-01(上午档)

### 已完成 ✅
1. **包名改定:`mcp-sprout`**(用户拍板)。PyPI 实测:`mcpx` 0.1.1 已被占、`mcpx-cli` 0.1.1 也被占;`mcpforge` 留作备选
2. 目录改名 `mcpx` → `mcp-sprout`;PLAN.md 全部引用同步替换(§6 命名行改为"已定"、§11 风险行改为"已应验",旧名只保留在被占/改名的语境里)
3. **修掉真坑①**:`.mcp.json` 与兜底命令的路径 `F:/项目/mcpx` 不存在(真实是 `F:\MCP项目`)→ 已修正,并且 `claude mcp add weather` 注册成功。项目级(local scope)注册在会话里 /mcp 看不到 → 改 **user 级全局注册**,`claude mcp list` 健康检查 ✔ Connected
4. **修掉真坑②**:`FastMCP("Weather", version=...)` 在 mcp 1.30.0 直接 TypeError(`version` 是 2.x API)→ 已删;并做了协议级冒烟测试:手写 initialize + tools/list JSON-RPC 打进 stdio,`get_weather` 返回正常 ✅
5. `lab/pitfalls.md` 已开张,先记上述两坑(踩坑日志 = 文章/README 素材)

### 收尾(中午档)
- M0 收官三步完成:真机调用 weather 成功;坑3(print 小吞大污,非确定性污染)、坑4(raise → isError 响应,堆栈被吞)实测入档;`weather_server.py` 回滚干净版并验证
- 实验临时文件已删除

## 2026-10-31(历史存档)

### 已完成 ✅
1. 环境检测:**Python 3.14.4 + uv 0.12.3 均已装**,零安装;`lab/.venv` 就绪,`mcp[cli]==1.30.0` 验证通过
2. **踩到真实坑**:最新 mcp 2.x 删除 FastMCP(改名 MCPServer)→ 决策锁定 `mcp<2`(面试素材)
3. PLAN.md 重写为 **v2.0**:脚手架入口 + 调试面板核心、小步里程碑 M0~M5、被看见计划、双档验收、降级线
4. 写好 `lab/weather_server.py`(最小 server,含注释)+ `.mcp.json`(项目级 weather 配置)

> ⚠️ 当天兜底命令与 `.mcp.json` 的路径 `F:/项目/mcpx` 实为坏路径(不存在),2026-11-01 已修正,勿再使用

### 文件地图
| 文件 | 用途 |
|---|---|
| `PLAN.md` | 项目总规划 v2.0(定位/里程碑/风险/面试语料) |
| `PROGRESS.md` | 本文件,进度存档 |
| `src/mcp_sprout/cli.py` | Typer 入口:new / version |
| `src/mcp_sprout/generator.py` | 名字校验 + Jinja2 渲染,FILES 清单即防坑设计文档 |
| `src/mcp_sprout/templates/default/` | 10 个模板文件 |
| `tests/` | mcp-sprout 自身单测(13 个) |
| `lab/demo-server/` | M1 验收产物(生成物 demo,已跑通验收链) |
| `lab/smoke_demo.py` | 生成物协议冒烟脚本(M2 回归可复用) |
| `lab/weather_server.py` | M0 实验 server(干净版) |
| `lab/pitfalls.md` | 痛点笔记(9 条真实坑) |
| `.mcp.json` | Claude Code 项目级 MCP 配置(weather;user 级注册在 ~/.claude.json) |
