#!/usr/bin/env bash
# 一键配置 GitHub 认证并推送项目。
# 用法：bash push.sh [仓库URL]
# 不加参数时默认 https://github.com/lll1123-AKF/deadline-bot.git

set -e
cd "$(dirname "$0")"

REPO_URL="${1:-https://github.com/lll1123-AKF/deadline-bot.git}"

echo "======================================================"
echo " DeadlineBot — 配置并推送到 GitHub"
echo "======================================================"
echo ""

echo "[1/5] 启用 Git Credential Manager（浏览器登录）"
git config --global credential.helper manager
echo "      OK"

echo "[2/5] 初始化本地仓库"
if [ ! -d .git ]; then
  git init -q
  git branch -M main
  echo "      已初始化，主分支 main"
else
  echo "      已存在，跳过"
fi

echo "[3/5] 配置提交身份"
if [ -z "$(git config --global user.name)" ]; then
  read -p "      请输入 GitHub 用户名: " name
  git config --global user.name "$name"
fi
if [ -z "$(git config --global user.email)" ]; then
  read -p "      请输入 GitHub 邮箱: " email
  git config --global user.email "$email"
fi
echo "      $(git config --global user.name) <$(git config --global user.email)>"

echo "[4/5] 提交文件"
git add -A
if git diff --cached --quiet; then
  echo "      没有新改动"
else
  git commit -q -m "feat: deadline-bot - notification-to-task agent skill for nanobot"
  echo "      已创建提交"
fi

echo "[5/5] 设置远程仓库并推送"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi
echo "      远程：$REPO_URL"
echo ""
echo "  如果弹出 GitHub 登录窗口，请选择「浏览器登录」并授权。"
echo "  （首次推送才会弹，之后凭据会自动保存）"
echo ""

git push -u origin main

echo ""
echo "======================================================"
echo " 推送成功！"
echo " 仓库地址：${REPO_URL%.git}"
echo "======================================================"
