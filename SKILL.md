---
name: deadline-bot
description: 通知任务 Agent Runtime 的能力说明书。把学校/公司通知拆成多条结构化待办，识别中文截止日，按内容排可解释的执行顺序，生成每日进度与分级提醒，并支持自然语言改任务与定时主动提醒。当用户粘贴通知、问「有什么要交的」「今天先做什么」「进度怎么样」或要求「每天早上提醒我」时使用。
version: 0.2.0
author: local-extension
allowed-tools: Bash, Read, Write
---

# DeadlineBot 能力说明书

> **定位提醒**：这个文件是 `runtime/skills.py::SkillsLoader` 注入 system prompt 的「说明书」，
> 告诉模型「什么时候该调、按什么流程调」。**工具是函数，技能是说明书**——两者分开才能热插拔。
> 本项目自带完整的 Agent Runtime（见 `ARCHITECTURE.md`），不需要依赖任何外部框架就能独立运行。

---

## 一、内核里有哪些工具

| 工具 | 什么时候用 | 关键参数 |
| --- | --- | --- |
| `add_notices` | 用户粘贴通知（含编号清单 / 多行事项） | `text`：通知原文 |
| `list_tasks` | 修改任务前先拿 id | 无 |
| `update_task` | 改优先级、进度、状态、标题、备注、自然语言改截止日 | `task_id` + 要改的字段 |
| `get_plan` | 「先做什么 / 排个顺序 / 优先级」 | `top` |
| `get_daily` | 「今天进度 / 完成率 / 做得怎么样」 | 无 |
| `get_due` | 「有什么要交的 / 快到期的 / deadline」 | 无 |
| `schedule_reminder` | 「每天早上 8 点提醒我」 | `cron_expr`、`message` |

`ToolRegistry` 会为这些工具生成稳定排序的 JSON Schema，执行前校验参数；
工具名拼错会给近似建议，参数错误或执行异常会变成带提示的文本**回喂给模型**，
由模型决定重试、换参数还是换工具。

---

## 二、标准工作流

1. **粘贴通知** → 调 `add_notices`。一条通知含多个事项时会自动拆成多条，每条保留自己的原文。
2. **问顺序** → 调 `get_plan`，把「理由」一起讲给用户，不要只报任务名。
3. **问进度 / 到期** → 调 `get_daily` / `get_due`。
4. **改任务** → 先 `list_tasks` 拿 id，再 `update_task`；改完说明新状态与排序变化。
5. **设提醒** → 调 `schedule_reminder`。到点时 `CronService` 会注入一条
   `channel="cron"` 的入站消息，走**同一个** AgentLoop，不另写播报逻辑。
6. **复合请求**（如「记下这条通知并告诉我先做什么」）→ 一轮里按顺序调用多个工具，
   工具结果全部回填后再汇总成自然语言回复。

### 对话规则

- 用户粘贴像通知的文本（含「通知」「前提交」「截止」或明确日期），默认解析入库，不用反复确认。
- 回复简短：先结论，再列要点；不要把原始 JSON 丢给用户。
- 日期是推断的（如「3天内」按当前时间推算）要说清推算依据。
- **解析不出日期就如实说「无明确截止日」，绝不编造**——这是可信度底线。
- 一次 turn 有上限（默认 6 轮工具调用），防止模型陷入死循环。

---

## 三、日期与拆分能力边界

规则模式支持：完整年月日、月日、今天/明天/后天、本周X/下周X、`N天内`/`N天后`、月底前。
教学周次（如「14周」）不是日期，会被从标题里清掉；「17周前交」若没给具体月日，标为无截止日。

多事项拆分支持：`1. 2. 3.`、`一、二、`、`(1)`、多行清单、单行分号分隔的清单。
**只有识别到 >= 2 个条目才拆**，避免把一条普通通知切碎。

超出规则范围的长尾表达（「下个月第二个工作周结束前」）：

- 有 `OPENAI_API_KEY` 时用 `python cli.py add "..." --mode llm`；
- 否则如实告诉用户没识别出来，请补充明确日期。

---

## 四、可选：接入外部 Agent 框架

本项目**不依赖** nanobot。但如果想把它挂进外部框架，有三种方式，
都不需要改动内核——这正是 `MessageBus` + `session_key` 解耦的意义：

1. **`NanobotChannel.invoke(agent, command, text)`**：把 `due` / `plan` / `daily` / `add` 等
   命令翻译成一轮普通对话，返回纯文本给外部框架转发。
2. **HTTP**：`python server.py` 后 `POST /api/chat {"text": "...", "chat_id": "..."}`，
   响应含 `reply` 与完整 `trace`。
3. **CLI**：`python cli.py due` / `plan` / `daily` 等确定性命令，供外部 skill 直接调用。

对应到 nanobot 的 scheduled automation：

- 指令：`cd <PROJECT_ROOT> && python cli.py due`
- 频率：`0 8 * * *`（每天 08:00，Asia/Shanghai）
- 交付：回到创建该自动化的会话

> 早期版本把本项目描述成「nanobot 工作区 skill，nanobot 负责大脑和神经」——
> **那是升级前的定位**。现在对话、记忆、工具编排、定时调度都在本项目自己的 Runtime 里，
> 外部框架只是可选渠道。

---

## 五、设计取舍（讲项目时可用）

- **为什么用 JSON 不用数据库**：演示阶段人能直接读、git 能 diff、零配置；换 SQLite 只替换 store 层。三处持久化都用临时文件 + `os.replace` 原子写。
- **为什么规则优先于 LLM**：常见表达固定，规则零成本、可测试、能指出命中的原文片段；LLM 只兜长尾。
- **为什么工具错误不抛异常**：抛栈会直接断掉整个 turn；变成文本回喂，模型才有机会自愈。
- **为什么定时触发要注入入站消息**：复用主循环，主动性不产生第二套逻辑。
- **为什么有 `RulePlanner`**：让完整工具循环在没有密钥、没有网络的环境下也能真实执行和被测试，它不是「假装 AI」，是测试替身。
- **为什么记录 `Trace`**：一次 turn 的 model / tool_call / tool_result / final 都能回放，面试与排障时解释「模型为什么这么选」。

---

## 六、验证

```bash
python -m unittest discover -s tests -v
python verify.py
python agent_cli.py --demo --prefer-rule
```

详见 `VALIDATION.md`；架构与 nanobot 改造映射见 `ARCHITECTURE.md`。
