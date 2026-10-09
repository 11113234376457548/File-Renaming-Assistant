# 贡献指南

感谢你有兴趣改进本项目。以下流程可以让你的改动更快被合并。

## 环境准备

```bash
git clone https://github.com/11113234376457548/File-Renaming-Assistant.git
cd File-Renaming-Assistant
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

## 开发约定

1. **引擎与界面必须保持解耦**。`src/renamer/core.py` 不允许导入任何 Qt 模块，
   否则单元测试将无法在没有显示器的环境中运行。
2. **英文标识符，中文注释与文档**。面向用户的文案（界面、README）使用中文。
3. **行宽 100**，遵循 `ruff` 配置。
4. **行为改动必须补测试**。新增规则或修复缺陷时，请在 `tests/` 下添加用例。

## 提交前自检

```bash
python -m pytest -q      # 全部通过
ruff check .             # 无告警
```

若改动了界面，请顺带更新文档截图：

```bash
python scripts/screenshot.py
```

## 提交信息

采用 [约定式提交](https://www.conventionalcommits.org/zh-hans/)：

```
feat: 支持按 EXIF 拍摄时间重命名
fix: 修复空目录导致的崩溃
docs: 补充撤销机制的说明
test: 补充交换名撤销的边界用例
```

## 分支与 PR

1. 从 `main` 切出特性分支：`git checkout -b fix/undo-swap`
2. 保持单次 PR 聚焦一个问题，避免夹带无关格式化改动。
3. PR 描述中说明：**改了什么、为什么改、如何验证**。
4. 确保 CI 全绿后再请求评审。

## 报告问题

请使用仓库的 Issue 模板，并尽量提供：

- 操作系统与 Python 版本；
- 复现步骤（文件名示例、所填参数）；
- 期望结果与实际结果；
- 必要时附上截图。

> 安全相关的问题请勿公开提交 Issue，请通过邮箱私下联系维护者。
