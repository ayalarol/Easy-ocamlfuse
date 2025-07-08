import os

APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/ayalarol/Easy-ocamlfuse"
LICENSE_URL = f"{GITHUB_URL}/blob/main/LICENSE"

SCRIPT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
ICONS_DIR  = os.path.join(ASSETS_DIR, "icons")

LOGO_FILE  = os.path.join(ICONS_DIR, "gdrive_logo.png")

# resto de constantes…
CONFIG_FILE = os.path.expanduser("~/.gdrivemanagerconfig/config.json")
GDFUSE_DIR   = "~/.gdfuse"
OAUTH_PORT   = 8080