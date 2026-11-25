# DeadlineBot 架构说明：从 nanobot 核心逻辑到独立 Agent Runtime

> 这份文档回答两个问题：**nanobot 到底是怎么跑起来的**，以及**本项目哪些地方参照了它、哪些地方是自己实现的**。
> 面试时如果只能讲一份文档，讲这份。

---

## 0. 先说清楚边界（诚信第一）

| 说法 | 是否成立 |
| --- | --- |
| 本项目是 nanobot 的 fork / 分支 | ❌ 不是。没有 import nanobot，没有复制它的代码 |
| 本项目参照了 nanobot 的分层与运行机制 | ✅ 是。逐个读了它的核心源码后按同样思路重写 |
| 本项目自带完整的对话、记忆、工具、定时能力 | ✅ 是。关掉外部框架也能独立跑 |
| nanobot 是本项目主体 | ❌ 不是。现在它只是 `channels.py` 里一个可选的接入适配器 |
| 本项目实现了 nanobot 的全部能力 | ❌ 没有。多模态、多 provider、飞书/钉钉渠道、子 agent、复杂压缩策略都刻意不做 |

**一句话定位**：参照 nanobot 的 Agent 运行时分层，用 Python 标准库独立实现的一套精简 Agent Runtime，落地在「通知 → 任务 → 排序 → 提醒」这个具体场景上。

---

## 1. nanobot 核心逻辑拆解

我按调用链读了这些源码（下载在 `.research/nanobot/`，仓库不含该目录）：

```
channels/*              InboundMessage / OutboundMessage，把各渠道统一成同一种消息
bus/queue.py             MessageBus：inbound / outbound 双队列 + 事件订阅
bus/events.py            session_key = f"{channel}:{chat_id}"，会话按渠道隔离
agent/context.py         ContextBuilder：identity / bootstrap / memory / skills / history → system prompt
agent/skills.py          SkillsLoader：只注入技能摘要，用到才加载全文
agent/tools/base.py      Tool 契约：name / description / parameters(JSON Schema) / execute
agent/tools/registry.py  get_definitions() 稳定排序缓存、参数校验、错误回喂
agent/runner.py          _run_core()：多轮 tool-calling 主循环
agent/memory.py         长期记忆文件
agent/autocompact.py    会话历史过长时压缩成摘要
agent/tools/cron.py     把「定时」做成工具，触发时注入一个 turn
```

### 1.1 五层骨架

```
┌─ Channels ─────────────────────────────────────────────┐
│  CLI / WebUI / 飞书 / Discord / Email                   │
│  只做两件事：外部输入 → InboundMessage；Outbound → 外部 │
└───────────────────────┬────────────────────────────────┘
                        ▼
┌─ MessageBus ───────────────────────────────────────────┐
│  inbound Queue / outbound Queue / subscribers          │
│  ★ 解耦点：内核完全不知道消息来自哪个渠道               │
└───────────────────────┬────────────────────────────────┘
                        ▼
┌─ ContextBuilder ───────────────────────────────────────┐
│  identity + bootstrap + memory + skills 摘要 + history  │
│  → 组装成一次模型调用的 messages                       │
└───────────────────────┬────────────────────────────────┘
                        ▼
┌─ AgentRunner._run_core ─────────────────────────────────┐
│  for i in range(max_iterations):                       │
│      resp = model.chat(messages, tools)                │
│      if resp.has_tool_calls:                           │
│          execute → 结果 append 回 messages → continue  │
│      return resp.content     # 没有工具调用 = 最终回复   │
└───────────────────────┬────────────────────────────────┘
                        ▼
┌─ 支撑服务 ─────────────────────────────────────────────┐
│  ToolRegistry / SessionMemory / CronService / Skills    │
└────────────────────────────────────────────────────────┘
```

### 1.2 三个最值得学的设计决策

**① 渠道统一成消息信封 + session_key 隔离**
`bus/events.py` 里 `session_key = f"{channel}:{chat_id}"`。同一个内核可以同时服务 CLI 和飞书，两边记忆互不串台，而且加新渠道不用改内核。

**② 工具错误不抛异常，而是回喂给模型**
`tools/registry.py` 把参数错误、执行异常包成一段文本返回。模型读到错误后自己决定重试、换参数还是换工具。这是 agent 能自愈的关键——如果一遇错就抛栈，循环就断了。

**③ 定时触发 = 往总线注入一条 InboundMessage**
`tools/cron.py` 没有另写一套「定时播报」逻辑，而是到点生成一条普通入站消息，让同一个 `AgentLoop` 再跑一轮。**主动性不是新功能，是复用主循环**——这是「助手」和「聊天机器人」的分界线。

另外两个细节：`get_definitions()` 稳定排序并缓存（避免每轮 prompt 抖动导致模型缓存失效）；技能只注入摘要、用到才加载全文（控制上下文长度）。

---

## 2. 改造映射表

| nanobot | 本项目 | 做了什么取舍 |
| --- | --- | --- |
| `bus/queue.py` + `bus/events.py` | `runtime/messages.py` | asyncio.Queue → 同步 `deque`，零依赖、易单测；保留双队列 + 订阅 + `session_key` |
| `channels/*` | `runtime/channels.py` | 3 个适配器：CLI / HTTP / nanobot。nanobot 从「主体」降级为「其中一个渠道」 |
| `agent/context.py` | `runtime/context.py` | 保留分层 system prompt，额外注入「当前任务快照」，减少无意义的 list 调用 |
| `agent/skills.py` | `runtime/skills.py` | 扫描 `SKILL.md` frontmatter，只注入摘要；保留 `load(name)` 全文接口 |
| `agent/tools/base.py` + `registry.py` | `runtime/tools.py` | JSON Schema、稳定排序缓存、参数校验、名称纠错建议、错误回喂，全部保留 |
| `agent/runner.py::_run_core` | `runtime/loop.py` | 同样的多轮循环 + `max_iterations` 护栏；额外把每轮记成 `Trace` |
| `agent/memory.py` + `autocompact.py` | `runtime/memory.py` | `TaskStore`（结构化任务记忆）+ `SessionMemory`（对话记忆、超长合成摘要而非丢弃） |
| `agent/tools/cron.py` | `runtime/scheduler.py` | 触发时 `InboundMessage(channel="cron")` 注入总线，走同一个 loop |
| provider 抽象 | `runtime/llm.py` | 只保留一个 `chat(messages, tools) -> LLMResponse` 契约 + OpenAI-compatible 实现 |
| —（本项目原创） | `runtime/llm.py::RulePlanner` | **零 API key 的确定性「模型替身」**：实现同一契约，照样产出 `tool_calls`，让完整工具循环离线可跑、可测 |
| —（本项目原创） | `runtime/trace.py` | 一次 turn 的 model / tool_call / tool_result / final 链，面试可回放 |
| —（本项目原创） | `runtime/app.py` | `DeadlineAgent` 一行组装全部组件；`build_agent()` 工厂便于测试隔离 |
| —（本项目原创） | `server.py` | 标准库 HTTP 服务，把内核暴露成 `/api/chat`，前端可直接观察工具调用链 |
| core 领域能力 | `deadline_bot/parser.py` 等 | 通知拆分、中文日期解析、内容排序、每日进度、随时修改 |

---

## 3. 本项目一次 turn 的完整时序

以「帮我记一下：1. 课程设计 12月5日前交；2. Java大作业 12月19日前交，排一下先做什么」为例：

```
用户/HTTP/cron
   │  InboundMessage(channel="http", chat_id="web", content=...)
   ▼
MessageBus.publish_inbound → 订阅者收到事件 → consume 认领
   ▼
AgentLoop.handle()
   ├─ ContextBuilder.build(current_input, memory.history("http:web"))
   │     = system(identity + 工具约定 + 任务快照 + 技能摘要) + 历史 + 用户输入
   ├─ 第 1 轮：llm.chat(messages, registry.definitions())
   │     RulePlanner 识别复合意图 → tool_calls = [add_notices, get_plan]
   │     ToolRegistry.execute 逐个执行
   │       add_notices → parser.split_notices → 2 条 Task → TaskStore 原子写
   │       get_plan    → work_score 打分 + 理由
   │     两个 tool result append 回 messages，Trace 各记一条
   ├─ 第 2 轮：llm.chat(...) 收到 role="tool" → 汇总成自然语言
   └─ 发布 OutboundMessage + 写回 SessionMemory（按 session_key）
   ▼
渠道拿到回复（CLI 打印 / HTTP 返回 JSON + trace / nanobot 转发）
```

定时任务走的是**同一张图**：`CronService.trigger()` 造一条 `channel="cron"` 的入站消息，后面的步骤一模一样。

---

## 4. 项目结构

```
deadline-bot/
├── deadline_bot/
│   ├── core（原有领域能力）
│   │   ├── models.py       Task / Reminder、紧急度与 work_score 排序
│   │   ├── parser.py       中文日期解析、多事项拆分、rule / llm 双模式
│   │   ├── store.py        JSON 原子写、去重、动态修改
│   │   └── reminder.py     due / plan / daily 三种报告
│   └── runtime（本次升级的 Agent 内核）
│       ├── messages.py      Inbound / Outbound / MessageBus
│       ├── trace.py        一次 turn 的可回放链路
│       ├── llm.py           LLM 契约 / OpenAI-compatible / RulePlanner
│       ├── memory.py        SessionMemory + 历史压缩
│       ├── skills.py        SkillsLoader（摘要优先）
│       ├── tools.py         ToolSpec / Registry / 7 个默认工具
│       ├── scheduler.py     CronService，触发注入入站消息
│       ├── context.py      ContextBuilder
│       ├── loop.py         AgentLoop 多轮 tool-calling
│       ├── channels.py      CLI / HTTP / nanobot 三种渠道
│       └── app.py          DeadlineAgent 统一装配
├── cli.py                  确定性命令式入口（add / plan / daily / update ...）
├── agent_cli.py            交互式 Agent 入口（走完整 Runtime）
├── server.py               HTTP 服务（静态页 + /api/*）
├── docs/                   在线演示页（可连本地 Runtime，也可纯浏览器降级）
├── tests/
│   ├── test_parser.py      core 层测试
│   └── test_runtime.py      内核层测试
├── verify.py                一键自检
└── ARCHITECTURE.md / README.md / RESUME_GUIDE.md / VALIDATION.md / SKILL.md
```

---

## 5. 关键设计决策与为什么

**为什么写 `RulePlanner` 而不是只接真模型？**
演示和 CI 不能依赖网络和 API key，但「模型决定调哪个工具」这一步又必须真实发生，否则循环、错误回喂、trace 全都测不到。RulePlanner 实现了和真模型一模一样的 `chat()` 契约，把那一步替换成确定性规则，其余组件全部真实执行。有 `OPENAI_API_KEY` 时 `build_llm()` 自动换成 `OpenAICompatLLM`，**主循环一行都不用改**。

**为什么异常要变成文本回喂？**
`ToolRegistry.execute()` 从不向外抛业务异常，参数缺失、工具名拼错、handler 崩溃都返回带 `[请结合用户目标判断是否需要重试…]` 的 `ToolResult`。模型下一轮读到它，可以换参数重试。这比「抛栈 → 整个 turn 失败」健壮得多。

**为什么用 JSON 原子写？**
`TaskStore` / `SessionMemory` / `CronService` 都用 `tempfile.mkstemp` + `os.replace`，避免写一半崩溃留下半个损坏的 JSON。演示阶段 JSON 人能直接读、git 能 diff、零配置；换 SQLite 只需替换 store 层，接口不变。

**为什么规则解析优先于 LLM？**
常见通知表达固定，规则模式零成本、可测试、可解释（能指出命中的原文片段）；LLM 只兜长尾。日期解析错了会直接害人错过 deadline，所以「不确定就标无截止日、绝不编造」是硬约束。

**为什么多事项拆分要 >= 2 个标记才拆？**
宁可少拆也不要把一条普通通知切碎。只有识别到至少两个编号条目（或多行事项）才拆，每条任务单独保留自己的 `raw_notice`，详情页可回溯。

**为什么网页是双模式？**
公网静态托管跑不了 Python。前端探测 `/api/health`：连得上就走真实内核并回显 trace，连不上自动降级为浏览器本地演示。同一份代码，面试官点开链接能看 UI，本地起服务能看完整 Agent 行为。

---

## 6. 能力边界（别吹过头）

- 没有接入真实 IM 渠道（飞书/微信），`NanobotChannel` 只是适配接口，说明「加渠道不用改内核」。
- `RulePlanner` 是关键词规则，不是语言模型；真模型路径支持但在无密钥环境下未做在线联调。
- cron 只支持 `0 8 * * *` / `08:00` / `every:N`，没有完整 crontab 语义。
- 会话压缩是「合成一条 system 摘要」，不是 nanobot 的 Consolidator。
- 单端 JSON 存储，无多用户、无并发锁、无鉴权；`/api/*` 默认只监听 `127.0.0.1`。
- 在线静态页的数据只存在浏览器 localStorage，与本地 Python 的数据不互通（除非启动 `server.py` 并走 `/api/chat`）。

这些限制都在 `VALIDATION.md` 里如实列着，面试主动讲比被问出来好。

---

## 7. 怎么验证这套架构真的在跑

```bash
python -m unittest discover -s tests -v   # core + runtime 全部测试
python verify.py                            # 一键自检（含 Runtime 工具链、定时触发、渠道适配）
python agent_cli.py --demo --prefer-rule      # 多轮演示 + trace + 定时任务 + 会话记忆
python server.py                            # 打开 http://127.0.0.1:8765/ 与内核对话
```

验收点：`AgentLoop` 一轮里出现 `model → tool_call → tool_result → final`；复合意图一轮执行两个工具；`CronService.tick()` 返回的回复同样来自 `AgentLoop.handle()`；`session_key` 不同的渠道记忆互不干扰。
