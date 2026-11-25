# deadline-bot — 通知转任务助手

> 一个基于 **nanobot**（HKUDS/nanobot）工作区 skill 机制的二次开发项目。
> 把学校/公司的通知文本变成结构化待办，自动识别截止日期，并在截止前分级提醒。

**在线演示**：<https://deadline-bot-demo.app.workbuddy.host/?sharecode=5G7T6OER6J>（无需安装，打开即用）
也可以直接双击 `docs/index.html` 在浏览器里体验，不需要任何服务。

**仓库**：<https://github.com/lll1123-AKF/deadline-bot>

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen)

## 30 秒看懂这个项目

打开上面的**在线演示**，粘贴一条通知（如「班主任通知：本周五下午5点前交社会实践报告」），
它会立刻解析出任务、截止日和来源，并按内容给出「先做什么」的排序和理由。
你也可以加载 8 条内置示例，切换「执行顺序 / 每日进度 / 截止提醒」三个视图，
随时改优先级、改进度、改截止日——所有前面提到的能力都能在网页里直接点。

> 网页是纯前端交互演示（用 JS 复刻同一套逻辑），真实的 Python 实现、单元测试与设计说明在本仓库。

## 它能做什么

学生和上班族每天都在接收同一种信息：

> 「班主任通知：本周五下午5点前交社会实践报告，请班长统一收齐。」
> 「HR通知：明天下午6点前提交本月工作总结。」

这些信息散落在微信群、邮件、公告里，看一眼觉得记住了，转头就忘。deadline-bot 做的是把它们变成**可追踪、会提醒的任务**：

```
通知文本 → 规则/LLM 解析 → Task（标题/截止日/来源/类别/优先级）→ JSON 记忆 → 分级提醒
```

## 为什么选 nanobot 改造

nanobot 是港大 HKUDS 实验室的开源个人 AI 智能体，扩展点正好是这个项目需要的两样东西：

1. **工作区 Skill**：把 `SKILL.md` 放进 `~/.nanobot/workspace/skills/` 就能让 agent 学会新能力。
2. **Automations**：内置 cron 定时任务和 heartbeat 机制，可以把提醒推到聊天窗口，而不需要自己写调度器。

本项目把「通知解析 + 任务管理 + 提醒生成」做成确定性的 Python 代码（skill 的四肢），nanobot 负责对话、记忆和定时触发（skill 的大脑和神经）。**边界清楚，是这个项目最值得讲的设计点。**

## 快速开始

### 1. 纯本地演示（不需要 nanobot，不需要 API key）

```bash
cd deadline-bot
python demo.py
```

会看到 5 条示例通知被解析成结构化任务，并生成一份分级提醒日报。

### 2. 命令行使用

```bash
# 添加一条通知
python cli.py add "教务处通知：2026年11月30日前提交选课确认表"

# 批量导入（data/sample_notices.txt 有 8 条学生 + 上班族示例）
python cli.py import data/sample_notices.txt

# 查看所有任务 / 只看待办提醒
python cli.py list
python cli.py due

# 按任务内容排执行顺序（含理由）/ 每日进度报告
python cli.py plan
python cli.py plan --top 3
python cli.py daily

# 标记完成 / 删除 / 生成日报
python cli.py done <task_id>
python cli.py remove <task_id>
python cli.py report --title "周三早报"
```

### 2b. 随时改任务

```bash
# 开始做（进度至少 5%），完成后一键 100%
python cli.py start <task_id>
python cli.py finish <task_id>

# 改任意属性：标题、截止日、优先级、状态、进度、类别、来源
python cli.py update <task_id> --priority high --progress 40
python cli.py update <task_id> --due "下周二下午3点"   # 支持自然语言改时间
python cli.py update <task_id> --status pending --title "新的标题"

# 追加备注（带时间戳，保留变更历史）
python cli.py note <task_id> "教务处说可以延后，已确认"
```

改完后 `plan` 和 `daily` 会**立即按新状态重新排序**，不需要手动刷新。

### 3. 装进 nanobot（真正的改造目标）

先按官方文档装好 nanobot（需要 Python 3.11+ 和一个模型 API key）：

```powershell
irm https://raw.githubusercontent.com/HKUDS/nanobot/main/scripts/install.ps1 | iex
```

然后把本目录复制成 nanobot 的工作区 skill：

```bash
# Windows PowerShell
Copy-Item -Recurse . "$HOME\.nanobot\workspace\skills\deadline-bot"
```

把 `SKILL.md` 里的 `{PROJECT_ROOT}` 替换成这个目录的实际绝对路径。

重启 nanobot 后，在对话里直接粘贴通知即可。要开定时提醒，对 nanobot 说：

> 每天早上 8 点运行 deadline-bot 的 due 命令，把即将到期的任务发给我。

## 解析能力

| 表达 | 例子 | 结果 |
|---|---|---|
| 完整日期 | `2026年11月30日前` | 2026-11-30 23:59 |
| 月日 | `12月5日前` | 今年 12-05 23:59 |
| 相对日 | `明天下午6点前` | 次日 18:00 |
| 星期 | `本周五下午5点前` / `下周三前` | 对应日期 17:00 / 18:00 |
| 相对时长 | `3天内报销` | 当前时间 + 3 天 |
| 月底 | `本月底前` | 月末 23:59 |

**LLM 兜底**：遇到规则解析不了的复杂表达，设置任意 OpenAI-compatible 环境变量后加 `--mode llm`：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选
export OPENAI_MODEL=deepseek-chat                     # 可选
python cli.py add "下个月第二个工作周结束前把材料交了" --mode llm
```

规则模式是默认，因为它零成本、可测试、能指出命中的原文片段；LLM 只用来兜长尾。

## 项目结构

```
deadline-bot/
├── SKILL.md                  # nanobot 工作区 skill 定义（改造入口）
├── README.md
├── cli.py                    # 命令行入口
├── demo.py                   # 一键演示
├── deadline_bot/
│   ├── models.py             # Task / Reminder 数据结构与紧急度分级
│   ├── parser.py             # 通知解析：rule + llm 双模式
│   ├── store.py              # JSON 持久化（原子写 + 去重）
│   └── reminder.py           # 分级提醒报告
├── docs/                     # 在线演示页（GitHub Pages 发布源）
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   ├── sample_notices.txt    # 学生 + 上班族示例通知
│   └── tasks.json            # 运行后生成，可删除
└── tests/
    └── test_parser.py        # 22 个回归测试
```

### 内容排序是怎么算的

`plan` 不是简单按截止日排，而是给每件事算一个「该先做分数」：

| 信号 | 权重来源 |
|---|---|
| 优先级 | high=3 / normal=1.5 / low=0 |
| 类别提前量 | 考试 3 天、作业 1.5 天、提交/审批 1 天、会议 0 天 |
| 截止紧迫度 | 连续函数：逾期 > 24h > 3 天 > 7 天，越近分越高 |
| 进行中加权 | +0.5，避免半途而废 |

每条顺序都带「理由」输出，比如「优先级 high、资料提交需提前 1 天、剩余 1.3 天」——**可解释**是 agent 可信度的关键。

跑测试：

```bash
python -m unittest discover -s tests -v
```

## 技术设计（也是面试时怎么讲）

**一句话定位**：这是一个「面向通知场景的 agent harness 扩展」，不是套壳聊天机器人。

可以展开讲四个点：

1. **分层**：`parser → store → reminder` 三层，每层只干一件事。nanobot 的 AgentLoop 负责对话编排，本 skill 只暴露确定性的 CLI 给 agent 调用——这是从 learn-claude-code 里学到的「harness 与智能分离」思想。
2. **解析策略**：规则优先、LLM 兜底。规则模式用 7 类正则覆盖常见中文日期表达，返回命中的原文片段，可解释、可测试；LLM 模式用 OpenAI-compatible 接口处理长尾，输出 JSON 后做结构化校验。
3. **双层排序**：`due` 按剩余时间分 6 档给「什么时候会出事」的提醒；`plan` 综合优先级、类别提前量、紧迫度、进行中状态给「先做哪件」的执行顺序，并输出可解释的理由。前者是时间维度，后者是内容维度，回答的是两个不同问题。
4. **状态可演进**：Task 有 status/progress/notes/updated_at，`update` 支持随时改任意字段（含自然语言改截止日）。改完排序实时重算——真实场景里计划本来就一直在变，agent 必须能跟上。
5. **记忆与可靠性**：JSON 原子写（临时文件 + os.replace）避免崩一半；按「标题 + 截止日」去重；解析不出日期就如实标「无截止日」，不编造——agent 的可信度比覆盖率更重要。

**已知的下一步**（如果被追问「还能怎么改」）：
- 换成 SQLite + 索引，支持按来源/类别查询；
- 接 IM 渠道（飞书/微信）自动抓取通知，而不是手动粘贴；
- 加一个 confirm 环节：解析结果先给用户确认再入库，降低误抽风险；
- 用 nanobot 的 heartbeat 做「只在紧急时提醒」的静默监控。

## 诚实说明

这是**独立编写的教学/演示项目**，借鉴了 nanobot 的 skill 与 automation 机制，并不是 nanobot 官方项目的一部分。简历上建议写「基于 nanobot 二次开发通知管理 skill」，并准备好讲清楚上面几点设计——这样经得起面试官追问。

简历文案、展示脚本和面试追问清单见 **[RESUME_GUIDE.md](RESUME_GUIDE.md)**。
验证方法与可用性边界见 **[VALIDATION.md](VALIDATION.md)**；一键自检运行 `python verify.py`。
