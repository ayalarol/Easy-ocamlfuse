import os
import json
import shutil
from .i18n import _

class ConfigManager:
    def __init__(self, config_dir="~/.gdrivemanagerconfig", config_name="config.json", key_subdir=".secure_key"):
        self.config_dir = os.path.expanduser(config_dir)
        self.config_file = os.path.join(self.config_dir, config_name)
        self.key_dir = os.path.join(self.config_dir, key_subdir)

        # crear carpeta de config
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

        #logica por si haya duplicados o exitencias de la carpeta
        config_json_dir = os.path.join(self.config_dir, config_name)
        if os.path.isdir(config_json_dir):
            inner_config = os.path.join(config_json_dir, config_name)
            if os.path.isfile(inner_config):
                shutil.move(inner_config, self.config_file)
            inner_key = os.path.join(config_json_dir, key_subdir)
            if os.path.isdir(inner_key):
                for fname in os.listdir(inner_key):
                    src = os.path.join(inner_key, fname)
                    dst = os.path.join(self.key_dir, fname)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                shutil.rmtree(inner_key)
            shutil.rmtree(config_json_dir)

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
