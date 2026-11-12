"""Версия AI Limits — единственное место, где она задаётся.

`python version.py <файл>` записывает описание версии для PyInstaller (--version-file),
чтобы версия была видна в свойствах exe. Это делает build_exe.cmd.
"""
import sys

__version__ = "1.4.2"


def pyinstaller_version_info():
    parts = ([int(p) for p in __version__.split(".") if p.isdigit()] + [0, 0, 0, 0])[:4]
    v = tuple(parts)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Biz2k'),
      StringStruct('FileDescription', 'AI Limits'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'AI Limits'),
      StringStruct('OriginalFilename', 'AI Limits.exe'),
      StringStruct('ProductName', 'AI Limits'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('LegalCopyright', '(c) 2026 Biz2k, MIT License')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(pyinstaller_version_info())
    else:
        print(__version__)
