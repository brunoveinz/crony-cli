"""
Internationalization (i18n) module for Crony.
Provides multilingual support with environment-based language selection.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Supported languages
SUPPORTED_LANGUAGES = ["en", "es"]
DEFAULT_LANGUAGE = "en"

# Path to translations directory
TRANSLATIONS_DIR = Path(__file__).parent / "translations"


class Translator:
    """Manages translations for the application."""

    def __init__(self, language: Optional[str] = None):
        """
        Initialize the translator with a specific language.

        Args:
            language: Language code (e.g., 'en', 'es'). If None, uses CRONY_LANG env var or default.
        """
        # Determine language
        if language is None:
            language = os.getenv("CRONY_LANG")
            if not language:
                try:
                    import yaml
                    from pathlib import Path
                    config_path = Path.home() / ".crony" / "config.yml"
                    if config_path.exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            cfg = yaml.safe_load(f) or {}
                            language = cfg.get("language")
                except Exception:
                    pass

            if not language:
                language = DEFAULT_LANGUAGE

        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        self.language = language
        self._translations: Dict[str, Any] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load translations from JSON file for the current language."""
        lang_file = TRANSLATIONS_DIR / f"{self.language}.json"

        if not lang_file.exists():
            raise FileNotFoundError(
                f"Translation file not found: {lang_file}. "
                f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
            )

        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                self._translations = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {lang_file}: {e}")

    def _get_nested(self, key: str) -> Any:
        """Get value from nested dictionary using dot notation (e.g., 'errors.daemon_running')."""
        keys = key.split(".")
        value = self._translations

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return None
            else:
                return None

        return value

    def translate(self, key: str, **kwargs) -> str:
        """
        Get translation for a key with optional string interpolation.

        Args:
            key: Translation key using dot notation (e.g., 'errors.daemon_running')
            **kwargs: Optional values for string interpolation using {var_name} syntax

        Returns:
            Translated string, with fallback to key name if not found
        """
        value = self._get_nested(key)

        if value is None:
            # Fallback: try English if current language fails
            if self.language != "en":
                fallback_translator = Translator(language="en")
                fallback_value = fallback_translator._get_nested(key)
                if fallback_value is not None:
                    return str(fallback_value).format(**kwargs) if kwargs else str(fallback_value)

            # If all else fails, return the key itself
            return key

        # If value is not a string (e.g., nested dict), return key
        if not isinstance(value, str):
            return key

        # Perform string interpolation if kwargs provided
        if kwargs:
            try:
                return value.format(**kwargs)
            except (KeyError, ValueError):
                return value

        return value

    def __call__(self, key: str, **kwargs) -> str:
        """Allow using translator as a callable: t(key, var=value)"""
        return self.translate(key, **kwargs)


# Global translator instance
_translator: Optional[Translator] = None


def get_translator(language: Optional[str] = None) -> Translator:
    """
    Get a translator instance with optional language override.

    Args:
        language: Language code. If None, uses cached instance or creates new one.

    Returns:
        Translator instance
    """
    global _translator

    if language is not None:
        # Create a new instance if language is specified
        return Translator(language=language)

    if _translator is None:
        _translator = Translator()

    return _translator


def set_language(language: str) -> None:
    """Set the global language for translations."""
    global _translator
    _translator = Translator(language=language)


def get_supported_languages() -> list:
    """Get list of supported languages."""
    return SUPPORTED_LANGUAGES


def get_current_language() -> str:
    """Get the current language."""
    return get_translator().language

