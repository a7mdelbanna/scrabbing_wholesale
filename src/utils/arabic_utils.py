"""Utilities for handling Arabic text in product data."""
import unicodedata
import re
from typing import Optional, Tuple


class ArabicTextProcessor:
    """Utilities for handling Arabic text in product data."""

    # Arabic diacritics (tashkeel)
    TASHKEEL = re.compile(r"[\u0617-\u061A\u064B-\u0652]")

    # Arabic-Indic digits to Western digits
    ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

    # Common weight/unit patterns in Arabic
    WEIGHT_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?)\s*(جرام|جم|كيلو|كجم|غرام|غم|لتر|مل|ملي|قطعة|حبة|علبة|كرتونة)",
        re.UNICODE,
    )

    # Unit translations
    UNIT_TRANSLATIONS = {
        "جرام": "gram",
        "جم": "gram",
        "غرام": "gram",
        "غم": "gram",
        "كيلو": "kg",
        "كجم": "kg",
        "لتر": "liter",
        "مل": "ml",
        "ملي": "ml",
        "قطعة": "piece",
        "حبة": "piece",
        "علبة": "box",
        "كرتونة": "carton",
    }

    @classmethod
    def normalize(cls, text: Optional[str]) -> Optional[str]:
        """Normalize Arabic text for consistent storage and comparison.

        Args:
            text: Arabic text to normalize.

        Returns:
            Normalized text or None if input is None.
        """
        if not text:
            return text

        # Remove diacritics
        text = cls.TASHKEEL.sub("", text)

        # Normalize Unicode
        text = unicodedata.normalize("NFKC", text)

        # Convert Arabic-Indic digits to Western
        text = text.translate(cls.ARABIC_DIGITS)

        # Normalize common letter variations
        replacements = {
            "ى": "ي",  # Alef Maksura to Ya
            "ة": "ه",  # Ta Marbuta to Ha
            "أ": "ا",  # Alef with Hamza above
            "إ": "ا",  # Alef with Hamza below
            "آ": "ا",  # Alef with Madda
            "ٱ": "ا",  # Alef Wasla
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # Trim and normalize whitespace
        text = " ".join(text.split())

        return text

    @classmethod
    def extract_weight_from_name(cls, name: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Extract weight/unit information from product name.

        Args:
            name: Product name possibly containing weight info.

        Returns:
            Tuple of (clean_name, weight_value, unit_type)
        """
        match = cls.WEIGHT_PATTERN.search(name)
        if match:
            weight_str = match.group(0)
            weight_value = match.group(1)
            unit_ar = match.group(2)
            unit_en = cls.UNIT_TRANSLATIONS.get(unit_ar, "piece")

            clean_name = name.replace(weight_str, "").strip()
            # Clean up extra separators
            clean_name = re.sub(r"\s*[-/]\s*$", "", clean_name)
            clean_name = re.sub(r"^\s*[-/]\s*", "", clean_name)
            clean_name = " ".join(clean_name.split())

            return clean_name, weight_value, unit_en

        return name, None, None

    @classmethod
    def is_arabic(cls, text: str) -> bool:
        """Check if text contains Arabic characters.

        Args:
            text: Text to check.

        Returns:
            True if text contains Arabic characters.
        """
        if not text:
            return False
        return bool(re.search(r"[\u0600-\u06FF]", text))

    @classmethod
    def extract_numbers(cls, text: str) -> list:
        """Extract all numbers from text (including Arabic-Indic digits).

        Args:
            text: Text to extract numbers from.

        Returns:
            List of extracted numbers as strings.
        """
        if not text:
            return []

        # Convert Arabic-Indic digits first
        text = text.translate(cls.ARABIC_DIGITS)

        # Extract numbers
        return re.findall(r"\d+(?:\.\d+)?", text)

    @classmethod
    def clean_price_text(cls, price_text: str) -> Optional[float]:
        """Clean price text and convert to float.

        Args:
            price_text: Price text possibly containing Arabic numerals and currency.

        Returns:
            Price as float or None if parsing fails.
        """
        if not price_text:
            return None

        # Convert Arabic-Indic digits
        text = price_text.translate(cls.ARABIC_DIGITS)

        # Remove currency symbols and text
        text = re.sub(r"[جنيهEGPLE\s]", "", text, flags=re.IGNORECASE)

        # Find the number
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None

        return None
