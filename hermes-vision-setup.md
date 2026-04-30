---
name: hermes-vision-setup
title: "Hermes Agent Vision 配置技能"
description: "根据用户现有条件（API Key、网络环境、操作系统），自动决策并配置最佳的 Vision 看图方案"
category: "messaging"
---

# Hermes Agent Vision 配置技能

## 使用说明

> 当用户说"我看不到图"、"帮我配一下看图能力"、"vision 怎么配置" 时加载此技能。

### 第一步：采集用户现状（必要信息）

依次（或一次性）了解以下信息。**不要一次性全问**，根据回答自然推进：

1. **操作系统** — Ubuntu / Windows / macOS？
2. **网络环境** — 在国内还是国外？有没有代理？
3. **手头现有的 API Key** — 用户有什么 key？引导用户去拿，不要假设：
   - 阿里百炼（`sk-` 开头，国内直连）
   - OpenRouter（`sk-or-v1-` 开头，海外中转）
   - Google Gemini（免费，国内需代理）
   - 其他（智谱 GLM、百度文心等）

---

### 第二步：决策逻辑

拿到以上信息后，按优先级推荐：

```
有代理 or 国外？
  ├── 有 Gemini key → 用 Gemini（免费额度大）
  ├── 有 OpenRouter key → 用 OpenRouter
  └── 两者都有 → 让用户选

无代理、国内？
  ├── 有阿里百炼 key → 用百炼 qwen-vl-max（国内直连 ✅）
  ├── 有智谱 GLM key → 用 GLM-4V（国内直连 ✅）
  └── 都没有 → 引导用户去阿里百炼注册拿 key（最省事）
```

**如果用户都有，让用户选，不要替他做主。**

---

### 第三步：执行配置

根据决策结果，修改 `~/.hermes/config.yaml` 的 `auxiliary.vision` 段。

各方案的配置模板：

#### 阿里百炼（国内推荐）

```yaml
auxiliary:
  vision:
    provider: openai
    model: qwen-vl-max
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: "sk-用户的key"
    timeout: 120
    download_timeout: 30
```

#### OpenRouter（海外中转）

```yaml
auxiliary:
  vision:
    provider: openrouter
    model: google/gemini-3-flash-preview  # 或其他视觉模型
    base_url: ""
    api_key: "sk-or-v1-用户的key"
    timeout: 120
    download_timeout: 30
```

#### Google Gemini（需代理）

```yaml
auxiliary:
  vision:
    provider: google
    model: gemini-3-flash-preview
    base_url: ""
    api_key: "AIzaSy...用户的key"
    timeout: 120
    download_timeout: 30
```

#### 智谱 GLM（国内直连）

```yaml
auxiliary:
  vision:
    provider: openai
    model: glm-4v-plus
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key: "用户的智谱key"
    timeout: 120
    download_timeout: 30
```

---

### ⚠️ 关键经验：Vision API Key 填在 config.yaml，不是 .env

Vision 的 `api_key` 是填在 `~/.hermes/config.yaml` 的 `auxiliary.vision.api_key` 字段，**不是**在 `.env` 里。

如果 `api_key` 为空或 provider 不匹配，Hermes 会自动 fallback 到主模型（如 DeepSeek），而主模型不一定支持看图。

```yaml
# ✅ 正确
auxiliary:
  vision:
    api_key: "sk-xxxx"

# ❌ 错误：这样 vision 不会读这个变量
# .env 里加 VISION_API_KEY=xxx 不管用
```

---

### 第四步：重启 Gateway

⚠️ **关键安全规则（血泪教训）**：如果用户是通过微信/飞书在跟 AI 对话，AI **绝对不能自己执行** `hermes gateway run --replace` 或 `hermes gateway restart`，因为这会杀掉当前进程 → 微信/飞书断连 → 对话中断。必须让用户在**终端手动操作**。

**之前踩坑**：AI 在对话中执行了 `hermes gateway run --replace`，导致 Gateway 进程被替换，微信连接断开，用户发了一大堆消息都收不到回复。最终用户自己去终端跑 `systemctl --user restart hermes-gateway` 才恢复。

**正确流程**：AI 修改 config.yaml → 告诉用户命令 → 用户在终端手动执行 → 重启后用户发图验证。

#### 根据用户水平选择指引方式

##### 👑 用户会用终端
直接告知命令即可。如果用户记不清、怕打错，可以单独发两行或一行，方便他复制粘贴。

##### 📖 用户会用终端但不熟
准备好**可直接复制粘贴的单条命令**，按系统推荐。让用户复制整行后按回车。

| 系统 | 复制粘贴这一条 |
|------|---------------|
| **Ubuntu**（有 systemd） | `systemctl --user restart hermes-gateway` |
| **macOS**（有 launchd） | `hermes gateway restart` |
| **Windows** | `hermes gateway restart` |
| **Docker** | `docker restart hermes-gateway` |

##### 🆘 用户完全不会用终端

> 如果用户说"我不懂终端"、"不会操作"、"你在云电脑上帮我不行吗"：
>
> 1. 写一份**图文步骤**（点哪儿、输什么、按哪个键），像教小白一样
> 2. 比如 Ubuntu 无影云电脑 → 告诉用户：
>    - "在桌面上找到 **终端**（黑色窗口图标）点开"
>    - "会看到一个闪烁的光标，把下面这行字复制粘贴进去，按回车键："
>      ```
>      systemctl --user restart hermes-gateway
>      ```
>    - "等几秒钟，然后给我发张图试试"

> 如果用户说"我执行了但不行"、"点不开终端"、"没反应"：
> - 一步步排查：什么系统 → 看到什么错误 → 截个图发给我

---

### 第五步：验证

让用户发一张图测试。如果能看到内容 → ✅ 完成。
如果还是看不到 → 检查 `agent.log` 排错。

---

## 排错指南

### 症状：重启后 vision 还是用的主模型（如 DeepSeek）

**原因**：`auxiliary.vision.api_key` 为空或 provider 不对时，会 fallback 到主模型。

**检查**：
```bash
grep -A 6 'vision:' ~/.hermes/config.yaml
# 确认 provider、model、api_key 都填对了
tail -20 ~/.hermes/logs/agent.log
# 看有没有 "Vision auto-detect: using active provider XXX"
# 如果有这句，说明 vision 配置没生效
```

### 症状：Gateway 启动但微信/飞书连不上

**原因**：可能是 Gateway 进程冲突。

**解决**：
```bash
systemctl --user restart hermes-gateway
# 等 10 秒再看
systemctl --user status hermes-gateway
```

### 症状：看图报错 "No authentication provided" 或 401

**原因**：API Key 无效或格式错误。

**检查**：
- key 有没有多余空格？
- 是不是复制漏了字符？
- key 是否在对应平台有 vision 模型的使用权限？

### 症状：阿里百炼 key 能用，但看图很慢

**原因**：qwen-vl-max 首次加载需要几秒预热。后续调用会变快。
如果一直慢，检查 timeout 设置是否够大（建议 120s+）。

### 症状：macOS 上找不到 `systemctl`

**原因**：macOS 用 launchd 不用 systemd。
**解决**：
```bash
# 检查服务状态
launchctl list | grep hermes
# 重启
hermes gateway restart
# 或手动
launchctl kickstart gui/$(id -u)/hermes.gateway
```

### 症状：Windows 上没有 `systemctl`

**原因**：Windows 用服务管理器。
**解决**：
```bash
hermes gateway restart
# 或
net stop hermes-gateway && net start hermes-gateway
```

---

## 验证完成后的收尾

- 询问用户是否需要保存 API Key 到记忆（方便以后重装时自动恢复）
- 告知用户：以后换主模型的 API Key 不影响 vision 能力，两者独立
- 告知用户：发图直接在微信/飞书里发就行，不需要额外操作
