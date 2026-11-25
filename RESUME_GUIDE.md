# 简历与展示指南

这份文档解决三个问题：**这个项目算什么、简历上怎么写、面试时怎么展示**。
原则只有一条：**说真话，但用专业的语言把真话说清楚。**

---

## 一、它到底算什么？

### 准确说法

> 参照 HKUDS/nanobot 的 Agent 运行时分层，用 Python 标准库独立实现的一套精简 Agent Runtime，
> 落地在「通知 → 任务 → 排序 → 提醒」场景。自带消息总线、工具注册表、上下文构建、
> 多轮 tool-calling 循环、会话记忆与定时调度，可独立运行。

它**是**一个能跑起来的 Agent 应用（有模型/规划器决定调什么工具、有工具执行、有循环、有记忆、有主动触发）。
它**不是**一个通用 Agent 框架（没有多模态、多 provider 适配、真实 IM 渠道、子 agent）。

与 nanobot 的关系：**参照设计、重写实现，不是 fork**。`runtime/channels.py::NanobotChannel`
只是演示「新增渠道不必改内核」的一个可选适配器，nanobot 不是项目主体。

### 分层表述（按被追问的深度逐级展开）

| 深度 | 可以怎么说 |
| --- | --- |
| 一句话 | 一个独立实现的通知任务 Agent Runtime |
| 30 秒 | 拆了 nanobot 的核心链路，自己实现了消息总线、工具注册表、多轮工具循环、会话记忆和定时调度 |
| 2 分钟 | 加上：工具错误回喂、上下文分层组装、session_key 隔离、定时触发复用主循环、离线 RulePlanner、Trace 可回放 |
| 被深挖 | 打开 `ARCHITECTURE.md` 逐层讲，并主动说明哪些没做 |

---

## 二、简历怎么写

### 版本 A（稳妥，推荐先背这个）

> **DeadlineBot｜通知任务 Agent Runtime**（个人项目，Python 3.11+ / 零第三方依赖）
> <https://github.com/lll1123-AKF/deadline-bot> · [在线演示](https://lll1123-AKF.github.io/deadline-bot/)
>
> - 参照 nanobot 运行时分层，独立实现消息总线、工具注册表（JSON Schema + 参数校验 + 错误回喂）、上下文构建、多轮 tool-calling 循环、会话记忆压缩与定时调度；内核与渠道解耦，支持 CLI / HTTP / nanobot 三种接入。
> - 中文通知解析采用规则为主、可选 LLM 兜底双通道，覆盖 7 类日期表达与多事项自动拆分，解析不出日期如实标注「无截止日」；模型层默认使用零密钥的确定性规划器 `RulePlanner`（与真模型同 `chat()` 契约），使完整工具循环离线可回归。
> - 设计零 API key 的确定性规划器实现同一模型契约，使完整工具循环离线可运行、可回归；`Trace` 记录每次模型决策与工具结果，便于调试。
> - 73 个单元测试 + 一键自检覆盖语法、CLI、工具链、定时主动触发、渠道适配与前端脚本；JSON 原子写保障持久化可靠性。

### 版本 B（投 Agent / LLM 应用岗，措辞更贴岗位）

> **DeadlineBot｜可观测的 Agent Runtime 与工具编排**
> - 实现 `AgentLoop` 多轮工具调用（model → tool_calls → execute → 结果回填 → final），带迭代上限护栏；工具异常转为可恢复文本回喂模型，支持自愈与重试。
> - `ContextBuilder` 分层组装 identity / 工具约定 / 任务快照 / 技能摘要 / 会话历史；按 `channel:chat_id` 隔离会话，历史超长自动压缩为摘要。
> - 定时任务通过注入 `InboundMessage` 复用同一主循环实现主动提醒；`RulePlanner` 作为可测试的 LLM 替身保证离线演示与 CI。

### 技术关键词（按需挑，别堆）

`Agent Runtime` / `tool calling` / `MessageBus` / `ToolRegistry` / `Context Engineering` /
`session memory` / `cron-triggered turn` / `observability (Trace)` / `JSON Schema` /
`OpenAI-compatible API` / `LLM fallback` / `atomic write` / `unittest`

### 不建议写的话

- ❌「独立开发了完整 AI 智能体框架」——范围过大，一问就露。
- ❌「基于 nanobot 二次开发的 skill」——这是升级前的旧定位，会显得项目只是个小插件。
- ❌「自研大模型 / 自研 Agent 框架」——没有的事。
- ✅ 主动说「参照 nanobot 的设计思想重写，但能力范围刻意收窄」，比被问出来好得多。

---

## 三、链接怎么给

| 用途 | 链接 |
| --- | --- |
| 代码 | <https://github.com/lll1123-AKF/deadline-bot> |
| 在线演示 | <https://lll1123-AKF.github.io/deadline-bot/> |
| 架构说明 | 仓库内 `ARCHITECTURE.md`（建议面试前让面试官直接点这个文件） |

> ✅ 两个链接都在你自己账号 `lll1123-AKF` 下，没有第三方托管域名。
> 面试前确认三件事：① 本地改动已 `git push`（Pages 会自动重建）；
> ② README 顶部描述是「独立 Agent Runtime」；③ CI 徽章为绿色。
> 静态页永远是「浏览器模式」；要现场演示真实内核，双击 `start_server.bat`
> 后访问 `http://127.0.0.1:8765/`。推送步骤见 `PUSH_GUIDE.md`。

---

## 四、5 分钟展示脚本

| 时间 | 做什么 | 讲什么 |
| --- | --- | --- |
| 0:00–0:40 | 打开 GitHub Pages 演示页，粘贴那条 4 事项通知 | 「真实场景里一条通知塞 4 件事，旧版会解析成 1 条。现在自动拆成 4 条，每条独立解析日期，卡片默认只显示名称和时间，详情折叠。」 |
| 0:40–1:20 | 点「详细信息」、切换「执行顺序 / 每日进度 / 截止提醒」 | 「排序不是按截止日，是按内容算可解释分数，每条都给理由；进度和截止是两个不同维度的问题。」 |
| 1:20–2:00 | 打开 `ARCHITECTURE.md` 的五层图 | 「我拆了 nanobot 的核心链路：渠道 → 总线 → 上下文 → 工具循环 → 支撑服务，然后按同样分层自己实现了一遍。」 |
| 2:00–3:20 | 本地 `python server.py`，刷新页面，在「Agent Runtime 对话」输入「记下通知并排一下顺序」，展开 Trace | 「这一栏不是前端复刻，是真实内核。看 Trace：模型选了两个工具、参数是什么、结果回填、第二轮才给最终回复。工具出错会变成文本回喂而不是崩掉。」 |
| 3:20–4:00 | `python agent_cli.py --demo --prefer-rule` | 「定时任务不是另写一套播报，是注入一条 channel=cron 的入站消息，走同一个 Loop；不同渠道按 session_key 隔离记忆。」 |
| 4:00–5:00 | `python verify.py` + `python -m unittest discover -s tests -v` | 「73 个测试 + 一键自检。之前自检抓到过 `--help` 里 `%` 未转义导致崩溃的 bug，这次又抓到单行清单首条被吞的问题，都补了回归测试。」 |

---

## 五、高频追问清单

**Q：这跟调用 LangChain / 直接用 OpenAI function calling 有什么区别？**
A：没有用框架，是想把循环、注册表、上下文、记忆这几层自己写清楚。真模型路径用的是标准 `/chat/completions` + `tools`，协议一致；区别是我把「模型」抽象成一个 `chat(messages, tools)` 契约，所以能塞进 `RulePlanner` 做离线回归，也能换任意兼容服务而不动主循环。

**Q：哪些是你自己写的，哪些是抄 nanobot 的？**
A：设计思想参照 nanobot（双队列 + session_key、工具注册表稳定排序和错误回喂、上下文分层、定时注入 turn），代码是按这个思路用标准库重写的，没有 import 也没有复制。原创部分是 `RulePlanner`、`Trace`、`DeadlineAgent` 装配、HTTP 服务、以及整个通知领域层。

**Q：为什么不用数据库？**
A：演示阶段 JSON 人能直接读、git 能 diff、零配置。三处写都用临时文件 + `os.replace` 原子替换，避免写一半损坏。换 SQLite 只替换 store 层，接口不变。

**Q：规则解析和 LLM 怎么分工？**
A：常见中文日期表达固定，规则零成本、可测试、能指出命中的原文片段；LLM 只兜长尾。日期解析错了会直接害人错过 deadline，所以宁可标「无截止日」也不编造。

**Q：多事项拆分为何要求 >= 2 个标记？**
A：宁可少拆也别把一条普通通知切碎。每条任务保留自己的 `raw_notice`，详情页可回溯。之前线上页被反馈「4 条解析成 1 条」，就是补了这个拆分 + 回归测试。

**Q：`RulePlanner` 算不算「假 AI」？**
A：它是测试替身（test double），不是伪装成模型。作用是把「模型决定调哪个工具」这一步变成确定性输入，让循环、校验、错误回喂、trace、记忆都能在无网络无密钥下被真实执行和验证。有 key 时自动换成真模型，主循环不改。

**Q：定时任务怎么实现的「主动」？**
A：到点生成一条 `InboundMessage(channel="cron")` 投进总线，`AgentLoop.handle()` 照常跑一轮。所以定时提醒和用户提问走的是同一套上下文、同一套工具、同一套记忆，没有第二套逻辑。

**Q：工具执行失败了会怎样？**
A：不抛栈。参数错误、工具名拼错、handler 异常都包成带提示的 `ToolResult` 回填给模型，模型下一轮决定重试、换参数还是换工具。上限 6 轮防死循环。

**Q：怎么保证不同入口的记忆不串？**
A：`session_key = f"{channel}:{chat_id}"`。CLI 和 HTTP 即便 chat_id 相同也互相隔离，测试里清掉一个会话另一个仍在。

**Q：线上网页和 Python 后端是一套代码吗？**
A：不是，这点要如实说。在线静态页跑不了 Python，用 JS 复刻了同一套领域逻辑便于体验；启动 `server.py` 后前端探测到 `/api/health` 会自动改走真实内核并回显 Trace。双模式共用一份前端代码。

**Q：能不能真的投入使用？**
A：作为个人单机工具可以（自己粘贴通知、本地跑）；作为产品不行——无鉴权、无多用户、无并发锁、没有解析结果确认环节、数据单端 JSON。这些限制写在 `VALIDATION.md`，我会主动说明。

**Q：下一步会怎么改？**
A：① 解析结果先给用户确认再入库；② 换 SQLite + 索引；③ 接真实 IM 渠道自动抓通知；④ 把 cron 换成真实后台调度进程；⑤ 接入真模型后补一轮意图识别评测集。

---

## 六、面试时的一个小技巧

被问到「你遇到过什么 bug」时，讲这三个真实的：

1. `argparse` help 文本里写了 `进度 100%`，`%` 被当格式化占位符，`python cli.py --help` 直接崩。→ 转义成 `%%`，并把各子命令 help 加进自检。
2. 一条含 4 个编号事项的通知被解析成 1 条。→ 补 `split_notices()`，Python/JS 两端对齐，7 个回归测试。
3. 单行「帮我记一下：1. …；2. …」首条被引导语吞掉，只拆出 2 条。→ 扩展编号标记前缀并加数字前瞻断言防「12:30」误判，补 2 个回归测试。

每个都能讲「怎么发现的 → 怎么定位 → 怎么防回归」，比背概念有说服力。
