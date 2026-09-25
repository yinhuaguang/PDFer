"""额外实用功能：图片转 PDF、优化压缩、设置/移除打开密码。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pikepdf
from PIL import Image, UnidentifiedImageError

from .errors import PdfOperationError
from .progress import NULL_CONTEXT, TaskContext

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class OptimizeResult:
    """PDF 优化结果。"""

    output: Path
    before_bytes: int
    after_bytes: int

    @property
    def saved_bytes(self) -> int:
        return self.before_bytes - self.after_bytes

    @property
    def ratio(self) -> float:
        if self.before_bytes <= 0:
            return 0.0
        return self.after_bytes / self.before_bytes


def _prepare_output(output: str | Path) -> Path:
    target = Path(output)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfOperationError(f"无法创建输出目录：{target.parent}：{exc}") from exc
    return target


def _check_different(source: str | Path, output: str | Path) -> None:
    try:
        if Path(source).resolve() == Path(output).resolve():
            raise PdfOperationError("输出路径不能与源文件相同，请使用新的文件名。")
    except OSError:
        return


def _open_pikepdf(source: str | Path, password: str | None = None) -> pikepdf.Pdf:
    path = Path(source)
    if not path.is_file():
        raise PdfOperationError(f"文件不存在：{path}")
    try:
        return pikepdf.Pdf.open(str(path), password=password or "")
    except pikepdf.PasswordError as exc:
        hint = "密码错误" if password else "该文件需要打开密码"
        raise PdfOperationError(f"《{path.name}》已加密：{hint}。") from exc
    except pikepdf.PdfError as exc:
        raise PdfOperationError(f"无法读取《{path.name}》：{exc}") from exc
    except OSError as exc:
        raise PdfOperationError(f"无法打开《{path.name}》：{exc}") from exc


def images_to_pdf(
    images: Sequence[str | Path],
    output: str | Path,
    *,
    dpi: int = 150,
    jpeg_quality: int = 92,
    ctx: TaskContext = NULL_CONTEXT,
) -> Path:
    """把多张图片按给定顺序合成为一个 PDF。"""

    if not images:
        raise PdfOperationError("请至少选择一张图片。")

    source_paths = [Path(item) for item in images]
    invalid = [p.name for p in source_paths if p.suffix.lower() not in _IMAGE_SUFFIXES]
    if invalid:
        raise PdfOperationError(f"存在不支持的图片格式：{', '.join(invalid[:5])}")

    target = _prepare_output(output)
    prepared: list[Image.Image] = []
    total = len(source_paths)

    try:
        for index, source in enumerate(source_paths, 1):
            ctx.check_cancel()
            if not source.is_file():
                raise PdfOperationError(f"图片不存在：{source}")
            try:
                with Image.open(source) as original:
                    # PDF 不支持透明通道；透明区域统一铺白底，避免变成黑色。
                    if original.mode in ("RGBA", "LA") or (
                        original.mode == "P" and "transparency" in original.info
                    ):
                        rgba = original.convert("RGBA")
                        white = Image.new("RGB", rgba.size, "white")
                        white.paste(rgba, mask=rgba.getchannel("A"))
                        converted = white
                    else:
                        converted = original.convert("RGB")
                    prepared.append(converted.copy())
            except (OSError, UnidentifiedImageError) as exc:
                raise PdfOperationError(f"无法读取图片《{source.name}》：{exc}") from exc
            ctx.report(index, total + 1, f"正在读取图片 {index}/{total}")

        ctx.check_cancel()
        first, rest = prepared[0], prepared[1:]
        try:
            first.save(
                target,
                "PDF",
                save_all=True,
                append_images=rest,
                resolution=max(36, min(1200, dpi)),
                quality=max(1, min(100, jpeg_quality)),
            )
        except OSError as exc:
            raise PdfOperationError(f"无法生成 PDF：{exc}") from exc

        ctx.report(total + 1, total + 1, "PDF 已生成")
        return target
    finally:
        for image in prepared:
            image.close()


def optimize_pdf(
    source: str | Path,
    output: str | Path,
    *,
    password: str | None = None,
    ctx: TaskContext = NULL_CONTEXT,
) -> OptimizeResult:
    """重写 PDF 结构、压缩流并生成对象流。

    这是无损的结构优化，不会降低图片分辨率；对已经高度压缩的 PDF，
    输出可能与原文件接近，极少数文件甚至会略大。
    """

    _check_different(source, output)
    target = _prepare_output(output)
    source_path = Path(source)
    ctx.report_stage("正在读取 PDF…", 1, 3)
    ctx.check_cancel()

    pdf = _open_pikepdf(source_path, password)
    try:
        encrypted = bool(pdf.is_encrypted)
        ctx.report_stage("正在清理未引用资源…", 2, 3)
        ctx.check_cancel()
        try:
            pdf.remove_unreferenced_resources()
        except Exception:
            # 某些结构特殊的 PDF 无法安全清理资源，跳过即可，后续压缩仍然有效。
            pass

        try:
            pdf.save(
                str(target),
                compress_streams=True,
                recompress_flate=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                encryption=True if encrypted else False,
            )
        except (pikepdf.PdfError, OSError) as exc:
            raise PdfOperationError(f"无法保存优化后的 PDF：{exc}") from exc
    finally:
        pdf.close()

    ctx.report_stage("优化完成", 3, 3)
    try:
        before = source_path.stat().st_size
        after = target.stat().st_size
    except OSError:
        before = after = 0
    return OptimizeResult(target, before, after)


def protect_pdf(
    source: str | Path,
    output: str | Path,
    *,
    user_password: str,
    owner_password: str | None = None,
    source_password: str | None = None,
    ctx: TaskContext = NULL_CONTEXT,
) -> Path:
    """为 PDF 设置 AES-256 打开密码。"""

    if not user_password:
        raise PdfOperationError("打开密码不能为空。")
    _check_different(source, output)
    target = _prepare_output(output)
    ctx.report_stage("正在读取 PDF…", 1, 2)
    ctx.check_cancel()

    pdf = _open_pikepdf(source, source_password)
    try:
        encryption = pikepdf.Encryption(
            owner=owner_password or user_password,
            user=user_password,
            R=6,
            aes=True,
            metadata=True,
        )
        try:
            pdf.save(str(target), encryption=encryption)
        except (pikepdf.PdfError, OSError) as exc:
            raise PdfOperationError(f"无法保存加密 PDF：{exc}") from exc
    finally:
        pdf.close()

    ctx.report_stage("密码已设置", 2, 2)
    return target


def unprotect_pdf(
    source: str | Path,
    output: str | Path,
    *,
    password: str,
    ctx: TaskContext = NULL_CONTEXT,
) -> Path:
    """使用正确密码打开 PDF，并另存为不带打开密码的副本。"""

    if not password:
        raise PdfOperationError("请输入当前打开密码。")
    _check_different(source, output)
    target = _prepare_output(output)
    ctx.report_stage("正在验证密码…", 1, 2)
    ctx.check_cancel()

    pdf = _open_pikepdf(source, password)
    try:
        try:
            pdf.save(str(target), encryption=False)
        except (pikepdf.PdfError, OSError) as exc:
            raise PdfOperationError(f"无法保存解密后的 PDF：{exc}") from exc
    finally:
        pdf.close()

    ctx.report_stage("密码已移除", 2, 2)
    return target
