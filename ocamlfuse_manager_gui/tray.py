# -*- coding: utf-8 -*-
import threading
import sys
import os
import subprocess
from PIL import Image
from .i18n import i18n_instance
_ = i18n_instance.gettext

# Intentar importar pystray de forma segura, ya que puede fallar por librerías de sistema ausentes
try:
    import pystray
    PYSTRAY_AVAILABLE = True
except (ImportError, Exception) as e:
    print(f"Pystray no disponible o error de librerías: {e}")
    PYSTRAY_AVAILABLE = False

class TrayIconManager:
    def __init__(self, root, unmount_cb, quit_cb):
        self.root = root
        self.unmount_cb = unmount_cb
        self.quit_app = quit_cb
        self.tray_icon = None
        self.skip_tray_creation = not PYSTRAY_AVAILABLE
        self.mounted_accounts = {} # Almacenar {etiqueta: punto_montaje}

    def create_tray_icon(self, icon_path):
        if self.skip_tray_creation or not PYSTRAY_AVAILABLE:
            print(_("Saltando creación de bandeja del sistema (no disponible o error de librerías)."))
            return

        def run_tray():
            try:
                # Truco: Sobrescribir temporalmente signal.signal para evitar el error en hilos secundarios
                import signal
                original_signal = signal.signal
                signal.signal = lambda s, h: original_signal(s, h) if threading.current_thread() is threading.main_thread() else None
                
                image = Image.open(icon_path).resize((64, 64), Image.Resampling.LANCZOS)
                self.tray_icon = pystray.Icon(
                    "easy-ocamlfuse", 
                    image, 
                    _("Easy Ocamlfuse"), 
                    menu=self._create_menu()
                )
                self.tray_icon.run()
            except Exception as e:
                print(_("Error crítico al ejecutar la bandeja: {}").format(e))
                self.skip_tray_creation = True
                self.tray_icon = None

        # Ejecutar en un hilo separado para no bloquear la GUI
        threading.Thread(target=run_tray, daemon=True).start()

    def _create_menu(self):
        """Genera el menú dinámicamente basado en las cuentas montadas."""
        if not PYSTRAY_AVAILABLE:
            return None
            
        menu_items = []

        # Añadir sección de "Abrir carpeta" al inicio si hay cuentas montadas
        if self.mounted_accounts:
            for label, path in self.mounted_accounts.items():
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
        if self.tray_icon and PYSTRAY_AVAILABLE:
            try:
                self.tray_icon.menu = self._create_menu()
            except Exception as e:
                print(f"Error actualizando menú de bandeja: {e}")

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
        if self.tray_icon and PYSTRAY_AVAILABLE:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
