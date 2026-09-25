# Release Guide

## 本地发布前检查

```powershell
pytest
.\build.ps1
.\dist\PDFer.exe --self-test
Get-FileHash .\dist\PDFer.exe -Algorithm SHA256
```

确认：

- 全量测试通过；
- `PDFer.exe --self-test` 返回成功；
- GUI 可正常启动；
- 合并、拆分、页面预览、PDF/图片互转、优化、加密和解密均可执行；
- `README.md` 与 `CHANGELOG.md` 中版本号正确。

## GitHub Release

推荐使用标签触发自动发布：

```powershell
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` 会在 Windows Runner 上：

1. 安装 Python 和依赖；
2. 运行 pytest；
3. 构建单文件 `PDFer.exe`；
4. 执行内置 self-test；
5. 生成 SHA-256；
6. 将 EXE 和校验文件附加到 GitHub Release。

## 目录版

如需调试 Qt DLL、排查 PyInstaller 模块收集或获得更快冷启动：

```powershell
.\build.ps1 -OneDir
```

目录版不是普通用户的首选下载形式。
