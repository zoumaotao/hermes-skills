---
name: feishu-archive
description: 把内容存到飞书云文档并关联知识库。用户说"存了"或"把这个存飞书"时，我自动完成上传→导入为文档→关联知识库。
---

# 飞书云文档归档

## 使用场景

用户发来文件/链接/聊天内容，我处理后（总结/提炼/生成），用户审阅后说"存了"或"把这个存飞书"，我自动归档到飞书知识库。

## 前置条件

- Feishu 平台连接正常（Gateway 运行中）
- 环境变量 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 已配置
- 以下工具可用：
  - `feishu_doc_create` — 创建空白文档
  - `feishu_drive_upload` — 上传文件到云盘
  - `feishu_drive_import` — 导入为云文档
  - `feishu_wiki_list_spaces` — 列出所有知识库空间
  - `feishu_wiki_create_node` — 创建知识库节点（关联文档）

## 工作流

### 方案A：已有文件 → 上传导入 → 关联知识库（最稳）

适合 PDF、HTML、MD、图片等已有文件，不依赖 block API 格式校验。

```
1. feishu_drive_upload(file_path, file_name)        # 上传到云盘
   → 返回 file_token

2. feishu_drive_import(file_token, file_name, ext)  # 导入为云文档
   → 返回 doc_token、doc_url

3. feishu_wiki_list_spaces()                        # 查可用的知识库
   → 选一个 space_id（或让用户指定）

4. feishu_wiki_create_node(space_id, title, obj_token)
   → 把文档关联到知识库
   → 返回 node_token、知识库链接
```

### 方案B：纯文本内容 → 创建文档 → 写内容 → 关联知识库

适合在线生成的总结/报告/笔记。注意：飞书 block API 格式校验严格，空行/空文本会报错。

```
1. feishu_doc_create(title)                          # 创建空白文档
   → 返回 doc_token、doc_url

2. 内容较多时：先生成 MD 文件，走方案A上传导入
   内容较少时：用 feishu_doc_add_blocks 直接写（注意避免空block）

3. feishu_wiki_create_node(space_id, title, obj_token)
   → 关联知识库
```

## 踩坑记录

### 1. get_client() 返回 None

**问题**：feishu_doc_create 等工具的 get_client() 只从 thread-local 获取 client，
而 thread-local client 只由 feishu_comment 事件处理器注入。其他线程调用时 client 为 None。

**修复**：get_client() 增加 fallback：检查环境变量 FEISHU_APP_ID/FEISHU_APP_SECRET，
自动创建 lark client。已修复于 feishu_doc_tool.py 和 feishu_drive_tool.py。

### 2. 工具注册了但不可用

**问题**：feishu_doc_create 等工具只在 feishu_doc toolset 里注册了，
但飞书平台加载的是 hermes-feishu toolset，里面没有包含新工具。

**修复**：在 toolsets.py 的 hermes-feishu 下也加上新工具列表。

### 3. block API 格式校验严格

**问题**：feishu_doc_add_blocks 要求 block 格式极其严格：
- 不能有空文本元素（text_element 必须有非空 text）
- 不支持 divider block 类型
- 空行需要特殊处理

**对策**：内容多时优先用方案A（导出文件 → 上传导入），
避免直接调 block API。

### 4. 工具变更需要新会话

**问题**：修改 toolsets.py 后 Gateway 重启了，但当前会话的工具列表是启动时缓存的。

**对策**：改 toolset 后需要 `/reset` 或新会话才生效。

## 常用命令

```
# 列出知识库空间
feishu_wiki_list_spaces()

# 上传文件
feishu_drive_upload(file_path="/path/to/file.md", file_name="标题.md")

# 导入为文档
feishu_drive_import(file_token="xxx", file_name="标题", file_extension="md")

# 关联知识库（link模式：引用已有文档）
feishu_wiki_create_node(space_id="xxx", title="标题", obj_token="xxx")

# 创建新节点（origin模式：新建空白文档）
feishu_wiki_create_node(space_id="xxx", title="标题")
```

## 关于知识库

飞书知识库（Wiki）的结构：
- space（空间）= 一个独立的知识库
- node（节点）= 知识库里的一篇文章/页面
- 节点可以有父子关系（树结构）
- 一个文档可以被多个空间引用，但每个空间只能有一个 node 指向它

用关键词自然生长分类：不需要预先设计复杂目录结构，
用户说"存到[关键词]"就按关键词作为归类线索。
