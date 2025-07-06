import os

SCRIPT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
ICONS_DIR  = os.path.join(ASSETS_DIR, "icons")

LOGO_FILE  = os.path.join(ICONS_DIR, "gdrive_logo.png")

# resto de constantes…
CONFIG_FILE = "~/.gdrive_manager_config.json"
GDFUSE_DIR   = "~/.gdfuse"
OAUTH_PORT   = 8080
