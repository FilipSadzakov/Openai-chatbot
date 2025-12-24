import unicodedata

def normalize(text: str) -> str:
    text = (text or "").lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
