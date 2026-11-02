# mcp-sprout —— MCP 开发工作台:脚手架为入口,调试面板为核心

> 求职作品集项目 · Python · AI/Agent 生态 · v2.0(重定位版)
> 一句话定位:**从生成到调试,MCP Server 开发的一条龙**。
> 差异点一句话:官方给你协议和零散工具(模板仓库 + Inspector),mcp-sprout 给你一条命令加一块面板——
> 新手手工起一个规范的 MCP Server 要 30 分钟 + 踩三个坑,mcp-sprout 3 分钟生成、调试点一眼看清。

## 1. 目标(分层,可验收)

| 层 | 目标 | 验收方式 |
|---|---|---|
| G1 | 求职作品集:目标岗位 = AI 应用 / Agent 开发 | 简历挂上项目后,能引发面试官 ≥3 个追问 |
| G2 | 被看见:做完 ≠ 作品集 | PyPI 已发布 + ≥3 个真实使用者 + ≥1 篇公开文章 |
| G3 | 学会:Python、MCP 协议、CLI/Web 工程 | 面试能徒手画出 MCP 调用时序图 |
| G4 | 完成:两个月内做完并投递 | 每里程碑有可 demo 产物,烂尾 = 失败 |

## 2. 定位与赢点(竞品对照)

**不是**:MCP SDK/框架(打不过也不打 FastMCP)、Server 托管平台、又一个聊天应用。

| 竞品 | 它做什么 | mcp-sprout 赢在哪 |
|---|---|---|
| 官方 create-*-server 模板 | 静态模板,复制后自己改 | 交互定制 + 生成即规范(日志/报错/CI 全内置) |
| 官方 MCP Inspector | 调试 UI,重连繁琐 | 面板表单按 inputSchema 自动渲染 + JSON-RPC 时间线 + 自动重启 |
| 各类 create-mcp-* 脚手脚 | 只有生成 | 生成之后的部分没人做:调试体验是 mcp-sprout 的核心差异化 |

**一句话赢点(面试版):生态都在卷"生成",没人管"生成之后"——调试是每个 MCP 开发者第一个小时的痛点,mcp-sprout 把这段体验做成产品。**

## 3. 用户与场景

- 主用户:MCP 新手个人开发者;想接 AI 的小团队(人数=1 的"全栈+AI")
- 场景:30 分钟起一个规范 server → 调试 → 交给 Claude Code / 团队使用
- 需求来源:M0 亲手踩坑(用户研究 = 痛点笔记),不是拍脑袋

## 4. 功能阶梯(每档可独立交付、独立发布)

**v0(最小可发布)**:`mcp-sprout new <name> --desc <...>` 参数式生成默认模板(无交互问答);生成项目可被 Claude Code 直接连接
**v1(核心完整)**:交互问答(传输方式/资源模板/依赖工具)+ `mcp-sprout dev` 面板:工具列表、表单自动渲染、JSON-RPC 时间线、文件变更自动重启
**v2(选做,12 月起)**:`mcp-sprout validate`(schema 质量检查)、Streamable HTTP 模板、SDK 2.x 模板变体、FastMCP 风格模板。注:做 Streamable HTTP 模板时,面板要按传输类型分支(stdio_client / streamablehttp_client)——进程管理、自动重启、stderr 管道是 stdio 专属能力,远程服务无"子进程"可杀,语义需重定义

**明确不做**:SDK/框架、托管平台、代码编辑器式功能(守边界,防体量失控)。

## 5. 命令与生成物规范

### `mcp-sprout new <name>`(v0 参数式,v1 交互式)

```
$ mcp-sprout new my-server --desc "公司内部知识库查询"
# v1 交互版追加:
? 传输方式: (● stdio  ○ Streamable HTTP)
? 生成资源(resources)模板: Yes
? 依赖管理: (● uv  ○ pip)
✔ 已生成 my-server/,共 8 个文件
```

生成目录(每项对应一个防坑设计):

```
my-mcp-server/
├── pyproject.toml            # uv;依赖 mcp<2(锁定 1.x,见风险登记)
├── README.md                 # 英文;两行配置接入 Claude Code
├── .mcp.json                 # 开箱即用的宿主配置
├── src/my_mcp_server/
│   ├── server.py             # 入口:日志走 stderr + 统一异常兜底
│   └── tools/example.py      # 示范工具,带 docstring 规范
├── tests/test_tools.py       # 不碰协议,直接测工具函数
└── .github/workflows/ci.yml  # ruff + pytest
```

### `mcp-sprout dev`(v1,核心差异化)

在项目目录下运行,起本地面板:

- 工具列表 + 按 inputSchema 自动渲染参数表单(嵌套对象/枚举/数组)
- 调用后展示完整 JSON-RPC 请求/响应 + 耗时,时间线排布
- 日志实时流(WebSocket 推 stderr)
- 文件变更自动重启 server(watchdog)
- 一键复制宿主配置块

```
[浏览器] --HTTP/WS--> [FastAPI 面板进程] --官方 ClientSession--> [用户 server 进程 stdio 管道]
```

面试概念提炼:这是 **Agent 可观测性** 的最小实现。

## 6. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| CLI | Typer + Rich(交互用 Questionary,v1 才引入) | 类型注解驱动,和 MCP schema 风格同源 |
| 模板 | Jinja2 | 条件/循环生成多文件 |
| MCP SDK | 官方 `mcp` 包,锁定 1.x(`mcp<2`) | **实测**:SDK 2.x 已把 FastMCP 改名 MCPServer,教程未跟上;锁版本 = 工程意识(面试素材) |
| 面板 | FastAPI + uvicorn + WebSocket;前端原生 HTML/JS | 每层讲得清,不引框架 |
| 测试 | pytest + pytest-asyncio | 协议层用 ClientSession 连 echo server 测 |
| Lint | ruff;打包 uv + pyproject,entry point `mcp-sprout`,发 PyPI | 2026 标准姿势 |
| 命名 | **已定 `mcp-sprout`**(2026-11-01 实测:mcpx 与 mcpx-cli 在 PyPI 均被占);预留备选 `mcpforge` | 已解决;文档/命令统一用 mcp-sprout |

模板 `requires-python` 写 `>=3.12`(兼容本机 3.14)。

## 7. 环境现状(2026-10-31 实测)

- 系统 Python 3.14.4(`D:\SOFT\Python`)+ uv 0.12.3,均已具备,零安装
- 实验环境:`lab/.venv`(Python 3.14.5),`mcp[cli]==1.30.0` 已装,`FastMCP` 导入验证通过
- **已实测坑**:最新 `mcp` 2.3.0 删除 `mcp.server.fastmcp`;中文路径在 Windows 终端显示乱码(执行无碍,保险起见连接流程以 /mcp 面板为兜底)

## 8. 里程碑(按真实水平小步走;只依赖课程"时间",不依赖课程"内容")

原则:**每个里程碑有可 demo 产物;先发布,后完善;课程教什么都是课外练习场,教爬虫/数据都兼容。**

| 阶段 | 时间 | 学习前提 | 做什么 | 完成标准 |
|---|---|---|---|---|
| M0 | 10-31 ~ 11-01 | 无 | ✅ 环境已就绪;手写最小 server 接进本地 Claude Code;故意踩 stdout / 异常两个坑 | Claude 成功调用自己的工具;`lab/pitfalls.md` ≥3 条 |
| M1 | 11 月第 1 周 | 函数/字符串/文件读写 | ✅ 11-01 完成:`mcp-sprout new` v0:参数式生成 10 文件模板;验收链 uv sync / pytest / ruff / ClientSession 冒烟全绿 + Claude Code 真机调用通过(1+2=3) | 生成的项目跑通、接 Claude Code 零报错 |
| M2 | 11 月第 2 周 | 字典/列表/循环 | ✅ 11-01 完成:交互问答(Questionary)+ 模板变体 basic/full(错误兜底、资源模板);两个变体验收链双绿 | `new` 能出 2 种模板 |
| M3 | 11 月第 3~4 周 | 函数装饰器/类;课程教 Web 则进度重叠 | ✅ 11-02 完成:面板 v1 全功能(工具列表/表单调用/时间线/日志流/watchdog 自动重启/一键复制接入命令),28 测试全绿,用户浏览器验收通过 | 面板调通自己生成的 server,录屏一段(录屏待用户) |
| M4 | 12 月前半 | pytest/包发布 | ✅ 覆盖率 100%(11-02)+ CI + 发布 PyPI + 文章 1 + 发布贴(见 §9) | **档 A 达成** |
| M5(选) | 12 月起 | — | 档 B 增强:文章 2、2.x 模板、validate | 按求职节奏决定 |

**降级线(防烂尾守则)**:进度崩 → 砍问答保 v0、砍面板保档 A,先投递;原则:**发布过的半成品 > 未发布的完美品**。M3 面板做不动 → 档 A 照常投递,面板写成简历"进行时"。

## 9. 被看见计划(作品集的另一半,G2 专属)

| 节点 | 动作 |
|---|---|
| M4 发布当周 | 文章 1(掘金/CSDN):「MCP 踩坑记:为什么一个 print 就能把协议写坏」——用 pitfalls.md,**只讲坑不推产品**,先攒读者 |
| 发布第 2 周 | 文章 2:「从 Java 转 Python 两个月,我做了个 MCP 脚手架」附 10s GIF,文末 GitHub/PyPI 链接 |
| 发布第 3 周 | 社区贴:Reddit r/mcp + 阮一峰科技爱好者周刊投稿;真实使用者大概率从这里来 |
| 简历 | 项目名 + PyPI/GitHub 链接 + 一句量化:"已发布,mcp 生态脚手架,被 N 个开发者在用" |
| 目标 | 使用者 ≥3 且有真实反馈(数字不重要,反馈才是面试素材) |

## 10. 面试语料

**电梯演讲(60s):**
"每家公司都在接 AI,但起一个规范的 MCP Server 要么手工拷贝样板、要么在官方 Inspector 里反复重连。
我做了 Python CLI 工具 mcp-sprout:交互生成规范项目——日志、错误处理、测试、CI 全配好;加一个内置调试面板,
表单自动渲染、JSON-RPC 时间线一眼看清。项目不大,但覆盖 CLI 设计、进程管理、JSON-RPC、异步、Web 面板,每层我都能展开讲。"

**高频问题:**
- "为什么不做聊天应用?" → 同质化;工具类项目能做完、能讲深、能被真实使用
- "和 FastMCP 什么关系?" → 它是框架,我是脚手架 + 调试器,互补;见 §2 对照表
- "为什么把调试面板当核心?" → 生态都在卷生成,没人管生成之后;调试是新人第一个小时的痛点(我的踩坑笔记就是证据)
- "SDK 1.x 和 2.x 怎么选?" → 2.x 改名 MCPServer 且生态未跟上;锁版本保稳定,2.x 做成模板变体跟进
- "怎么找到用户的?" → 自己先当用户踩坑 → 社区找同类问题的帖子验证 → 写文章引流;展示"发现问题→验证→解决"闭环
- "MCP 三种传输区别?" → stdio(本地子进程)/ Streamable HTTP(现代远程)/ SSE(上代,正被替代);mcp-sprout v1 主打 stdio(生成即用,宿主一个命令直接拉起),Streamable HTTP 模板在 v2 规划里
- "面板里同时有 HTTP/WS 和 stdio,不冲突吗?" → 各司其职:HTTP/WS 是面板自身的网页通信,**不是 MCP 传输**;MCP 协议层全程 stdio(官方 stdio_client 连用户 server 子进程)。分得清 UI 层与协议层,本身就是加分点

## 11. 风险登记

| 风险 | 对策 |
|---|---|
| PyPI 重名 | ~~已应验~~:mcpx 与 mcpx-cli 均被占(2026-11-01 实测)→ 已改定 mcp-sprout,备选 mcpforge |
| Windows 中文路径/编码 | 已实测执行无碍;连接失败时走 /mcp 面板兜底 |
| SDK 2.x 破坏性变更 | 锁 `mcp<2`;2.x 模板的决策点定在 12 月,面试前必须有话术 |
| 课程内容与项目不同步 | 里程碑只按周不按课,任何课型兼容(§8 原则) |
| 工期崩 / 烂尾 | 降级线 + "先发布后完善"守则;每个 M 有可 demo 产物 |
| 双头项目定位涣散 | v2.0 已重定位:脚手架是入口,**调试面板是核心**,一句话说得清 |

## 12. 验收两档

**档 A(投递线)**:`mcp-sprout new` v0/v1 发布 PyPI + README 英文完整 + 10s GIF + 文章 1 + 使用者 ≥3
**档 B(理想线)**:档 A + `mcp-sprout dev` 完整面板 + 测试覆盖 >70% + CI 绿 + 文章 2 + 2.x 模板变体

- [ ] 档 A 全部达成才更新简历
- [ ] 面试前用电梯演讲做 2 次模拟(找朋友或对着 GPT 录屏复盘)