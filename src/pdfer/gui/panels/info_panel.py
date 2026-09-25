"""文档信息面板：只读展示 PDF 的元信息。"""

from __future__ import annotations

from html import escape

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ...core import DocInfo, read_info
from ...core.errors import PdfError
from ..widgets import Hint, PathRow, make_password_edit
from .base import Panel

_MISSING = "—"


class InfoPanel(Panel):
    title = "文档信息"
    description = "查看页数、纸张尺寸、加密状态与元数据，不修改任何内容。"

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.make_header(self.title, self.description))

        self.source = PathRow("源文件")
        self.source.changed.connect(lambda _: self._on_read())
        layout.addWidget(self.source)

        row = QHBoxLayout()
        row.addWidget(QLabel("密码"))
        self.password = make_password_edit()
        self.password.setFixedWidth(240)
        row.addWidget(self.password)
        row.addStretch(1)
        self.read_button = QPushButton("重新读取")
        self.read_button.clicked.connect(self._on_read)
        row.addWidget(self.read_button)
        layout.addLayout(row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setPlaceholderText("选择一个 PDF 文件后，这里会显示它的详细信息。")
        layout.addWidget(self.browser, 1)

        self.raw_hint = Hint("")
        layout.addWidget(self.raw_hint)

    # ------------------------------------------------------------------ 交互

    def _on_read(self) -> None:
        path = self.source.path
        if not path:
            self.browser.clear()
            self.raw_hint.clear()
            return

        try:
            info = read_info(path, self.password.text() or None)
        except PdfError as exc:
            self.browser.setHtml(
                f"<p style='color:#a32d2d;'>无法读取该文件：</p><p>{escape(str(exc))}</p>"
            )
            self.raw_hint.clear()
            return

        self.browser.setHtml(self._render(info))
        self.raw_hint.setText("页数为实际解析结果；加密状态由 PDF 内部的加密字典决定。")
    def _render(self, info: DocInfo) -> str:
        def row(label: str, value: str) -> str:
            text = escape(value) if value else _MISSING
            dim = "" if value else "color:#9ca3af;"
            return (
                "<tr>"
                f"<td style='padding:4px 16px 4px 0;color:#6b7280;white-space:nowrap;'>{escape(label)}</td>"
                f"<td style='padding:4px 0;{dim}'>{text}</td>"
                "</tr>"
            )

        sizes = "".join(
            f"<li>{escape(label)}：{count} 页</li>" for label, count in info.size_summary
        )
        uniform = "全部页面尺寸一致" if info.is_uniform_size else "页面尺寸不统一"

        outline_text = (
            f"有 {info.outline_count} 个书签" if info.has_outline else "无书签"
        )

        return f"""
        <div style="font-family:'Microsoft YaHei UI','Segoe UI',sans-serif;font-size:13px;color:#1f2430;">
          <h3 style="margin:0 0 8px 0;font-size:14px;font-weight:500;">{escape(info.name)}</h3>
          <table style="border-collapse:collapse;font-size:13px;">
            {row('页数', f'{info.page_count} 页')}
            {row('文件大小', info.file_size_text + f'（{info.file_size:,} 字节）')}
            {row('PDF 版本', info.pdf_version)}
            {row('加密状态', '已加密（需要密码）' if info.encrypted else '未加密')}
            {row('书签', outline_text)}
            {row('标题', info.title)}
            {row('作者', info.author)}
            {row('主题', info.subject)}
            {row('关键词', info.keywords)}
            {row('创建工具', info.creator)}
            {row('生成程序', info.producer)}
            {row('创建时间', info.creation_date)}
            {row('修改时间', info.modification_date)}
          </table>
          <h4 style="margin:14px 0 4px 0;font-size:13px;font-weight:500;">页面尺寸（{uniform}）</h4>
          <ul style="margin:0;padding-left:20px;font-size:13px;">{sizes or '<li>—</li>'}</ul>
        </div>
        """
