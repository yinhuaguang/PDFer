# Contributing

感谢你愿意改进 PDFer。

## 开发环境

推荐 Windows 10/11 + Python 3.10 及以上版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

启动：

```powershell
python -m pdfer
```

测试：

```powershell
pytest
```

## 代码结构

```text
src/pdfer/core/        纯 PDF 业务逻辑，不依赖 Qt
src/pdfer/gui/         PySide6 图形界面
src/pdfer/gui/panels/  各功能面板
tests/                 核心逻辑与 GUI smoke tests
```

新增功能优先放在 `core` 层，并为核心逻辑补测试；GUI 只负责收集参数、提交任务和展示结果。

## Pull Request

提交 PR 前请确保：

1. `pytest` 全部通过；
2. 不把用户 PDF、临时文件、`build/` 或 `dist/` 提交到仓库；
3. 新增运行时依赖前先说明必要性、许可证和对 EXE 体积的影响；
4. 不引入 AGPL 依赖到当前 MIT 主项目；
5. 耗时操作不要阻塞 Qt 主线程。

## 依赖原则

PDFer 的目标是“小而够用”。新增依赖应优先考虑：

- 是否能复用现有 pypdf / pikepdf / PDFium / Pillow 能力；
- 是否会明显增加单 EXE 体积；
- 是否要求外部程序或在线服务；
- 是否对开源许可证造成新的分发义务。

OCR、PDF 转 Word、复杂正文编辑等重型功能应单独讨论，不默认进入核心发行版。
