import gettext
import os
from pathlib import Path

class I18N:
    def __init__(self, lang="es"):
        self.lang = lang
        self.LOCALE_DIR = Path(__file__).parent / "locale"
        self.translation = self._setup_translation()

    def _setup_translation(self):
        try:
            return gettext.translation(
                "ocamlfuse_manager",
                self.LOCALE_DIR,
                languages=[self.lang],
                fallback=True,
            )
        except FileNotFoundError:
            return gettext.NullTranslations()

    def gettext(self, text):
        return self.translation.gettext(text)

# Instancia global (idioma predeterminado: español)
i18n_instance = I18N("es")
_ = i18n_instance.gettext
