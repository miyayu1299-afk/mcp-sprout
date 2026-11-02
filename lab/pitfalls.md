# pitfalls.md —— 痛点笔记(README "Why" 与文章素材)

> 每条:一句话现象 → 根因 → 教训 → 面试话术钩子
> M0 目标:≥3 条 ✅(已 4 条,全部实测)

## 坑1:宿主配置里写了不存在的路径

- **现象**:`.mcp.json` 和兜底命令里写 `F:/项目/mcpx/...`,实际目录是 `F:\MCP项目`——配置路径不存在,/mcp 面板看不到 server、连接报"找不到 python.exe"
- **根因**(2026-11-01 发现):配置先于验证写死;目录改名/搬位置后没有全量检查旧绝对路径
- **教训**:1) 写配置前先验证路径真实存在;2) 任何改名/搬迁,`grep -r` 旧路径挨个更新
- **话术钩子**:Windows 中文路径 + 绝对路径配置是新手的隐形第一堵墙;官方模板没有路径检查,mcp-sprout 生成 `.mcp.json` 时要防的设计点

## 坑2:教程 API 混版本:`FastMCP(version=...)` 在 1.30.0 直接 TypeError

- **现象**:`FastMCP("Weather", version="0.1.0")` → 启动即崩:`__init__() got an unexpected keyword argument 'version'`
- **根因**:`version` 是 mcp 2.x 的构造参数;项目锁了 `<2`,代码却照 2.x 教程抄
- **教训**:**锁版本 = 连文档一起锁**;`import` 通过 ≠ 能实例化,冒烟测试要实跑到 `tools/list`
- **话术钩子**:正面验证"SDK 1.x/2.x 怎么选"面试题的答案——生态分裂期,把版本锁进模板就是脚手架的价值

## 坑3(实测):工具函数里 print() —— 小 print 凭空消失,大 print 污染协议,且污染是非确定性的

- **现象**(2026-11-01 三组对照实验,stdio + mcp 1.30.0):
  - 小 print(`print("调试:进来了")`,17 字节):进程干净退出(码 0),stdout/stderr 里**完全找不到**,调试信息凭空消失;Claude Code 真机调用结果正常
  - 大 print(20KB):**运行中途**直接冲进 stdout 管道,JSON-RPC 通道被搅乱——客户端逐行解析必然失败
  - 即:协议会不会坏,取决于 print 累计量(8KB 缓冲),污染时机不可预测
- **根因**:读 SDK 源码 `mcp/server/stdio.py`——stdio 模式标准输出就是协议通道;1.30.0 的 `stdio_server` 自己包了一个 UTF-8 TextIOWrapper **直接写 `sys.stdout.buffer`**,而 `print()` 走原始 gbk `sys.stdout`,两者共用同一底层缓冲。小 print 落在 8KB 用户态缓冲里,进程 teardown 时底层 buffer 被关,未 flush 数据静默丢弃;超过 8KB 自动 flush → 即时污染
- **教训**:stdio 模式下 **print 是绝对的雷**:量小你看不到(以为代码没执行),量大协议崩(且崩得莫名其妙)。日志只能走 stderr
- **话术钩子**:mcp-sprout 模板把"日志走 stderr + logging 配置"写进生成物,防的就是这个坑;非确定性 bug(取决于数据量)是最难排查的一类,这是面试能展开讲的故事

## 坑4(实测):工具函数 raise 异常 —— 进程不崩,但堆栈被吞

- **现象**(2026-11-01 实测):`raise ValueError("数据库挂了")` → 进程不崩(退出码 0),SDK 把它包装成**正常 JSON-RPC 响应**返回:`"isError": true`,text = `Error executing tool get_weather: 数据库挂了`;`structuredContent` 整个缺失;stderr 只有一行 INFO 日志,**堆栈不落任何日志**
- **根因**:mcp 1.x 在 tool 调用层 catch 异常转 `ToolError`,只把异常消息放进返回内容
- **教训**:异常 ≠ 崩溃——客户端友好(拿到明确错误文本),但服务端排查困难(堆栈被吞)。模板应内置 `logging.exception`,错误要"客户端友好 + 服务端可查"两条腿
- **话术钩子**:Agent 可观测性的最小设计点——错误既要在响应里讲清,也要在日志里留痕,mcp-sprout 生成物把这一点做进默认配置

## 坑5(实测):Typer 单命令扁平化 —— `app new xxx` 报 unexpected extra argument

- **现象**(2026-11-01 实测,typer 0.27.3):app 只注册一个 `@app.command()` 时,`mcp-sprout new demo-server` 报 `Got unexpected extra argument(s) (demo-server)`;`--help` 显示 `Usage: ... [OPTIONS] {name}` —— 命令没了,参数全被提升到 app 层
- **根因**:Typer 对**只有一个命令**的 app 做扁平化(把唯一命令当成主入口);两个命令时一切正常
- **教训**:定位过程 = 最小复现逐项排除(先怀疑参数名 `name` 有魔法,再怀疑函数名,最后定位到命令数);解法不写 hack——加一个真实有用的 `version` 命令即可,同时保留标准 `cmd 子命令` 形式
- **话术钩子**:框架"特性"与直觉不符时,靠最小复现定位而不是翻文档;写 CLI 时"命令数变化会改变解析行为"是值得警惕的边界

## 坑6(实测):中文 Windows 控制台 GBK —— 输出 ✔/✗ 直接 UnicodeEncodeError

- **现象**(2026-11-01 实测):rich 打印 `✔ 已生成 ...` 时崩溃:`UnicodeEncodeError: 'gbk' codec can't encode character '✔'`。更阴的是:文件已全部生成,**崩溃发生在生成之后的输出环节**——功能完成但 CLI 报错 exit 1
- **根因**:中文 Windows 默认控制台代码页 GBK;✔(U+2714)/✗(U+2717)不在 GBK 字符集内,写出时编码失败
- **教训**:1) CLI 面向中文 Windows 用户,标记用 ASCII(`[OK]`/`[FAIL]`),中文文本本身 GBK 可编没问题;2) 单测用 CliRunner 捕获输出,**测不出真实控制台编码问题**,必须真实终端跑一遍才闭环
- **话术钩子**:跨平台 CLI 的编码设计;测试金字塔之上还要一层"真实环境冒烟"

## 坑7(实测):`isatty()` 不足以判断"能不能交互问答" —— Git Bash(mintty)里 questionary 直接崩

- **现象**(2026-11-01 实测):Git Bash(mintty)下跑交互式 `new`:`sys.stdin.isatty()` 返回 True → questionary 被拉起 → prompt_toolkit 报 `NoConsoleScreenBufferError: Found xterm-256color, while expecting a Windows console`
- **根因**:win32 平台上 prompt_toolkit 要拿**真实 Windows console handle**;mintty 是 POSIX 风格伪终端(TERM=xterm),isatty 为真但 handle 拿不到
- **教训**:1) `isatty()` 只能测"是不是终端",测不出"是什么终端";2) 交互前加终端能力预检(win32 + `TERM=xterm` → 判定伪终端,降级);3) 问答块再套 try/except 兜底——**交互是锦上添花,生成是底线**,终端问题永远不能炸掉主流程
- **话术钩子**:CLI 降级设计:同一命令在 cmd/PowerShell/Windows Terminal 里交互、在管道/CI/Git Bash 里参数式,两条路都通

## 坑8(实测):新用户在终端裸跑 stdio server,敲回车报 Invalid JSON

- **现象**(2026-11-01 用户实测):`uv run demo-ask` 后终端没有任何提示,用户按回车 → `Received exception from stream: ... Invalid JSON: EOF while parsing a value at line 2 column 0 [input_value='\n']`,并冒出一条 `notifications/message` 错误
- **根因**:stdio server 把 stdin 当协议通道,**任何一行非 JSON(包括空行)都会被校验拒绝**;server 没崩,只是"抱怨"后继续等。新用户第一直觉是"直接运行",而 stdio server 是给客户端连的,不是给人用的
- **教训**:1) 模板应在启动时用 stderr 打一条"怎么连接"的提示(已加进 server.py.j2);2) 官方模板只说 "run it",不说"然后呢"——这正好是 mcp-sprout dev 面板要解决的第一小时痛点
- **话术钩子**:启动日志即文档——把"怎么用"写进程序输出,mcp-sprout 的模板让用户第一次运行就知道下一步

## 坑9(两次踩中):`claude mcp add` 默认 local scope,/mcp 面板看不到

- **现象**(2026-10-31 与 11-01 各踩一次):`claude mcp add xxx ...` 执行成功,但 /mcp 面板只有旧 server,新 server 不出现
- **根因**:`claude mcp add` 默认注册到**项目级(local scope)**,写进当前目录的 `.mcp.json`;而 Claude Code 会话的 /mcp 面板读的是 **user 级**全局配置——两个配置层,教程几乎不讲
- **教训**:1) 注册用 `--scope user`;2) 注册后立刻 `claude mcp list` 验证;3) 还看不到就重启 Claude Code(MCP server 在会话启动时加载)
- **话术钩子**:宿主工具的配置分层(local/user/project)是隐形概念;mcp-sprout 生成的 `.mcp.json` 恰好是 local 层——跟"claude mcp add 默认行为"的错位就是新手看不到 server 的真相

## 坑10(实测):取消 asyncio.to_thread 里阻塞的任务,线程不会醒 —— pytest 挂死

- **现象**(2026-11-01 实测):dev 面板日志流第一版:EventBus 用 `asyncio.to_thread(queue.get)` 阻塞等日志行,stop 时 `task.cancel()`。单测跑到最后**永不退出**(pytest 整体挂死,不是失败)
- **根因**:`cancel()` 只取消协程侧的 await,`to_thread` 背后的线程仍阻塞在 `queue.get()` 上;线程池(ThreadPoolExecutor)线程是非 daemon 的,解释器退出时 atexit join 等它结束 → 永远等
- **教训**:1) 阻塞系统调用永远不能靠 cancel 退出——要设计**自然退出路径**(哨兵值、关 fd 触发 EOF/OSError);2) 异步任务卡死和线程卡死是两层问题,排查顺序:先看有没有线程阻塞
- **话术钩子**:异步编程的"取消语义"是面试高分区;mcp-sprout 面板日志流 = 跨线程管道桥接的真实案例

## 坑11(实测):subprocess 的文件对象参数只认 fileno() —— 自定义 TextIO 直接 AttributeError

- **现象**(2026-11-01 实测):日志流第二版:想给 `stdio_client(errlog=自定义TextIO)` 一个带 write() 的纯 Python 对象 → `AttributeError: 'LogSink' object has no attribute 'fileno'`(subprocess.py:1421)
- **根因**:`subprocess.Popen` 对 stdin/stdout/stderr 的文件对象只做一件事——`fileno()` 拿句柄 dup 给子进程,**从不调用 write()**。没有真实 fd 的对象在进程创建层就过不去
- **教训**:正确设计 = `os.pipe()` 持有写端 fd 的对象(fileno() 返回它)+ 事件循环线程读读端;停止时关写端让 reader 读到 EOF 自然退出(与坑10 的"自然退出"原则呼应)
- **话术钩子**:stdio 管道 + 事件循环的桥接设计;为什么日志流不是"写个类传进去"就完事——进程模型决定接口形态


## 坑12(实测):anyio cancel scope 绑定任务身份 —— 换任务退出直接 RuntimeError

- **现象**(2026-11-02 实测):watcher 防抖任务里调用 manager.restart() 后,测试在 TestClient 退出处挂死(faulthandler 显示事件循环空转);重启从未发生,真错误埋在事件循环日志里:`RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`
- **根因**:anyio 的 CancelScope(task group 底层)记录**进入时的任务**,要求在同一任务里退出。stdio_client 内部用 `anyio.create_task_group()` 管 stdin/stdout 泵:server 在 lifespan 启动任务里拉起,却从 watcher 防抖任务里 stop → RuntimeError → MCP 关停序列被腰斩 → 子进程/管道状态不一致 → 事件循环收尾挂死
- **教训**:1) 跨任务的 start/stop 生命周期要归拢到一个**专属 owner 任务**串行执行(操作队列 + future 回传),进入/退出永远同任务;2) 挂死排查顺序:先 faulthandler 拿线程栈,再看事件循环的异常处理器输出 —— 任务异常会被吞掉,测试却照样挂
- **面试话术钩子**:为什么面板不用"谁调谁停"?scope task affinity 是 anyio/trio 结构化并发的核心约束,owner 任务就是把这个约束显式化;顺带把"防抖重启 vs lifespan 关停"的并发竞争也消灭了


## 坑13(实测):uvicorn 不带 WebSocket 库 —— 前端时间线/日志全空白

- **现象**(2026-11-02 用户实测):浏览器里时间线空无一物,面板日志刷 `WARNING: No supported WebSocket library detected`,浏览器 WS 升级请求被拒(WinError 10054)
- **根因**:时间线/日志走 WebSocket,但依赖只装了纯 `uvicorn` —— 它的 WS 支持需要 `websockets`/`wsproto` 单独装(`uvicorn[standard]` 才自带)。FastAPI 的 TestClient 直连 ASGI 应用、不走真实 uvicorn,所以 28 个单测全绿也没抓住这个洞;我之前真机验收也只 curl 了 HTTP 接口
- **教训**:1) 凡是依赖"真实服务器进程"才能验证的能力(WS 握手、静态资源、uvicorn 插件),单测绿 ≠ 能跑,必须用真客户端(websockets 库/浏览器)冒烟一次;2) 依赖加 `websockets>=12` 解决
- **面试话术钩子**:TestClient 是 ASGI 层测试,不是服务器层测试 —— 两层都测才算闭环,这正是"单测 + 冒烟"的分工

## 坑14(实测):task.cancel() 对"没被调度过"的任务不投递 CancelledError —— 单测盲区

- **现象**(2026-11-02 覆盖率补漏时):watcher 防抖测试里连续两次 `_debounce()` 之间没有 await,第一个任务"还没启动"就被 cancel → `_debounced` 里的 `except CancelledError` 两行始终没被覆盖,coverage 99.6% 卡这
- **根因**:asyncio 的 Task.cancel() 对尚未开始执行的任务只做**标记**,协程体一行都不跑,CancelledError 在"await 这个任务"处直接抛出,而不是在协程内部的挂起点抛出——取消路径根本没进协程体
- **教训**:1) 测取消逻辑,要先 await 让任务真正进挂起点再 cancel;2) 覆盖率报告不只是数字:**盖不住的行往往暴露测试没真跑到那段逻辑**(或那段是死代码)
- **话术钩子**:"用覆盖率反推测试质量问题"——100% 之前每一步都是考据:缺的行该补测试、测不动的标 `# pragma: no cover`、测出来是死代码就删
