---
name: hermes-skills-to-github
title: "Hermes Skills 推送到 GitHub 仓库"
description: "将 Hermes Agent 的技能（skills）推送到 GitHub 仓库，方便保存、分享和跨设备同步。自动判断用户情况并引导操作。"
category: "github"
---

# Hermes Skills 推送到 GitHub 仓库

> 适用场景：用户想把自己 Hermes Agent 的技能（skills）保存到 GitHub，或想分享给其他人。

## 使用说明

当用户说"把我的 skill 放到 GitHub"、"打包发我"、"怎么把我做的东西传出去" 时加载此技能。

### 第一步：采集必要信息（澄清环节）

依次询问用户，不要一次性全抛。根据回答自然推进：

#### 1. GitHub 用户名
> "你的 GitHub 用户名是什么？"
>
> 如果用户不知道，引导去 https://github.com 查看右上角头像旁边的名字。

#### 2. 仓库名
> "仓库想叫什么名字？比如 `hermes-skills` 或者你来定。"

#### 3. 认证方式（二选一）

| 方式 | 说明 | 用户操作 |
|------|------|---------|
| **Personal Access Token (Classic)** | 推荐，最简单 | 去 https://github.com/settings/tokens → Generate new token (classic) → Note 随便填 → Expiration 选 No expiration → 勾上 `repo` → 生成 → 复制 token 给 AI |
| **SSH Key** | 更安全，步骤多 | 用户需要先在本地生成 SSH Key 并添加到 GitHub |

**推荐用 Token 方式**，用户只需要复制粘贴一串字符。

> ⚠️ 安全提示：告诉用户这个 token 有仓库完全控制权限，不要分享给不信任的人。

---

### 第二步：确认信息（让用户验证）

拿到 token 后，让用户看一眼截图确认。用户可能截图 GitHub 页面发过来（AI 看图确认），也可能是直接文字回复。

确认要点：
- Token 勾选了 `repo` 权限
- 用户名拼写正确
- 仓库名没有特殊字符

---

### 第三步：执行操作（AI 在后台完成）

> ⚠️ **注意**：执行过程中，AI 每跑一条敏感命令（如 `curl`、`git push`），系统可能会弹出 **`/approve session`** 的安全确认提示。你看到后只需要回复 **`/approve session`** 批准即可，AI 会继续执行下一步。

AI 依次执行：

```bash
# 1. 创建 GitHub 仓库
curl -s -H "Authorization: token <TOKEN>" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"name":"<REPO_NAME>","description":"Hermes Agent 技能合集","private":false}' \
  https://api.github.com/user/repos

# 2. 创建临时目录，复制 skill 文件
mkdir -p /tmp/<REPO_NAME>
cd /tmp/<REPO_NAME>
git init
git config user.name '<USERNAME>'
git config user.email '<USERNAME>@users.noreply.github.com'

# 3. 复制 skills 到目录
# 遍历 ~/.hermes/skills/ 下的所有 skill
# 保持目录结构

# 4. 创建 README.md
cat > README.md << 'EOF'
# <REPO_NAME>

我的 Hermes Agent 技能合集。
EOF

# 5. 提交并推送
git add -A
git commit -m "初始化：添加 Hermes Agent 技能"
git remote add origin https://<USERNAME>:<TOKEN>@github.com/<USERNAME>/<REPO_NAME>.git
git branch -M main
git push -u origin main
```

---

### 第四步：告知结果

告诉用户仓库地址，例如：
> 已完成！你的技能已推送至：**https://github.com/<USERNAME>/<REPO_NAME>**

---

## 常见问题

### Q: 仓库已存在（409 conflict）
说明同名仓库已经有了。询问用户：
- 是否用另一个名字？
- 是否要 force push 覆盖？

### Q: Token 无效（401）
- token 可能过期了（如果设了有效期）
- 让用户重新生成一个

### Q: 网络超时/无法连接 GitHub
- 检查用户网络环境（是否在国内，是否需要代理）
- 如果 AI 在无影云电脑/国内服务器上，GitHub 访问可能慢，可以耐心多试几次
- 或者让用户自己在本地操作

### Q: 用户说"我不懂 GitHub"
- 先问问用户有没有 GitHub 账号
- 如果没有 → 引导去 github.com 注册（5分钟）
- 注册后继续流程

### Q: 用户想 push 的不仅是 skills，还有别的文件
- 问清楚具体要 push 什么文件/目录
- AI 在复制阶段加入对应文件即可

---

## 安全提醒

- Token 使用完后，AI 不应将 token 存入记忆或 skill 中
- 推送完成后可告知用户删除临时目录：`rm -rf /tmp/<REPO_NAME>`
- 建议用户以后在 GitHub 设置中为 token 设置过期时间（如 30 天/90 天）
