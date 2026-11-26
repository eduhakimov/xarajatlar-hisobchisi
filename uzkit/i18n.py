"""Uch tilli (uz / ru / en) tarjima tizimi.

Foydalanish:
    from uzkit.i18n import tr, register
    register({
        "open": {"uz": "Ochish", "ru": "Открыть", "en": "Open"},
    })
    tr("open")              -> joriy tildagi matn
    tr("files_n", n=5)      -> "{n} ta fayl" kabi formatlash

Til almashtirilganda dastur o'zini qayta ishga tushiradi (window.py ga qarang).
"""
from typing import Dict

LANGUAGES = {"uz": "O'zbekcha", "ru": "Русский", "en": "English"}
DEFAULT_LANG = "uz"

_current = DEFAULT_LANG
_strings: Dict[str, Dict[str, str]] = {}

# Barcha dasturlar uchun umumiy so'zlar
_COMMON = {
    "file": {"uz": "Fayl", "ru": "Файл", "en": "File"},
    "settings": {"uz": "Sozlamalar", "ru": "Настройки", "en": "Settings"},
    "help": {"uz": "Yordam", "ru": "Справка", "en": "Help"},
    "about": {"uz": "Dastur haqida", "ru": "О программе", "en": "About"},
    "manual": {"uz": "Qo'llanma", "ru": "Руководство", "en": "User guide"},
    "exit": {"uz": "Chiqish", "ru": "Выход", "en": "Exit"},
    "language": {"uz": "Til", "ru": "Язык", "en": "Language"},
    "theme": {"uz": "Mavzu", "ru": "Тема", "en": "Theme"},
    "theme_light": {"uz": "Yorug'", "ru": "Светлая", "en": "Light"},
    "theme_dark": {"uz": "Qorong'i", "ru": "Тёмная", "en": "Dark"},
    "theme_system": {"uz": "Tizim bo'yicha", "ru": "Как в системе", "en": "System"},
    "ok": {"uz": "OK", "ru": "OK", "en": "OK"},
    "cancel": {"uz": "Bekor qilish", "ru": "Отмена", "en": "Cancel"},
    "close": {"uz": "Yopish", "ru": "Закрыть", "en": "Close"},
    "save": {"uz": "Saqlash", "ru": "Сохранить", "en": "Save"},
    "open": {"uz": "Ochish", "ru": "Открыть", "en": "Open"},
    "delete": {"uz": "O'chirish", "ru": "Удалить", "en": "Delete"},
    "add": {"uz": "Qo'shish", "ru": "Добавить", "en": "Add"},
    "edit": {"uz": "Tahrirlash", "ru": "Изменить", "en": "Edit"},
    "search": {"uz": "Qidirish", "ru": "Поиск", "en": "Search"},
    "browse": {"uz": "Tanlash...", "ru": "Обзор...", "en": "Browse..."},
    "start": {"uz": "Boshlash", "ru": "Начать", "en": "Start"},
    "stop": {"uz": "To'xtatish", "ru": "Остановить", "en": "Stop"},
    "done": {"uz": "Tayyor", "ru": "Готово", "en": "Done"},
    "error": {"uz": "Xatolik", "ru": "Ошибка", "en": "Error"},
    "warning": {"uz": "Ogohlantirish", "ru": "Предупреждение", "en": "Warning"},
    "ready": {"uz": "Tayyor", "ru": "Готово", "en": "Ready"},
    "working": {"uz": "Bajarilmoqda...", "ru": "Выполняется...", "en": "Working..."},
    "version": {"uz": "Versiya", "ru": "Версия", "en": "Version"},
    "author": {"uz": "Muallif", "ru": "Автор", "en": "Author"},
    "rights": {
        "uz": "Barcha huquqlar himoyalangan.",
        "ru": "Все права защищены.",
        "en": "All rights reserved.",
    },
    "restart_title": {"uz": "Qayta ishga tushirish", "ru": "Перезапуск", "en": "Restart"},
    "restart_lang": {
        "uz": "Tilni o'zgartirish uchun dastur qayta ishga tushiriladi. Davom etasizmi?",
        "ru": "Для смены языка программа будет перезапущена. Продолжить?",
        "en": "The app will restart to change the language. Continue?",
    },
    "unexpected_error": {
        "uz": "Kutilmagan xatolik yuz berdi. Tafsilotlar jurnal fayliga yozildi:",
        "ru": "Произошла непредвиденная ошибка. Подробности записаны в журнал:",
        "en": "An unexpected error occurred. Details were written to the log:",
    },
    "drop_here": {
        "uz": "Fayllarni shu yerga tashlang yoki bosib tanlang",
        "ru": "Перетащите файлы сюда или нажмите для выбора",
        "en": "Drop files here or click to choose",
    },
    "select_folder": {"uz": "Papkani tanlang", "ru": "Выберите папку", "en": "Choose a folder"},
    "select_file": {"uz": "Faylni tanlang", "ru": "Выберите файл", "en": "Choose a file"},
    "open_folder": {"uz": "Papkani ochish", "ru": "Открыть папку", "en": "Open folder"},
    "confirm": {"uz": "Tasdiqlash", "ru": "Подтверждение", "en": "Confirm"},
    "yes": {"uz": "Ha", "ru": "Да", "en": "Yes"},
    "no": {"uz": "Yo'q", "ru": "Нет", "en": "No"},
    "export": {"uz": "Eksport", "ru": "Экспорт", "en": "Export"},
    "import": {"uz": "Import", "ru": "Импорт", "en": "Import"},
    "print": {"uz": "Chop etish", "ru": "Печать", "en": "Print"},
    "clear": {"uz": "Tozalash", "ru": "Очистить", "en": "Clear"},
    "name": {"uz": "Nomi", "ru": "Название", "en": "Name"},
    "date": {"uz": "Sana", "ru": "Дата", "en": "Date"},
    "status": {"uz": "Holat", "ru": "Статус", "en": "Status"},
    "total": {"uz": "Jami", "ru": "Итого", "en": "Total"},
    "copy": {"uz": "Nusxalash", "ru": "Копировать", "en": "Copy"},
    "copied": {"uz": "Nusxalandi", "ru": "Скопировано", "en": "Copied"},
    "admin_required": {
        "uz": "Bu amal uchun administrator huquqi kerak. Dasturni administrator sifatida qayta ishga tushirasizmi?",
        "ru": "Для этого действия нужны права администратора. Перезапустить программу от имени администратора?",
        "en": "This action requires administrator rights. Restart the app as administrator?",
    },
}


def register(strings: Dict[str, Dict[str, str]]) -> None:
    """Dasturga xos tarjimalarni qo'shish."""
    _strings.update(strings)


def set_language(lang: str) -> None:
    global _current
    _current = lang if lang in LANGUAGES else DEFAULT_LANG


def language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    """Kalit bo'yicha joriy tildagi matn. Topilmasa — o'zbekcha yoki kalitning o'zi."""
    entry = _strings.get(key) or _COMMON.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(_current) or entry.get("uz") or entry.get("en") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def missing_keys() -> Dict[str, list]:
    """Testlar uchun: qaysi kalitlarda qaysi til yetishmaydi."""
    out = {}
    for k, v in {**_COMMON, **_strings}.items():
        miss = [l for l in LANGUAGES if not v.get(l)]
        if miss:
            out[k] = miss
    return out
