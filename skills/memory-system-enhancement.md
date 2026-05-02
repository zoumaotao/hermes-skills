---
name: memory-system-enhancement
description: "轻量增强 Hermes Agent 记忆系统——加时间戳、排序、top-K 截断。Use when the user says '记忆太乱了' / '能不能把记忆变智能一点' / '记忆没有时间概念' / '记忆太多被截断' — requires modifying tools/memory_tool.py in ~/.hermes/hermes-agent/."
version: 1.0.0
author: zoumaotao
license: MIT
metadata:
  hermes:
    tags: [memory, enhancement, hermes-agent, python, timestamp, sorting]
    related_skills: [code-change-decision-framework, code-change-safety-net, systematic-debugging]
---

# 记忆系统增强 — 时间戳 + 排序 + top-K 上限控制

> 适用场景：Hermes Agent 内置记忆（MEMORY.md / USER.md）是扁平的字符串列表，不分层不分类不衰减。需要轻量增强来让记忆有时间维度、排序合理、系统提示不因记忆过多而被 silent truncation。

## 架构决策

### 核心原则

1. **不改存储格式** — 保持 `§` 分隔的文本文件，不升级到 JSON Lines。收益有限，但引入解析复杂度和转义问题。
2. **不改工具 schema** — 不新增参数/action，所有过滤在渲染层自动完成。保持 API 稳定。
3. **磁盘全量保留** — add/replace/remove 操作磁盘上所有条目，注入时只截断显示。存的时候全存，用的时候只放最重要的。
4. **磁盘软上限 2x** — 避免磁盘无限膨胀，但比注入上限宽松 1 倍（memory: 4400, user: 2750）。
5. **零外部依赖** — 不引入 embedding、向量数据库、Mem0/Letta。`session_search` 的 FTS5 已覆盖语义搜索需求。

### 不做的事

| 不要做 | 原因 |
|---|---|
| LLM 自动打分排序 | 每次写记忆都调一次模型，成本高延迟大；时间倒序已够用 |
| Ebbinghaus 遗忘曲线 | 需要跟踪每个条目的年龄+被引用次数+上次使用，过度工程化 |
| 向量数据库 | 零外部依赖是优势，当前 FTS5 + 纯文本规则覆盖 95% |
| Core/Archive 分层 | 注入时 top-K 截断 + 磁盘全保留，等价于但更简单 |

## 改动的文件

`tools/memory_tool.py` 中的 `MemoryStore` 类。

### 修改点概览

**分组 A：时间戳 + 元数据处理**

```python
@staticmethod
def _format_entry(content: str) -> str:
    now = time.strftime("%Y-%m-%d")
    if " |t:" in content:
        return content
    return f"{content} |t:{now}"

@staticmethod
def _strip_metadata(content: str) -> str:
    idx = content.rfind(" |t:")
    if idx != -1:
        return content[:idx].strip()
    return content
```

引用点：`add()`、`replace()`、`_success_response()`、`_render_block()`

**分组 B：排序**

按最新在前排序，有 `|t:` 的始终排在无时间戳的之前，同优先级的按日期倒序。

**分组 C：top-K 注入上限控制**

重写 `_render_block()` — 按优先级和时间排序后，贪婪地选取条目直到达到字符上限，超出部分（最旧/低优先级）舍弃。头部添加 `(showing N/M entries — oldest excluded)` 提示。

**分组 D：磁盘上限放宽到 2x**

`add()` 和 `replace()` 中磁盘上限从 `char_limit` 改为 `char_limit * 2`。

### 完整修改清单

| 分组 | 改了什么 | 代码位置 |
|---|---|---|
| A | 新增 `_format_entry()` | 静态方法 |
| A | 新增 `_strip_metadata()` | 静态方法 |
| B | 新增 `_sort_entries()` | 静态方法 |
| C | 重写 `_render_block()` | 方法体 |
| D | `add()` 的 `limit` → `disk_limit = limit * 2` | add 方法 |
| D | `replace()` 的 `limit` → `disk_limit = limit * 2` | replace 方法 |

## 测试验证

**不 mock 文件 IO，创建临时目录测试：**

```python
import tempfile
fake_home = Path(tempfile.mkdtemp())
os.environ["HERMES_HOME"] = str(fake_home / ".hermes")
store = MemoryStore(memory_char_limit=500, user_char_limit=300)
```

### 必测场景

1. **上限截断** — 3 个长条目各 200 字符，上限 500，验证只注入 2 个，header 显示 `showing 2/3 entries`
2. **单超长条目不截断** — 1 条 1000 字符，上限 500，验证仍完整注入
3. **不超上限不截断** — 少量数据，header 无 `showing` 提示
4. **空条目返回空字符串**
5. **add 超注入上限但未超磁盘上限** — 验证成功写入
6. **add 超磁盘上限** — 验证被拒绝
7. **remove + add 循环** — 验证磁盘上限动态更新
8. **无时间戳条目排序** — 验证排最后

## 风险与回滚

### 风险
- 磁盘上限 2x 意味着磁盘文件可能膨胀到 2 倍，正常使用不影响
- `add` 返回的 `current_entries` 现在含剥离元数据（与改前一致，无影响）

### 回滚
```bash
cd ~/.hermes/hermes-agent
git checkout -- tools/memory_tool.py
# 或从备份恢复
cp tools/memory_tool.py.bak tools/memory_tool.py
```

## 扩展思路（按优先级）

| 优先级 | 做什么 | 收益 | 复杂度 |
|---|---|---|---|
| P1 | 分类标签 (`\|c:xxx`) | 按类别选择性注入 | 中 |
| P2 | 按分类选择性注入 | 进一步省 token | 中 |
| P3 | 自动淘汰/环形缓冲区 | 磁盘不无限膨胀 | 高 |
| P4 | 优先级评分（重要性×时间） | 智能排序 | 高 |

## Gotchas

- 这个改动涉及生产环境正在运行的代码。改前必须按照 `code-change-safety-net` 做备份
- 测试时一定用临时目录，不要在生产 `~/.hermes/memory.*` 文件上测试
- 改完重启 Gateway 前必须先问用户
