# -*- coding: utf-8 -*-
import gettext
import os
from pathlib import Path

class I18N:
    def __init__(self, lang="es"):
        self.lang = lang
        self.translation = self._setup_translation()

    def _setup_translation(self):
        # Intentar cargar desde la ruta relativa (para desarrollo/ejecución local)
        local_locale_dir = Path(__file__).parent / "locale"
        try:
            return gettext.translation(
                "ocamlfuse_manager",
                local_locale_dir,
                languages=[self.lang],
                fallback=True,
            )
        except FileNotFoundError:
            # Si no se encuentra localmente, intentar la ruta a nivel de sistema (para la versión instalada)
            gettext.bindtextdomain("ocamlfuse_manager", "/usr/share/locale")
            gettext.textdomain("ocamlfuse_manager")
            return gettext.translation(
                "ocamlfuse_manager",
                languages=[self.lang],
                fallback=True,
            )

    def gettext(self, text):
        return self.translation.gettext(text)

# Instancia global (idioma predeterminado: español)
i18n_instance = I18N("es")
_ = i18n_instance.gettext