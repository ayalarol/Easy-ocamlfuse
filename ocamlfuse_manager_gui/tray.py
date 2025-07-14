# -*- coding: utf-8 -*-
import pystray
from PIL import Image
from tkinter import messagebox
from .utils import centrar_ventana
from .i18n import i18n_instance
_ = i18n_instance.gettext

class TrayIconManager:
    def __init__(self, root, unmount_cb, quit_cb, is_gnome=False, minimized=False):
        self.root = root
        self.unmount_cb = unmount_cb
        self.quit_app = quit_cb
        self.is_gnome = is_gnome
        self.minimized = minimized
        self.tray_icon = None
        self.skip_tray_creation = False # New flag

    def create_tray_icon(self, icon_path):
        if self.skip_tray_creation:
            return

        try:
            image = Image.open(icon_path).resize((64, 64), Image.LANCZOS)
            menu = pystray.Menu(
                pystray.MenuItem(_("Mostrar"), self.show_window),
                pystray.MenuItem(_("Desmontar Todo"), self.unmount_all_tray),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(_("Salir"), self.quit_application)
            )
            self.tray_icon = pystray.Icon("gdrive_manager", image, _( "Google Drive Manager"), menu)
            self.tray_icon.run()
        except Exception as e:
            print(_(f"No se pudo crear bandeja: {e}"))

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        centrar_ventana(self.root)
        self.root.lift()
        self.root.focus_force()

    def unmount_all_tray(self, icon=None, item=None):
        self.unmount_cb()

    def quit_application(self, icon=None, item=None):
        if icon:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        if not messagebox.askyesno(_("Desea salir"), _( "¿Está seguro de que desea salir?")):
            if icon:
                self.root.withdraw()
            return
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except:
                pass
        self.quit_app()

    def on_closing(self):
        if self.tray_icon:
            self.root.withdraw()
        else:
            if messagebox.askyesno(_("Salir"), _( "¿Está seguro de que desea salir?")):
                self.quit_app()
