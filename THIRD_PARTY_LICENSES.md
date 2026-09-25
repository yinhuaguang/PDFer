# 第三方依赖许可证

PDFer 自身以 [MIT](LICENSE) 协议发布。下表列出主要运行时依赖及其协议。
第三方组件继续遵循各自许可证；本文件用于说明项目的依赖与分发方式，不构成法律意见。

## 运行时依赖

| 依赖 | 协议 | 用途 | 合规要求 |
|---|---|---|---|
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | 合并、拆分、页面操作、加密、元数据 | 保留版权声明 |
| [pikepdf](https://github.com/pikepdf/pikepdf) | MPL-2.0 | PDF 结构优化、AES-256 加密/解密 | 修改其 MPL 覆盖文件时遵守 MPL-2.0 |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Apache-2.0 | 页面渲染（转图片、缩略图） | 保留声明与 NOTICE |
| [PDFium](https://pdfium.googlesource.com/pdfium/) | BSD-3-Clause | pypdfium2 的底层引擎（Chrome 的 PDF 引擎） | 保留版权声明 |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU | 图像处理 | 保留声明 |
| [PySide6 / Qt](https://www.qt.io/) | LGPL-3.0 | GUI 框架 | 见下方「PySide6 合规说明」 |

## 开发依赖（不随程序分发）

| 依赖 | 协议 | 说明 |
|---|---|---|
| pytest | MIT | 测试 |
| PyInstaller | GPL-2.0-or-later + 例外条款 | 构建 Windows 可执行文件 |
| reportlab | BSD-3-Clause | 仅在测试中动态生成样例 PDF，不进入正式 EXE |

---

## PySide6 合规说明（重要）

PySide6 采用 **LGPL-3.0**，不是 AGPL。这意味着：

- ✅ 你**可以**以 MIT 或闭源方式分发使用 PySide6 的程序
- ⚠️ 但必须满足 LGPL 的两项要求

### Qt / PySide6 的分发方式

本项目同时保留两种构建：

- `pdfer.spec`：目录版，Qt DLL 独立存在，便于检查、替换和调试；
- `pdfer-onefile.spec`：面向普通 Windows 用户的单 EXE 版本，运行时由 PyInstaller 解包依赖。

仓库公开完整应用源码、构建脚本和依赖声明，便于用户自行重新构建或改用其它 Qt/PySide6 版本。实际发布者仍应根据自己的分发方式核对 LGPL-3.0 的完整义务。

### 保留版权与许可证通知

程序内「帮助 → 关于」页面列出主要第三方组件；仓库同时保留本文件与项目许可证。
单 EXE 构建会把 `LICENSE` 和 `THIRD_PARTY_LICENSES.md` 作为资源打入程序。

---

## 关于 PyMuPDF（AGPL-3.0）——本项目**未使用**

PyMuPDF（`fitz`）功能强大，但采用 **AGPL-3.0**。本项目刻意不引入它，原因：

1. 它要求**任何分发行为**都必须提供完整对应源码；
2. 大量公司明令禁止在内部使用 AGPL 软件，会直接损失这部分用户；
3. 其独有的两个能力（**彻底涂黑 redaction**、**增量更新**）目前不在功能范围内，
   而其余功能均可由上述宽松协议库完整实现，引入它带来的收益为零。

**如果将来确实需要这两个能力**，只有两条路：

- 将本项目整体改为 **AGPL-3.0**，或
- 向 Artifex 购买 PyMuPDF **商业授权**

任何情况下都不应在 MIT 协议的本体中混入 PyMuPDF 代码。
