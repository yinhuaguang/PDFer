"""PDF 读写的公共工具：打开、密码校验、输出路径处理。"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from .errors import PdfEncryptedError, PdfOperationError

PDF_SUFFIX = ".pdf"


def is_pdf(path: str | Path) -> bool:
    """判断是否为 PDF 文件（仅看扩展名，不读内容）。"""
    return Path(path).suffix.lower() == PDF_SUFFIX


def human_size(num_bytes: int | float) -> str:
    """把字节数格式化成人类可读的字符串。"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def open_reader(path: str | Path, password: str | None = None) -> PdfReader:
    """安全地打开 PDF，并处理加密与损坏两种情况。

    加密文档若用户未提供密码，会尝试用空密码解密——大量 PDF 只是加了
    权限密码（禁止打印/复制）而并未设置打开密码，空密码即可解开。

    Raises:
        PdfOperationError: 文件不存在、损坏或没有页面。
        PdfEncryptedError: 需要密码而密码缺失或错误。
    """
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise PdfOperationError(f"文件不存在：{pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - 底层库异常类型不稳定，统一兜底
        raise PdfOperationError(f"无法读取《{pdf_path.name}》：{exc}") from exc

    if reader.is_encrypted:
        try:
            unlocked = bool(reader.decrypt(password or ""))
        except Exception:  # noqa: BLE001
            unlocked = False
        if not unlocked:
            hint = "密码错误" if password else "该文件需要打开密码"
            raise PdfEncryptedError(f"《{pdf_path.name}》已加密：{hint}。")

    try:
        page_count = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise PdfOperationError(f"《{pdf_path.name}》页面结构损坏：{exc}") from exc

    if page_count == 0:
        raise PdfOperationError(f"《{pdf_path.name}》中没有任何页面。")

    return reader


def page_count(path: str | Path, password: str | None = None) -> int:
    """快速获取页数。"""
    return len(open_reader(path, password).pages)


def default_output_dir(src: str | Path, suffix: str) -> Path:
    """在源文件旁生成默认输出目录，如 ``文档_split``。"""
    source = Path(src)
    return source.with_name(f"{source.stem}{suffix}")


def default_output_path(
    src: str | Path, suffix: str, extension: str | None = None
) -> Path:
    """在源文件旁生成默认输出**文件**路径，保留原扩展名。

    ``a.pdf`` + ``"_编辑"`` → ``a_编辑.pdf``
    ``a.pdf`` + ``"_文字"`` + ``".txt"`` → ``a_文字.txt``
    """
    source = Path(src)
    ext = source.suffix if extension is None else extension
    return source.with_name(f"{source.stem}{suffix}{ext}")


def unique_path(path: str | Path) -> Path:
    """若目标已存在，则追加 ``(1)`` ``(2)`` 直到不冲突。"""
    target = Path(path)
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在并返回它。"""
    directory = Path(path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfOperationError(f"无法创建目录 {directory}：{exc}") from exc
    return directory
