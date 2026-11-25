# GitHub 配置与推送指南（0 基础版）

你目前的状态：

| 项目 | 状态 |
|---|---|
| GitHub 账号 | ✅ 已有：`lll1123-AKF` |
| git 用户名 / 邮箱 | ✅ 已配置 |
| Git Credential Manager | ✅ 已自带（2.9.0），可用浏览器登录 |
| 认证凭据 | ❌ 未配置 ← 只差这一步 |
| 远程仓库 | ❌ 未创建 |

**总共只需在网页上点 3 次 + 运行 1 条命令。**

---

## 第 1 步：在 GitHub 网页创建空仓库

1. 打开 <https://github.com>，登录你的账号 `lll1123-AKF`。
2. 找到**顶部导航栏搜索框右侧的「+」**（旁边带一个小下拉箭头）→ 点开 → 选 **New repository**。
   - 新版 Dashboard 里，**左侧边栏的「+」** 也能进同一个菜单，两个入口完全一样。
   - **最省事的办法**：直接在浏览器地址栏输入 <https://github.com/new> 并回车，一步到位，不用担心界面改版后找不到按钮。
3. 填写：
   - **Repository name**：`deadline-bot`
   - **Description**（可选）：`基于 nanobot 的通知转任务 Agent 技能`
   - 选择 **Public**（公开，面试官才能看到）
   - ⚠️ **不要**勾选 `Add a README file`、`.gitignore`、`Choose a license` —— 本地已经写好了，勾了会导致推送冲突。
4. 点 **Create repository**。
5. 创建成功后页面会显示地址 `https://github.com/lll1123-AKF/deadline-bot.git`。
   **这个地址已经写进推送脚本里了，不用复制**，直接进第 2 步即可。

> 如果仓库名 `deadline-bot` 已被占用，改成 `deadline-bot-agent` 之类，
> 并在运行脚本时把新地址作为参数传进去：`bash push.sh https://github.com/lll1123-AKF/新名字.git`

---

## 第 2 步：运行一键脚本（自动配置认证 + 推送）

在项目目录打开 **Git Bash**（或任何终端），运行：

```bash
bash push.sh
```

脚本会自动做这些事：

1. 配置 `credential.helper=manager`（启用浏览器登录）
2. 初始化本地 git 仓库（如果还没有）
3. 添加所有文件、创建首次提交
4. 设置远程仓库地址（默认 `https://github.com/lll1123-AKF/deadline-bot.git`）
5. 执行推送

**Windows 用户也可以直接双击 `push.bat`。**

### 第一次推送时会发生什么

会弹出一个 GitHub 登录/授权窗口（浏览器或 GCM 窗口）：

1. 选择 **「Sign in with your browser」/ 浏览器登录**
2. 在弹出的网页里登录你的 GitHub 账号
3. 点 **Authorize / 授权**
4. 回到终端，推送自动完成

凭据会被 GCM 安全保存，**以后再也不用手输**。

---

## 第 3 步：确认成功

打开 `https://github.com/lll1123-AKF/deadline-bot`，应该能看到：

- README.md 渲染出来的项目介绍
- `docs/` 目录里的在线演示页面源码
- `RESUME_GUIDE.md`、`VALIDATION.md` 等文档

把这个链接写进简历即可。

---

## 备选方案：浏览器登录不可用怎么办？

如果 GCM 弹窗失败（比如无图形界面），改用 Personal Access Token：

1. GitHub → 右上角头像 → **Settings** → 左侧最底 **Developer settings**
   → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
2. 勾选 `repo` 权限，设置过期时间，生成后**立刻复制**（只显示一次）。
3. 推送时，用户名填 `lll1123-AKF`，密码栏**粘贴这个 token**（不是账号密码）。

也可以手动配置：

```bash
git config --global credential.helper manager
git remote add origin https://github.com/lll1123-AKF/deadline-bot.git
git push -u origin main
```

---

## 可选：把演示页发布成在线链接

GitHub Pages（免费，和仓库绑定）。
⚠️ **从分支部署时，目录下拉只有 `/ (root)` 和 `/docs` 两项，不支持自定义目录名**，
所以本项目的演示网页专门放在 `docs/` 目录下。

1. 仓库页面 → **Settings** → 左侧 **Pages**
2. **Source** 选 `Deploy from a branch`
3. **Branch** 选 `main`，目录选 **`/docs`**，点 **Save**
4. 等 1-2 分钟，访问：
   ```
   https://lll1123-AKF.github.io/deadline-bot/
   ```

这样简历上可以放两个链接：**仓库**（看代码）+ **在线演示**（直接体验）。

---

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 双击 `push.bat` 满屏乱码、一堆「不是内部或外部命令」 | 旧版脚本里写了中文，cmd 默认按 GBK 解读 UTF-8 中文，把命令行也拆坏了。**脚本已重写为纯英文版**，重新双击即可；输出是英文属正常，看到 `SUCCESS` 就是成功 |
| 找不到右上角的「+」 | 新版 Dashboard 改了布局：点左侧边栏的「+」，或直接打开 <https://github.com/new> |
| `Repository not found` | 仓库没建、名字填错，或选了 Private 但没权限；核对 URL |
| `failed to push / rejected` | 创建仓库时勾了 README 导致历史冲突；删掉重建空仓库，或 `git pull --rebase origin main` |
| `Authentication failed` | 密码栏要填 token 不是账号密码；或用 GCM 浏览器登录 |
| 推送后 README 没显示 | 确认文件名是 `README.md`，且已 commit + push |
| 想改仓库描述 | 仓库首页右侧 ⚙️ 旁边可编辑 About |

---

## 安全提醒

- 不要任何形式把 token 发给我、发到聊天里、或写进代码文件。
- 用 GCM 浏览器登录就完全不需要 token，最安全。
- 本项目不含任何密钥；`.gitignore` 已排除本地任务数据。
