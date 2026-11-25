# DeadlineBot — 通知任务 Agent Runtime

> 把学校 / 公司通知变成可追踪、会排序、会主动提醒的任务。
> **不是 nanobot 的分支或一个小 skill**：项目自带消息总线、工具注册表、上下文构建、多轮 tool-calling 循环、会话记忆与定时调度，可独立运行；nanobot 只是可选接入渠道之一。

**在线演示**：<https://deadline-bot-demo.app.workbuddy.host/?sharecode=5G7T6OER6J>（打开即用，无需安装）
**仓库**：<https://github.com/lll1123-AKF/deadline-bot>

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-67%20passed-brightgreen)
![Deps](https://img.shields.io/badge/dependencies-0%20(stdlib%20only)-orange)

---

## 30 秒体验

```bash
python verify.py                          # 一键自检：单测 / 工具循环 / 定时触发 / 渠道适配
python agent_cli.py --demo --prefer-rule   # 多轮 Agent 演示 + 工具调用链 + 定时任务
python server.py                          # 打开 http://127.0.0.1:8765/ 和内核对话
```

不需要 API key、不需要装任何第三方包。`RulePlanner` 是零密钥的确定性「模型替身」，
它和真模型实现同一个 `chat()` 契约，所以**完整的工具调用循环离线照跑**。
设置 `OPENAI_API_KEY` 后会自动切换到 OpenAI-compatible 模型，主循环一行都不用改。

**Windows 上最省事**：在项目根目录双击 `start_server.bat`，脚本自动检测 Python、启动内核并打开浏览器。
⚠️ 必须访问 `http://127.0.0.1:8765/` 才会连上 Python 内核；公网静态页（GitHub Pages / 在线演示链接）
永远是纯浏览器模式，不会连到你本机的服务——这是预期行为，不是故障。

也可以直接双击 `docs/index.html`，或打开上面的在线演示链接——
没有后端时前端自动降级为浏览器本地演示，功能照样可用。

---

## 这个项目解决什么

学生和上班族每天都在接收同一种信息：

> 「班主任通知：本周五下午5点前交社会实践报告，请班长统一收齐。」
> 「注意：1.《GIS》课程设计 12月5日前交；2. 实验报告 12月13日前交；3. Java 大作业 12月19日前交；4. 课程论文 17周前交。」

看一眼觉得记住了，转头就忘，而且一条通知里往往塞了好几件事。DeadlineBot 做的是：

```
一条通知 → 多事项拆分 → 中文日期解析 → Task（标题/截止日/来源/类别/优先级）
        → JSON 原子写入 → 按内容排执行顺序（带理由）→ 每日进度 + 到点主动提醒
```

任务卡片默认只显示**名称 + 时间**，其余信息收进「详细信息」折叠区，
里面保留每条任务自己的通知原文，方便回溯核对。

---

## 架构一览

```
Channels (CLI / HTTP / nanobot 适配器)
        ↓  InboundMessage(channel, chat_id, content)
MessageBus  ·  session_key = channel:chat_id（会话隔离、渠道解耦）
        ↓
ContextBuilder（identity + 工具约定 + 任务快照 + 技能摘要 + 历史）
        ↓
AgentLoop 多轮 tool-calling
   model → tool_calls → ToolRegistry.execute → 结果回填 → 再问模型 → final
        ↓
OutboundMessage + SessionMemory（超长自动压成摘要）+ Trace（可回放）
        ↑
CronService.tick() 到点注入一条 channel="cron" 的入站消息 → 走同一条链路
```

逐层对照 nanobot 源码的拆解、改造映射表和设计取舍，见 **[ARCHITECTURE.md](ARCHITECTURE.md)**。
这是本项目最值得讲的一份文档。

**分层目录**：

```
deadline_bot/
├── models.py / parser.py / store.py / reminder.py   # core：确定性领域能力
└── runtime/                                        # runtime：Agent 内核
    ├── messages.py   trace.py    llm.py    memory.py
    ├── skills.py     tools.py    scheduler.py
    ├── context.py    loop.py     channels.py   app.py
cli.py            # 命令式入口：add / list / plan / daily / update / ...
agent_cli.py      # 交互式 Agent 入口（走完整 Runtime）
server.py        # 标准库 HTTP 服务：静态页 + /api/chat 等端点
docs/            # 在线演示页（双模式：连内核 / 纯浏览器）
tests/           # test_parser.py（core）+ test_runtime.py（内核）
verify.py        # 一键自检
```

---

## 两种入口，一套内核

### 命令式（cli.py）

```bash
python cli.py add "教务处通知：2026年11月30日前提交选课确认表"
python cli.py import data/sample_notices.txt       # 8 条学生 + 上班族示例
python cli.py list
python cli.py due                                  # 按剩余时间分级提醒
python cli.py plan --top 3                         # 按内容排执行顺序（含理由）
python cli.py daily                                # 完成率 / 进度条 / 今日聚焦
python cli.py update <id> --priority high --progress 40
python cli.py update <id> --due "下周二下午3点"     # 自然语言改期
python cli.py start <id>  /  finish <id>  /  note <id> "老师说可以延后"
```

一条通知含多个事项时 `add` 会自动拆成多条，改完任意字段后 `plan` / `daily` 立即重算。

### Agent 式（agent_cli.py / server.py）

```bash
python agent_cli.py --trace          # 每轮显示 model → tool_call → tool_result → final
python agent_cli.py --once "今天先做什么？"
```

或者启动 HTTP 服务，在网页的「Agent Runtime 对话」里输入：

| 输入 | 内核行为 |
| --- | --- |
| `帮我记一下：1.课程设计 12月5日前交；2.Java大作业 12月19日前交` | `add_notices` 拆成 2 条入库 |
| `今天先做什么？` | `get_plan`，按内容打分并输出理由 |
| `进度怎么样？` | `get_daily`，完成率与状态分布 |
| `t_xxxxxxxx 做完了` | `update_task`，状态与进度一致性约束 |
| `每天早上 8 点提醒我生成今日任务进度` | `schedule_reminder`，创建定时任务 |
| `记下通知并排一下顺序` | 一轮内依次执行 `add_notices` + `get_plan` |

每次回复都能展开 **Trace**，看到模型选了哪个工具、传了什么参数、工具返回了什么。
定时任务不是另写一套播报逻辑，而是注入一条入站消息走同一个 `AgentLoop`。

---

## 解析能力

| 表达 | 例子 | 结果 |
|---|---|---|
| 完整日期 | `2026年11月30日前` | 2026-11-30 23:59 |
| 月日 | `12月5日前` | 今年 12-05 23:59 |
| 相对日 | `明天下午6点前` | 次日 18:00 |
| 星期 | `本周五下午5点前` / `下周三前` | 对应日期 17:00 / 18:00 |
| 相对时长 | `3天内报销` | 当前时间 + 3 天 |
| 月底 | `本月底前` | 月末 23:59 |

**多事项拆分**：编号清单（`1. 2. 3.`、`一、二、`、`(1)`）、多行清单、以及单行分号分隔的
「帮我记一下：1. …；2. …」都会拆开；每条单独解析日期、单独保留原文。
只有识别到 **>= 2 个条目**才拆，宁可少拆也不把一条普通通知切碎。

**LLM 兜底**：规则解析不了的长尾表达，设置环境变量后加 `--mode llm`：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选
export OPENAI_MODEL=deepseek-chat                     # 可选
python cli.py add "下个月第二个工作周结束前把材料交了" --mode llm
```

规则优先，是因为零成本、可测试、能指出命中的原文片段；日期解析错了会直接让人错过 deadline，
所以**解析不出就如实标「无截止日」，绝不编造**。

---

## 内容排序怎么算

`plan` 不是简单按截止日排，而是给每件事算「该先做分数」：

| 信号 | 权重来源 |
|---|---|
| 优先级 | high=3 / normal=1.5 / low=0 |
| 类别提前量 | 考试 3 天、作业 1.5 天、提交/审批 1 天、会议 0 天 |
| 截止紧迫度 | 连续函数：逾期 > 24h > 3 天 > 7 天，越近分越高 |
| 进行中加权 | +0.5，避免半途而废 |

每条都带理由，例如「优先级 high、资料提交需提前 1 天、剩余 1.3 天」——**可解释**是可信度的关键。
`due` 回答「什么时候会出事」（时间维度），`plan` 回答「先做哪件」（内容维度），两者互补。

---

## 验证

```bash
python -m unittest discover -s tests -v   # 67 个测试，core + runtime
python verify.py                           # 一键自检
node --check docs/app.js                    # 前端脚本语法（装了 node 时）
```

自检覆盖：语法编译、全部单测、CLI 各子命令 help、解析入库、去重、自然语言改期、
动态修改、排序理由、完成状态一致性、Runtime 组装、多事项入库、工具调用链可回放、
内容排序工具、定时主动触发、HTTP 渠道适配、会话历史压缩、两个新入口、前端语法、文档齐备。

可用性评估与如实列出的能力边界见 **[VALIDATION.md](VALIDATION.md)**。

---

## 诚实说明

- 这是**独立编写的教学 / 演示项目**，参照 HKUDS/nanobot 的运行时分层与运行机制重写，不是 nanobot 官方项目，也没有复制它的代码。
- 本项目自带 Agent 内核，不依赖 nanobot 即可运行；`runtime/channels.py::NanobotChannel` 只是演示「加一个渠道不用改内核」的可选适配器。
- `RulePlanner` 是关键词规则，不是语言模型；真模型路径已实现但在无密钥环境下未做在线联调。
- 单端 JSON 存储、无鉴权、无多用户；`/api/*` 默认只监听 `127.0.0.1`。在线静态页数据只存在浏览器，与本地 Python 数据不互通（除非启动 `server.py`）。

简历文案、5 分钟展示脚本和高频追问清单见 **[RESUME_GUIDE.md](RESUME_GUIDE.md)**。
架构拆解与改造映射见 **[ARCHITECTURE.md](ARCHITECTURE.md)**。
