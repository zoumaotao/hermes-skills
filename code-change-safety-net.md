# 代码改动安全流程 — 改前备份、改时检查、改后测试、可回滚

> 适用场景：你需要修改正在运行中的代码（如 `tools/`、`hermes_ai_backend/` 目录下的文件），修改后要重新生效。
>
> 触发条件：任何对 `~/.hermes/hermes-agent/` 目录中 Python 文件的修改操作。

## 安全四步曲

### 第一步：改前 — 建立安全基线

```bash
# 1. 确认当前所在目录
cd ~/.hermes/hermes-agent

# 2. 确认 git 状态
git log --oneline -3
git status --short

# 3. 备份要改的文件
cp tools/memory_tool.py tools/memory_tool.py.bak
# 或统一备份到目录
mkdir -p /tmp/hermes-change-backup
cp tools/memory_tool.py /tmp/hermes-change-backup/$(date +%Y%m%d_%H%M%S)_memory_tool.py
```

> ⚠️ 如果该文件没有 git 版本控制或不在 git 仓库中，**必须手动备份**。

### 第二步：改中 — 每改完一个逻辑块立即检查

不要一次改完再检查，应该：

```python
# 每个修改块完成后立即：
import py_compile
py_compile.compile('tools/memory_tool.py', doraise=True)
# 若有 import 错误则：
python -c "import sys; sys.path.insert(0, '.'); from tools.memory_tool import MemoryStore; print('OK')"
```

如果是多个文件改动，在每个文件独立修改后分别检查语法，而非一起改完。

### 第三步：改后 — 功能测试

> **核心原则：不 mock 文件 IO，用临时目录做真实 IO 测试。**

创建独立测试文件：

```python
# test_xxx.py
import os, sys, tempfile
from pathlib import Path

# 1. 创建临时 HOME 环境
fake_home = Path(tempfile.mkdtemp())
os.environ["HERMES_HOME"] = str(fake_home / ".hermes")

# 2. 导入被测试类
sys.path.insert(0, ".")
from tools.memory_tool import MemoryStore

# 3. 用较小的字符上限测试边界
store = MemoryStore(memory_char_limit=500, user_char_limit=300)

# 4. 运行测试（场景清单如下）
# ...
```

#### 必测场景清单

| 分类 | 测试场景 | 验证点 |
|------|---------|--------|
| **正常路径** | 基本增删改查 | 功能不变 |
| **上限截断** | 故意填入超过上限的数据 | 被截断，header 有提示 |
| **单超长条目** | 一条就超限的数据 | 不被截断（保证至少一条） |
| **不过限** | 少量数据 | 不截断，无额外提示 |
| **空数据** | 零条目 | 返回空，不报错 |
| **边界** | 写入超磁盘上限 | 被拒绝，提示明确 |
| **幂等** | 重复操作 | 不产生数据重复 |

### 第四步：上线 — 重启生效

只有测试全部通过后，才可以重启服务。

```bash
# 确认测试通过后，清理临时测试文件
rm -rf /tmp/test_hermes_memory*
rm -rf /tmp/hermes-change-backup

# 询问用户是否要重启 Gateway（如果用户已连 IM）
# 不要自己直接重启
```

## 回滚流程

### 如果有 git 跟踪

```bash
cd ~/.hermes/hermes-agent
git checkout -- tools/memory_tool.py  # 恢复到最新提交
```

### 如果有备份文件

```bash
cp /tmp/hermes-change-backup/<TIMESTAMP>_memory_tool.py ~/.hermes/hermes-agent/tools/memory_tool.py
```

### 检查回滚后的状态

```bash
python -c "import sys; sys.path.insert(0, '.'); from tools.memory_tool import MemoryStore; print('回滚验证通过')"
```

## 常见风险

| 风险 | 后果 | 预防 |
|------|------|------|
| 改了未测试 | 运行时报错，影响用户使用 | 强制执行第三步，不跳过 |
| 测试通过但重启后有问题 | 服务不可用 | 保留备份直到用户确认新版本正常 |
| 改完后忘记重启 | 改动未生效，用户以为没做 | 第四步必须做 |
| 多个文件连环改 | 局部回滚困难 | 每次只改一个文件，测完再改下一个 |
| 无意中杀了 Gateway 进程 | 服务中断 | 不要自己 kill 进程，用 process list 确认再用安全方式重启 |
