"""shared ocr-side name normalization, no web deps so the runtime stays lean"""

import re
import unicodedata


def normalize(text):
    """fold case, accents, and punctuation to a plain matchable string"""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return " ".join(s.split())
