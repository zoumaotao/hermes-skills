# hermes

我的 Hermes Agent 配置集合。

## 结构

```
hermes/
├── skills/     # Hermes Agent 技能（SKILL.md）— 我学会的套路和流程
└── tools/      # 工具代码存档 — Hermes Agent 框架的自定义扩展
                # 这些文件是我对 hermes-agent 开源项目的改动，
                # 参考 docs/hermes-agent-框架说明.md 了解上下文
```

## tools/ 说明

`tools/` 里的文件是我对 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 开源框架的本地修改/新增，存放在此作为备份和记录。

这些文件**不能独立运行**——它们依赖 hermes-agent 的工具注册系统（`tools/registry.py`）和 `lark_oapi` 库。要使用这些改动，需要将它们复制回 `~/.hermes/hermes-agent/tools/` 对应位置。

### 文件清单

| 文件 | 来源 | 用途 |
|------|------|------|
| `feishu_doc_tool.py` | tools/feishu_doc_tool.py | 飞书文档读写（创建、上传、导入） |
| `feishu_drive_tool.py` | tools/feishu_drive_tool.py | 飞书评论管理 |
| `feishu_wiki_tool.py` | tools/feishu_wiki_tool.py | 飞书知识库节点管理（新建、查询） |
| `send_message_tool.py` | tools/send_message_tool.py | 跨平台消息发送 |
| `toolsets.py` | toolsets.py | 工具集注册表（修改版） |

### 背景

这些改动是为了打通「飞书云文档归档」链路而做的：
- 修复了 `get_client()` 返回 None 的问题（新增环境变量自动初始化）
- 新增了 `feishu_doc_create`、`feishu_drive_upload`、`feishu_drive_import` 等工具
- 新增了 `feishu_wiki_list_spaces`、`feishu_wiki_create_node`、`feishu_wiki_get_node`
- 更新了 toolsets.py 中 `feishu_doc` 和 `hermes-feishu` 的注册
