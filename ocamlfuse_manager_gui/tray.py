# -*- coding: utf-8 -*-
import pystray
from PIL import Image
import threading
import sys
import os
import subprocess
from .i18n import i18n_instance
_ = i18n_instance.gettext

class TrayIconManager:
    def __init__(self, root, unmount_cb, quit_cb):
        self.root = root
        self.unmount_cb = unmount_cb
        self.quit_app = quit_cb
        self.tray_icon = None
        self.skip_tray_creation = False
        self.mounted_accounts = {} # Almacenar {etiqueta: punto_montaje}

    def create_tray_icon(self, icon_path):
        if self.skip_tray_creation:
            return

        try:
            image = Image.open(icon_path).resize((64, 64), Image.Resampling.LANCZOS)
            self.tray_icon = pystray.Icon("easy-ocamlfuse", image, _("Easy Ocamlfuse"), menu=self._create_menu())
            
            def run_tray():
                import signal
                original_signal = signal.signal
                signal.signal = lambda s, h: None
                try:
                    self.tray_icon.run()
                finally:
                    signal.signal = original_signal

            threading.Thread(target=run_tray, daemon=True).start()

        except Exception as e:
            print(_("No se pudo crear la bandeja: {}").format(e))

    def _create_menu(self):
        """Genera el menú dinámicamente basado en las cuentas montadas."""
        menu_items = []

        # Añadir sección de "Abrir carpeta" al inicio si hay cuentas montadas
        if self.mounted_accounts:
            for label, path in self.mounted_accounts.items():
                # Usamos una función fábrica para capturar el path actual en el closure
                menu_items.append(pystray.MenuItem(
                    _("Abrir: {label}").format(label=label),
                    self._make_open_folder_cb(path)
                ))
            menu_items.append(pystray.Menu.SEPARATOR)

        menu_items.append(pystray.MenuItem(_("Mostrar"), self.show_window, default=True))

        menu_items.extend([
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("Desmontar Todo"), self.unmount_cb),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("Salir"), self.quit_app)
        ])
        return pystray.Menu(*menu_items)

    def _make_open_folder_cb(self, path):
        """Crea un callback que abre la carpeta especificada."""
        return lambda: self.root.after(0, lambda: self._open_folder(path))

    def _open_folder(self, path):
        try:
            if os.path.exists(path):
                if sys.platform == 'win32':
                    os.startfile(path)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
        except Exception as e:
            print(f"Error al abrir carpeta desde tray: {e}")

    def update_menu(self, mounted_accounts):
        """Actualiza la lista de cuentas montadas y refresca el menú."""
        self.mounted_accounts = mounted_accounts
        if self.tray_icon:
            self.tray_icon.menu = self._create_menu()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._do_show_window)

    def _do_show_window(self):
        try:
            if self.root.state() == 'iconic':
                self.root.deiconify()
            else:
                self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as e:
            print(f"Error al mostrar la ventana: {e}")

    def stop_tray(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None