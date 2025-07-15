# -*- coding: utf-8 -*-
import pystray
from PIL import Image
import threading
from .i18n import i18n_instance
_ = i18n_instance.gettext

class TrayIconManager:
    def __init__(self, root, unmount_cb, quit_cb):
        self.root = root
        self.unmount_cb = unmount_cb
        self.quit_app = quit_cb
        self.tray_icon = None
        self.skip_tray_creation = False

    def create_tray_icon(self, icon_path):
        if self.skip_tray_creation:
            return

        try:
            image = Image.open(icon_path).resize((64, 64), Image.Resampling.LANCZOS)
            menu = pystray.Menu(
                pystray.MenuItem(_("Mostrar"), self.show_window, default=True),
                pystray.MenuItem(_("Desmontar Todo"), self.unmount_cb),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(_("Salir"), self.quit_app)
            )
            self.tray_icon = pystray.Icon("easy-ocamlfuse", image, _("Easy Ocamlfuse"), menu)
            
            # Ejecutar en un hilo separado para no bloquear
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

        except Exception as e:
            print(_(f"No se pudo crear la bandeja: {e}"))

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