import os
import json
from .i18n import _

class ConfigManager:
    def __init__(self, config_file="~/.gdrive_manager_config.json"):
        self.config_file = os.path.expanduser(config_file)

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return {
                        "accounts": config.get("accounts", {}),
                        "mounted_accounts": config.get("mounted_accounts", {}),
                        "deleted_accounts": config.get("deleted_accounts", {}),
                        "autostart_enabled": config.get("autostart_enabled", False),
                        "ask_before_delete": config.get("ask_before_delete", True),
                        "language": config.get("language", "es")
                    }
            return self._get_default_config()
        except Exception as e:
            print(_(f"Error al cargar configuración: {e}"))
            return self._get_default_config()

    def save_config(self, data):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(_(f"Error al guardar configuración: {e}"))

    def _get_default_config(self):
        return {
            "accounts": {},
            "mounted_accounts": {},
            "deleted_accounts": {},
            "autostart_enabled": False,
            "ask_before_delete": True,
            "language": "es"
        }
