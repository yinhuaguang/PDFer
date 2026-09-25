"""程序入口：``python -m pdfer``（打包后即 PDFer.exe）。"""

from __future__ import annotations

import sys
import traceback


def _install_excepthook() -> None:
    """把未捕获异常变成对话框 + 崩溃日志，而不是让窗口凭空消失。"""
    from PySide6.QtWidgets import QMessageBox

    def hook(exc_type, exc_value, exc_tb) -> None:  # type: ignore[no-untyped-def]
        if issubclass(exc_type, KeyboardInterrupt):
            try:
                sys.__excepthook__(exc_type, exc_value, exc_tb)
            except Exception:  # noqa: BLE001 - 无控制台时 stderr 为 None
                pass
            return

        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

        # 打包成 exe 后是无控制台的窗口程序，sys.stderr 为 None，
        # 只打印就会把栈信息丢掉，所以同时落一份日志文件。
        if sys.stderr is not None:
            print(detail, file=sys.stderr)
        log_path = _write_crash_log(detail)

        message = f"发生了未预期的错误：\n\n{exc_value}"
        if log_path is not None:
            message += f"\n\n错误详情已记录到：\n{log_path}"
        QMessageBox.critical(None, "程序遇到问题", message)

    sys.excepthook = hook


def _write_crash_log(detail: str) -> Path | None:
    """把异常栈追加到用户目录下的日志，返回日志路径；失败则返回 ``None``。"""
    import os
    from datetime import datetime
    from pathlib import Path

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP")
    if not base:
        return None
    try:
        path = Path(base) / "PDFer" / "last_error.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n===== {stamp} =====\n{detail}")
        return path
    except OSError:
        return None


def _set_app_user_model_id() -> None:
    """让任务栏把 PDFer 当成独立程序，而不是 python.exe。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes  # noqa: PLC0415

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFer.Desktop.1")
    except Exception:  # noqa: BLE001 - 仅为美化任务栏图标，失败无妨
        pass


def _run_self_test() -> int:
    """验证正式打包产物中的核心原生依赖是否都能加载和工作。"""
    import tempfile
    from pathlib import Path

    try:
        from PIL import Image
        from pypdf import PdfReader, PdfWriter

        from pdfer.core import images_to_pdf, optimize_pdf, protect_pdf, unprotect_pdf

        with tempfile.TemporaryDirectory(prefix="pdfer-selftest-") as temp:
            root = Path(temp)

            source = root / "source.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with source.open("wb") as handle:
                writer.write(handle)

            image_a = root / "a.png"
            image_b = root / "b.png"
            Image.new("RGB", (80, 60), (240, 80, 80)).save(image_a)
            Image.new("RGB", (80, 60), (80, 120, 240)).save(image_b)

            image_pdf = images_to_pdf([image_a, image_b], root / "images.pdf")
            if len(PdfReader(str(image_pdf)).pages) != 2:
                raise RuntimeError("图片转 PDF 页数校验失败")

            optimized = optimize_pdf(source, root / "optimized.pdf")
            protected = protect_pdf(optimized.output, root / "protected.pdf", user_password="pdfer-test")
            plain = unprotect_pdf(protected, root / "plain.pdf", password="pdfer-test")
            if len(PdfReader(str(plain)).pages) != 1:
                raise RuntimeError("PDF 加密/解密校验失败")

        print("PDFer self-test: OK")
        return 0
    except Exception:  # noqa: BLE001 - self-test 必须输出完整诊断
        traceback.print_exc()
        print("PDFer self-test: FAILED")
        return 1


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    if "--self-test" in args:
        return _run_self_test()

    _set_app_user_model_id()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    # 这里刻意用绝对导入（``pdfer.xxx``）而不是相对导入（``.xxx``）：
    # 打包成 exe 时 PyInstaller 会把本文件当顶层脚本执行，此时它不属于任何包，
    # 相对导入会抛 "attempted relative import with no known parent package"。
    # 绝对导入在 ``python -m pdfer`` 和打包后两种场景下都成立。
    from pdfer.gui.main_window import MainWindow
    from pdfer.gui.theme import apply_theme
    from pdfer.gui.widgets import pil_to_qpixmap
    from pdfer.icon import render_icon
    from pdfer.version import __app_name__, __version__

    app = QApplication(args)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__app_name__)
    # 注意：不要再调 setApplicationDisplayName()。Qt 会把它拼到每个窗口标题末尾，
    # 而本程序的窗口标题里已经含 "PDFer"，会变成
    # "PDFer 0.1.0 — 免费开源的 PDF 工具箱 - PDFer" 这种重复。
    app.setWindowIcon(QIcon(pil_to_qpixmap(render_icon(256))))

    apply_theme(app)
    _install_excepthook()

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
