---
name: hermes-wechat-feishu-setup
title: "Hermes IM 平台连接配置"
description: "在 Hermes Gateway 中配置任意 IM 平台的连接，全程在聊天对话中完成，无需用户操作终端。支持微信、飞书、Telegram、Discord、Slack、钉钉等 20+ 平台。"
category: "messaging"
---

# Hermes IM 平台连接配置

> 适用场景：用户通过已连接的 IM（如微信）跟你聊天，想连上另一个平台（如飞书、Telegram 等）。
>
> **核心原则：全程对话完成，不让用户碰终端。**

AI也能在终端环境下直接完成配置，此时不需要交互式引导，直接操作即可。

---

## 第一步：确认用户想连哪个平台

列出所有支持的平台让用户选。

**Hermes 目前支持的 20 个平台：**

| # | 平台 | 配置方式 | 所需凭据 |
|---|------|---------|---------|
| 1 | Telegram | Bot Token | 用户去 @BotFather 创建 bot，拿到 token |
| 2 | Discord | Bot Token | 去 Discord Developer Portal 创建应用 |
| 3 | Slack | Bot Token + App Token | 去 Slack API 创建应用 |
| 4 | WhatsApp | 扫码配对 | 手机 WhatsApp 扫码 |
| 5 | Signal | 手机号 | 注册 Signal 账号 |
| 6 | Email | 邮箱地址+密码/授权码 | 用户自己的邮箱 |
| 7 | SMS (Twilio) | Account SID + Auth Token | Twilio 控制台 |
| 8 | Home Assistant | Long-Lived Token | Home Assistant 用户资料页 |
| 9 | Mattermost | Webhook URL / Token | Mattermost 系统控制台 |
| 10 | Matrix | 用户名+密码+Homeserver | Matrix 账号 |
| 11 | 钉钉 (DingTalk) | App Key + App Secret | 钉钉开发者后台创建应用 |
| 12 | **飞书 (Feishu/Lark)** | App ID + App Secret | 飞书开发者后台创建应用 |
| 13 | 企业微信 (WeCom) | Corp ID + Agent ID + Secret | 企业微信后台 |
| 14 | WeCom Callback | Token + EncodingAESKey | 企业微信自建应用 |
| 15 | **微信 (Weixin)** | 扫码登录 | 手机微信扫码 |
| 16 | BlueBubbles (iMessage) | Server URL + Password | BlueBubbles 服务器 |
| 17 | QQ Bot | App ID + Token | QQ 开放平台 |
| 18 | 元宝 (Yuanbao) | API Key | 元宝平台 |
| 19 | Open WebUI | API Key + URL | Open WebUI 实例 |
| 20 | Webhooks | Webhook URL | 任意 Webhook 端点 |

> 列表来自 Hermes 官方文档：https://hermes-agent.nousresearch.com/docs/user-guide/messaging/
>
> 特殊提示：微信的配置方式是扫码登录，不需要用户在外部创建应用。飞书和钉钉需要先去开发者后台创建应用拿 AppID+Secret。

---

## 第二步：引导用户获取凭据

用户选好平台后，根据平台类型，引导用户在对应平台的后台获取所需凭据。

### 需要扫码/配对（用户手机操作即可）
- **微信**：AI 在后台调用 iLink API 获取二维码，通过聊天发给用户，用户扫码确认
- **WhatsApp**：用户用手机 WhatsApp 扫描配对二维码

### 需要用户去外部平台创建应用/拿 token
这类平台需要用户在外部注册、创建 bot/应用，然后把凭据发给 AI。

**引导方式示例（以 Telegram 为例）：**

```
要连 Telegram 的话，需要你去做两件事：

1️⃣ 打开 Telegram，搜索 @BotFather
2️⃣ 发送 /newbot，按提示创建你的 bot
3️⃣ BotFather 会给你一个 API Token，长这样：
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
4️⃣ 把这个 Token 发给我
```

**不同平台的引导要点：**

| 平台 | 引导要点 |
|------|---------|
| Telegram | @BotFather → /newbot → 复制 token |
| Discord | Discord Developer Portal → New Application → Bot → 复制 token |
| Slack | api.slack.com → Create App → Bot Token + App-Level Token |
| 飞书 | open.feishu.cn → 创建应用 → 凭证与基础信息 → 复制 App ID 和 App Secret |
| 钉钉 | open.dingtalk.com → 创建应用 → 复制 AppKey 和 AppSecret |
| 企业微信 | work.weixin.qq.com → 应用管理 → 自建应用 → 获取 CorpID、AgentID、Secret |

> 引导要简短清晰，写完整的"第1步、第2步"让用户可操作。
> 用户拿到凭据后直接发到聊天里即可。

---

## 第三步：AI 自动写入配置

用户发来凭据后，AI 执行以下操作：

1. 写入 `~/.hermes/.env`：
   - 用 `patch` 工具在文件末尾的"实际配置区"追加对应的环境变量
   - 格式：`变量名=值`（注意 `=` 两边不要有空格）
   - 注意不要覆盖已有的其他配置
   - 如果变量已存在（如 `***` 占位符），用 `patch` 的 replace_all 模式替换掉 `=***`
   - ⚠️ 不要用 `cat >>` 追加，因为 `.env` 文件结构复杂（大量注释模板），追加可能插错位置

   **实际配置追加示例（patch 工具）：**
   ```
   # 在 ~/.hermes/.env 末尾看到类似
   # FEISHU_GROUP_POLICY=open
   # FEISHU_HOME_CHANNEL=oc_xxx
   # 
   # 就在这之后追加新的变量
   ```
   
   **替换占位符示例（patch 工具）：**
   ```
   # old: TELEGRAM_BOT_TOKEN=***
   # new: TELEGRAM_BOT_TOKEN=123456789:ABCdef...
   ```

2. 如果平台需要额外依赖，通过 `terminal` 安装：
   ```bash
   cd ~/.hermes/hermes-agent
   pip install 需要的包
   ```

3. 重启 Gateway：
   ```bash
   systemctl --user restart hermes-gateway
   ```
   > ⚠️ 如果当前对话正通过 Gateway 进行，AI 不能自己执行重启命令。
   > 改为告知用户：`请在终端执行：systemctl --user restart hermes-gateway`
   > 或如果 AI 在云电脑上，可以在非 Gateway 环境中执行。

---

## 第四步：验证

重启后，让用户在刚配置的平台上发条消息测试是否连通。

---

## 各平台环境变量参考

### Telegram
```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_ALLOWED_USERS=
TELEGRAM_HOME_CHANNEL=
```

### Discord
```bash
DISCORD_BOT_TOKEN=
DISCORD_APP_ID=
DISCORD_ALLOWED_USERS=
```

### Slack
```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ALLOWED_USERS=
```

### 飞书
```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_DOMAIN=feishu
FEISHU_CONNECTION_MODE=websocket
FEISHU_HOME_CHANNEL=
```

### 钉钉
```bash
DINGTALK_APP_KEY=
DINGTALK_APP_SECRET=
DINGTALK_HOME_CHANNEL=
```

### 企业微信
```bash
WECOM_CORP_ID=
WECOM_AGENT_ID=
WECOM_SECRET=
WECOM_HOME_CHANNEL=
```

### 微信
```bash
WEIXIN_ACCOUNT_ID=   # 扫码登录后自动获取
WEIXIN_TOKEN=        # 扫码登录后自动获取
WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com
WEIXIN_HOME_CHANNEL=
```

### Email
```bash
EMAIL_ADDRESS=your@email.com
EMAIL_PASSWORD=xxx
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_HOME_ADDRESS=your@email.com
```

---

## 常见问题

### Q: 用户说"我不懂怎么创建应用"
- 如果是飞书/钉钉这类需要创建应用的，告诉用户这是该平台的标准流程
- 可以直接给用户发对应的官方文档链接
- 如果用户实在不会，也可以让用户把后台页面的链接或截图发过来，AI 帮忙指引

### Q: 凭据发到聊天里安全吗？
- 微信和飞书的聊天内容是端到端传输的
- 敏感信息（token/secret）AI 写入 `.env` 后不会保存到记忆中
- 建议用户配置完成后去 `.env` 检查，并定期更换密钥

### Q: AI 不能自己重启 Gateway
- 如果当前会话正通过 Gateway 进行，AI 执行 `systemctl --user restart hermes-gateway` 会杀掉自己的连接
- 解决方案：让用户在终端手动执行重启命令
- 如果 AI 在云电脑上，可以用另一个会话执行（非 Gateway 进程）
