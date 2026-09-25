"""PDFer 核心层的异常体系。

设计原则：核心层不依赖任何 GUI 框架，所有面向用户的错误都表现为
携带**中文可读信息**的 :class:`PdfError` 子类，由界面层直接展示。
"""

from __future__ import annotations


class PdfError(Exception):
    """所有 PDFer 业务异常的基类。消息面向最终用户，可直接展示。"""


class PdfOperationError(PdfError):
    """通用操作失败：文件损坏、路径无效、依赖库报错等。"""


class PdfEncryptedError(PdfError):
    """文档已加密，且未提供密码或密码错误。"""


class PdfPasswordError(PdfError):
    """密码错误。"""


class PageRangeError(PdfError):
    """页码范围表达式无法解析。"""


class TaskCancelledError(PdfError):
    """任务被用户主动取消。

    并非真正的错误，界面层应当静默处理（提示"已取消"而非"失败"）。
    """
