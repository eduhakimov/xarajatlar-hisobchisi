"""Fayl yo'llari: PyInstaller (onefile) ichida ham, oddiy ishga tushirishda ham to'g'ri ishlaydi."""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """Dastur .exe ko'rinishida ishlayaptimi."""
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """Dastur fayllari joylashgan papka (exe ichida _MEIPASS, aks holda loyiha ildizi)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # uzkit/ papkasining ota-papkasi = loyiha ildizi
    return Path(__file__).resolve().parent.parent


def exe_dir() -> Path:
    """.exe fayl turgan papka (portativ ma'lumotlar uchun)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return base_dir()


def resource(*parts: str) -> Path:
    """assets/ yoki boshqa ichki resursga yo'l."""
    return base_dir().joinpath(*parts)


def data_dir(app_slug: str) -> Path:
    """Foydalanuvchi ma'lumotlari papkasi: %APPDATA%/BahtiyorSoft/<slug>."""
    root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    p = Path(root) / "BahtiyorSoft" / app_slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def documents_dir() -> Path:
    """Foydalanuvchining 'Hujjatlar' papkasi."""
    try:
        from PySide6.QtCore import QStandardPaths
        loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if loc:
            return Path(loc)
    except Exception:
        pass
    return Path.home() / "Documents"
