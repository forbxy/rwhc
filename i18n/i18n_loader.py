import locale
from pathlib import Path

PO_DIR = Path(__file__).with_name("locales")

def detect_lang(default="en"):
    # return "en"
    loc = (locale.getdefaultlocale()[0] or "").lower()
    if loc.startswith("zh"):
        return "zh"
    if loc.startswith("en"):
        return "en"
    return default

def _po_unescape(text: str) -> str:
    return (
        text.replace(r"\\", "\\")
            .replace(r"\"", "\"")
            .replace(r"\n", "\n")
            .replace(r"\t", "\t")
    )

def _load_po(lang: str) -> dict:
    path = PO_DIR / f"messages_{lang}.po"
    if not path.exists():
        return {}
    entries = {}
    current_id = None
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("msgid "):
                current_id = _po_unescape(line[7:-1])  # strip msgid "..."
            elif line.startswith("msgstr ") and current_id is not None:
                entries[current_id] = _po_unescape(line[8:-1])
                current_id = None
    return entries

class Translator:
    def __init__(self, lang=None):
        self.lang = lang or detect_lang()
        self.messages = _load_po(self.lang)
        # fallback to English translations when available
        self.fallback = _load_po("en") if self.lang != "en" else {}

    def gettext(self, msgid):
        if msgid in self.messages:
            txt = self.messages.get(msgid)
            return txt if txt else msgid
        if msgid in self.fallback:
            txt = self.fallback.get(msgid)
            return txt if txt else msgid
        return msgid

# default instance and global _
_translator = Translator()
_ = _translator.gettext