import os
import sys
import subprocess
import notify2
import webbrowser
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import shutil

from .constants import LOGO_FILE, GDFUSE_DIR, CONFIG_FILE, APP_VERSION
from .utils import ToolTip,centrar_ventana,verificar_ocamlfuse, detectar_distro_id, obtener_comando_instalacion_ocamlfuse, instalar_ocamlfuse_async, check_for_updates
from .config    import ConfigManager
from .mount     import MountManager
from .account   import AccountManager
from .tray      import TrayIconManager
from .i18n      import _, i18n_instance
ICON_SIZE = (24, 24)

class GoogleDriveManager:
    def __init__(self):
        minimized = "--minimized" in sys.argv
        self.root = tk.Tk(className="EasyOcamlfuse")
        self.root.withdraw()
        # --- Configuración de idioma antes de widgets ---
        self.config_mgr = ConfigManager(CONFIG_FILE)
        config_data = self.config_mgr.load_config()
        lang = config_data.get("language", "es")
        i18n_instance.lang = lang
        i18n_instance.translation = i18n_instance._setup_translation()
        
        global _
        _ = i18n_instance.gettext

        self.root.title(_("Easy Ocamlfuse"))
        self.root.geometry("930x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.minsize(930, 600) # Establece el tamaño mínimo de la ventana 
        centrar_ventana(self.root)
      
        if not minimized:
            self.root.deiconify()
        #carga de icono 
        try:
            icon_image = tk.PhotoImage(file=LOGO_FILE)
            self.root.iconphoto(True, icon_image)
            self.window_icon = icon_image
        except Exception as e:
            print(_("No se pudo cargar el icono de ventana: {}").format(e))

        # Config Manager
        self.config_mgr = ConfigManager(CONFIG_FILE)

        # Cargar configuración
        config_data = self.config_mgr.load_config()
        self.accounts = config_data.get("accounts", {})
        self.mounted_accounts = config_data.get("mounted_accounts", {})
        self.deleted_accounts = config_data.get("deleted_accounts", {})
        self.autostart_enabled = config_data.get("autostart_enabled", False)
        self.ask_before_delete = config_data.get("ask_before_delete", True)

        # Inicializar autostart_var ANTES de cualquier save_config
        self.autostart_var = tk.BooleanVar()
        xdg_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        desktop_session = os.environ.get("DESKTOP_SESSION", "").lower()
        is_bodhi = "enlightenment" in xdg_desktop or "enlightenment" in desktop_session or "bodhi" in desktop_session
        if is_bodhi:
            profile_path = os.path.expanduser("~/.profile")
            autostart_line = (
                f'# Autoinicio EasyOcamlfuse\n'
                f'if ! pgrep -f "gdrive_manager.py" > /dev/null; then\n'
                f'    nohup python3 "{os.path.abspath(__file__)}" --minimized >/dev/null 2>&1 &\n'
                f'fi'
            )
            try:
                with open(profile_path, "r") as f:
                    self.autostart_var.set(autostart_line.strip() in f.read())
            except FileNotFoundError:
                self.autostart_var.set(False)
        else:
            self.autostart_var.set(self.autostart_enabled)

        # Managers
        self.mount_mgr = MountManager(self.mounted_accounts)
        self.mount_mgr.start_mount_monitor(
            interval=5,
            on_unmount_callback=self.on_external_unmount
        )
        self.account_mgr = AccountManager(
            self,            self.accounts,
            self.deleted_accounts,
            self._save_state,
            self.refresh_accounts, 
            self.ask_before_delete
        )
        self.tray_mgr = TrayIconManager(
            self.root,
            unmount_cb=self.unmount_all,
            quit_cb=self.quit_application
        )

        # UI
        self.create_widgets()
        self.create_menu()
        self.check_installation()
        self.closing = False
        self._update_main_tab_button_states()
        self._update_accounts_tab_button_states()
        self.root.update_idletasks()  # Fuerza el render de la UI
        # Cargar cuentas y montajes en segundo plano
        threading.Thread(target=self._cargar_datos_pesados, daemon=True).start()
        # bandeja
        threading.Thread(
            target=lambda: self.tray_mgr.create_tray_icon(LOGO_FILE),
            daemon=True
        ).start()
        
        self.check_for_updates_on_startup()

    def _cargar_datos_pesados(self):
        self.refresh_accounts()
        self.refresh_mounts()
        self.automount_accounts()
    def _load_icon(self, path, size=ICON_SIZE, bg_color=None):
        try:
            full_path = os.path.join(os.path.dirname(__file__), path)
            image = Image.open(full_path)
            
            # Forzar conversión a RGBA si no tiene canal alpha
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Redimensionar manteniendo transparencia
            image = image.resize(size, Image.Resampling.LANCZOS)
            
            # Si se especificó color de fondo, compuesto con fondo
            if bg_color:
                background = Image.new("RGBA", image.size, bg_color)
                image = Image.alpha_composite(background, image)
            
            # Crear PhotoImage manteniendo referencia
            photo_image = ImageTk.PhotoImage(image)
            
            # Tkinter requiere mantener referencia a la imagen
            if not hasattr(self, '_icon_references'):
                self._icon_references = []
            self._icon_references.append(photo_image)
            
            return photo_image
            
        except Exception as e:
            print(f"Error cargando icono {path}: {e}")
            return None
    def _tk_supports_alpha(self):
      
        return sys.platform != "linux" or "wayland" in os.environ.get("XDG_SESSION_TYPE", "").lower()

    def _save_state(self):
        config = {
            "accounts": self.accounts,
            "mounted_accounts": self.mounted_accounts,
            "deleted_accounts": self.deleted_accounts,
            "autostart_enabled": self.autostart_var.get(),
            "ask_before_delete": self.ask_before_delete,
            "language": i18n_instance.lang
        }
        self.config_mgr.save_config(config)

    def refresh_accounts(self):
         self.account_mgr.refresh_accounts()

    #funciones de inicio con el sistema de la aplicacion
    def on_closing(self):
        """Maneja el evento de cierre de la ventana principal"""
        self.closing = True
        # Guardar configuración al cerrar
        self._save_state()
        self.tray_mgr.on_closing()

    def get_autostart_path(self):
        autostart_dir = os.path.expanduser("~/.config/autostart")
        os.makedirs(autostart_dir, exist_ok=True)
        return os.path.join(autostart_dir, "easy-ocamlfuse.desktop")

    def check_autostart(self):
        return os.path.exists(self.get_autostart_path())

    def toggle_autostart(self):
        autostart_path = self.get_autostart_path()
        xdg_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        desktop_session = os.environ.get("DESKTOP_SESSION", "").lower()

        # Lista negra de entornos donde el autoinicio estándar NO funciona bien
        problematic_desktops = ["enlightenment", "bodhi"]

        is_problematic = any(name in xdg_desktop or name in desktop_session for name in problematic_desktops)

        exec_path = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../main.py"))
        icon_path = os.path.abspath(LOGO_FILE)
        desktop_entry = f'''[Desktop Entry]\nType=Application\nName=EasyOcamlfuse\nExec={exec_path} {script_path} --minimized\nIcon={icon_path}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n'''
        autostart_line = (
            f'\n# Autoinicio EasyOcamlfuse\n'
            f'if ! pgrep -f "gdrive_manager.py" > /dev/null; then\n'
            f'    nohup python3 "{script_path}" --minimized >/dev/null 2>&1 &\n'
            f'fi\n'
        )
        profile_path = os.path.expanduser("~/.profile")

        def autostart_line_in_profile():
            try:
                with open(profile_path, "r") as f:
                    return autostart_line.strip() in f.read()
            except FileNotFoundError:
                return False

        if self.autostart_var.get():
            if is_problematic:
                # Lógica para Bodhi/Enlightenment
                if not autostart_line_in_profile():
                    self.show_bodhi_autostart_dialog(autostart_line, profile_path)
            else:
                # Lógica para todos los demás entornos (permitir autoinicio)
                with open(autostart_path, "w") as f:
                    f.write(desktop_entry)
        else:
            # Desactivar autostart
            if is_problematic:
                try:
                    if os.path.exists(profile_path):
                        with open(profile_path, "r") as f:
                            lines = f.readlines()
                        with open(profile_path, "w") as f:
                            skip = False
                            for line in lines:
                                if line.strip() == "# Autoinicio EasyOcamlfuse":
                                    skip = True
                                if not skip:
                                    f.write(line)
                                if skip and line.strip() == "fi":
                                    skip = False
                    self.autostart_var.set(False)
                except Exception as e:
                    messagebox.showerror(
                        _("Error"),
                        _("No se pudo eliminar la línea de autoinicio de ~/.profile:\n{}").format(e)
                    )
            else:
                if os.path.exists(autostart_path):
                    os.remove(autostart_path)
        self._save_state()

    def show_bodhi_autostart_dialog(self, autostart_line, profile_path):
        top = tk.Toplevel(self.root)
        top.title(_("Autoinicio en Bodhi/Enlightenment"))
        top.geometry("600x340")
        top.withdraw()
        centrar_ventana(top, self.root)
        top.deiconify()
        msg = (
            _("En Bodhi/Enlightenment el inicio automático estándar puede no funcionar.\n\n") +
            _("Para asegurar el autoinicio, añade la siguiente línea al final de tu archivo ~/.profile:\n\n") +
            f"{autostart_line}\n" +
            _("Puedes copiar el texto, editarlo manualmente o pulsar el botón para añadirlo automáticamente.\n") +
            _("Luego, reinicia sesión.")
        )
        # Widget Text solo lectura, seleccionable y copiable
        txt = tk.Text(top, wrap="word", font=("Arial", 10), cursor="arrow", height=10)
        txt.insert("1.0", msg)
        txt.config(state="disabled")
        txt.pack(padx=16, pady=(18, 4), fill="both", expand=True)

        # Clic derecho para copiar selección
        def copiar_seleccion(event):
            try:
                sel = txt.selection_get()
                top.clipboard_clear()
                top.clipboard_append(sel)
                estado_label.config(text=_("Texto copiado al portapapeles"))
            except tk.TclError:
                pass
            return "break"
        txt.bind("<Button-3>", copiar_seleccion)

        # Label de estado para feedback de copiado
        estado_label = ttk.Label(top, text="", anchor="w", foreground="green")
        estado_label.pack(fill="x", padx=10, pady=(0, 8), side="bottom")

        def agregar_a_profile():
            try:
                # Eliminar cualquier línea antigua de autoinicio EasyOcamlfuse
                if os.path.exists(profile_path):
                    with open(profile_path, "r") as f:
                        lines = f.readlines()
                    with open(profile_path, "w") as f:
                        skip = False
                        for line in lines:
                            if line.strip().startswith("# Autoinicio EasyOcamlfuse"):
                                skip = True
                            if not skip:
                                f.write(line)
                            if skip and line.strip() == "fi":
                                skip = False
                # Añadir la línea actualizada con el nombre actual del script
                with open(profile_path, "a") as f:
                    f.write("\n" + autostart_line)
                messagebox.showinfo(
                        _("Listo"),
                        _("Se añadió la línea de autoinicio a tu ~/.profile correctamente.\n") +
                        _("Reinicia sesión para que surta efecto.")
                    )
                self.autostart_var.set(True)
            except Exception as e:
                messagebox.showerror(
                    _("Error"),
                    _("No se pudo modificar ~/.profile:\n{}").format(e)
                )
                self.autostart_var.set(False)
            top.destroy()
        ttk.Button(top, text=_("Añadir automáticamente a ~/.profile"), command=agregar_a_profile).pack(pady=8)
        def cerrar_y_desactivar():
            self.autostart_var.set(False)
            top.destroy()
        ttk.Button(top, text=_("Cerrar"), command=cerrar_y_desactivar).pack(pady=(0, 16))
        top.transient(self.root)
        top.grab_set()
        self.root.wait_window(top)

    def on_external_unmount(self, label, mount_point):
        """Callback cuando se detecta un desmontaje externo"""
        # Programar la actualización en el hilo principal de Tkinter
        self.root.after(0, self.refresh_mounts)
        
        try:
            if not hasattr(self, '_notify_inited'):
                notify2.init("EasyOcamlfuse")
                self._notify_inited = True
            n = notify2.Notification(
                _("Desmontaje Detectado"),
                _("La cuenta '{label}' fue desmontada externamente.").format(label=label),
                icon=LOGO_FILE
            )
            n.set_urgency(notify2.URGENCY_NORMAL)
            n.show()
        except Exception as e:
            print(f"Error al mostrar la notificación: {e}")

    #creacion de los widgets de la interfaz
    def create_widgets(self):
        """Crear los widgets de la interface"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text=_("Gestión Principal"))

        self.accounts_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.accounts_frame, text=_("Gestión de Cuentas"))

        self.create_main_tab()
        self.create_accounts_tab()

    def create_main_tab(self):
        """Crear la pestaña principal"""
        # Frame de estado del sistema
        self.status_frame = ttk.LabelFrame(self.main_frame, text=_("Estado del Sistema"))
        self.status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = ttk.Label(self.status_frame, text=_("Verificando instalación..."))
        self.status_label.pack(pady=5)
        
       
        self.mounted_frame = ttk.LabelFrame(self.main_frame, text=_("Cuentas Montadas"))
        self.mounted_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configuración del Treeview
        columns = (_("Cuenta"), _( "Etiqueta"), _( "Punto de Montaje"), _( "Estado"))
        self.mounted_tree = ttk.Treeview(self.mounted_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.mounted_tree.heading(col, text=col, anchor="center")
            self.mounted_tree.column(col, width=150, anchor="center")
        
        scrollbar = ttk.Scrollbar(self.mounted_frame, orient=tk.VERTICAL, command=self.mounted_tree.yview)
        self.mounted_tree.configure(yscrollcommand=scrollbar.set)
        
        
        self.mounted_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        
        buttons_frame = tk.Frame(self.main_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        
        center_frame = tk.Frame(buttons_frame)
        center_frame.pack(anchor="center")
        
        # Cargar iconos
        self.mount_icon = self._load_icon("assets/icons/gestionMontajes/Mount.png")
        self.unmount_selected_icon = self._load_icon("assets/icons/gestionMontajes/unmount.png")
        self.unmount_all_icon = self._load_icon("assets/icons/gestionMontajes/unmout_all.png")
        self.refresh_icon = self._load_icon("assets/icons/gestionMontajes/update.png")
        self.open_folder_icon = self._load_icon("assets/icons/gestionMontajes/open_folder.png")

        # Botones de acción
        self.btn_mount_account = tk.Button(center_frame, text=_("Montar Cuenta"), image=self.mount_icon, compound=tk.LEFT, command=self.mount_account)
        self.btn_mount_account.pack(side=tk.LEFT, padx=8, pady=2)
        self.btn_unmount_selected = tk.Button(center_frame, text=_("Desmontar Seleccionada"), image=self.unmount_selected_icon, compound=tk.LEFT, command=self.unmount_selected)
        self.btn_unmount_selected.pack(side=tk.LEFT, padx=8, pady=2)
        self.btn_unmount_all = tk.Button(center_frame, text=_("Desmontar Todas"), image=self.unmount_all_icon, compound=tk.LEFT, command=self.unmount_all)
        self.btn_unmount_all.pack(side=tk.LEFT, padx=8, pady=2)
        self.btn_refresh_mounts = tk.Button(center_frame, text=_("Actualizar"), image=self.refresh_icon, compound=tk.LEFT, command=self.refresh_mounts)
        self.btn_refresh_mounts.pack(side=tk.LEFT, padx=8, pady=2)
        self.btn_open_folder = tk.Button(center_frame, text=_("Abrir Carpeta"), image=self.open_folder_icon, compound=tk.LEFT, command=self.open_mount_folder)
        self.btn_open_folder.pack(side=tk.LEFT, padx=8, pady=2)

    def create_accounts_tab(self):
        """Crear la pestaña de gestión de cuentas con un layout mejorado."""
        
      
        self.new_account_frame = tk.LabelFrame(self.accounts_frame, text=_("Agregar Nueva Cuenta"))
        self.new_account_frame.pack(fill=tk.X, padx=5, pady=5)
        # Configurar la rejilla para que la columna 1 (entradas) se expanda
        self.new_account_frame.columnconfigure(1, weight=1)

     
        self.label_label = tk.Label(self.new_account_frame, text=_("Etiqueta:"))
        self.label_label.grid(row=0, column=0, sticky=tk.W, padx=(5,2), pady=5)
        self.label_entry = tk.Entry(self.new_account_frame, width=30)
        self.label_entry.grid(row=0, column=1, sticky="ew", padx=(0,5), pady=5)
        ToolTip(self.label_entry, _("Nombre identificador para tu cuenta (ej: personal, trabajo) NO! dejes este campo vacio"))
        
      
        self.client_id_label = tk.Label(self.new_account_frame, text=_("Client ID:"))
        self.client_id_label.grid(row=1, column=0, sticky=tk.W, padx=(5,2), pady=5)
        self.client_id_entry = tk.Entry(self.new_account_frame, width=50)
        self.client_id_entry.grid(row=1, column=1, sticky="ew", padx=(0,5), pady=5)
        ToolTip(self.client_id_entry, _("Client ID de tu proyecto en Google Cloud Console."))
        
        
        self.client_secret_label = tk.Label(self.new_account_frame, text=_("Client Secret:"))
        self.client_secret_label.grid(row=2, column=0, sticky=tk.W, padx=(5,2), pady=5)
        self.client_secret_entry = tk.Entry(self.new_account_frame, width=50, show="*")
        self.client_secret_entry.grid(row=2, column=1, sticky="ew", padx=(0,5), pady=5)
        ToolTip(self.client_secret_entry, _("Client Secret de tu proyecto en Google Cloud Console."))
        

        btns_frame = tk.Frame(self.new_account_frame)
        btns_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        # Cargar iconos
        self.load_credentials_icon = self._load_icon("assets/icons/gestionCuentas/tokensJson.png")
        self.create_account_icon = self._load_icon("assets/icons/gestionCuentas/create_account.png")
        self.help_icon = self._load_icon("assets/icons/gestionCuentas/help_create_tokens.png")
        self.delete_account_icon = self._load_icon("assets/icons/gestionCuentas/delete_account.png")
        self.reauthorize_account_icon = self._load_icon("assets/icons/gestionCuentas/reauthorized_account.png")
        self.update_list_icon = self._load_icon("assets/icons/gestionCuentas/update_list.png")
        self.restore_account_icon = self._load_icon("assets/icons/gestionCuentas/restore_account.png")
        self.clean_text_icon = self._load_icon("assets/icons/gestionCuentas/cleantext.png")

        # Botones de configuración
        self.btn_cargar_json = tk.Button(btns_frame, text=_("Cargar JSON"), image=self.load_credentials_icon, compound=tk.LEFT, command=self.account_mgr.cargar_credenciales_json)
        self.btn_cargar_json.pack(side=tk.LEFT, padx=5, pady=2)
        
        self.btn_config_cuenta = tk.Button(btns_frame, text=_("Configurar Cuenta"), image=self.create_account_icon, compound=tk.LEFT, command=self.setup_account)
        self.btn_config_cuenta.pack(side=tk.LEFT, padx=5, pady=2)
        
        self.btn_limpiar_credenciales = tk.Button(btns_frame, text=_("Limpiar"), image=self.clean_text_icon, compound=tk.LEFT, command=lambda: self._update_credential_fields_state(locked=False), state="disabled")
        self.btn_limpiar_credenciales.pack(side=tk.LEFT, padx=5, pady=2)

        self.btn_ayuda = tk.Button(btns_frame, text=_("Ayuda"), image=self.help_icon, compound=tk.LEFT, command=self.account_mgr.mostrar_guia_oauth)
        self.btn_ayuda.pack(side=tk.LEFT, padx=5, pady=2)

        # --- Frame de lista de cuentas configuradas ---
        self.accounts_list_frame = ttk.LabelFrame(self.accounts_frame, text=_("Cuentas Configuradas"))
        self.accounts_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        acc_columns = (_("Etiqueta"), _( "Client ID"), _( "Estado"), _( "Montar al iniciar"))
        self.accounts_tree = ttk.Treeview(self.accounts_list_frame, columns=acc_columns, show="headings", height=10)
        for col in acc_columns:
            self.accounts_tree.heading(col, text=col, anchor="center")
            if col == _( "Montar al iniciar"):
                self.accounts_tree.column(col, width=120, anchor="center")
            else:
                self.accounts_tree.column(col, width=200, anchor="center")
        
        acc_scrollbar = ttk.Scrollbar(self.accounts_list_frame, orient=tk.VERTICAL, command=self.accounts_tree.yview)
        self.accounts_tree.configure(yscrollcommand=acc_scrollbar.set)
        
        self.accounts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        acc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def on_automount_click(event):
            region = self.accounts_tree.identify('region', event.x, event.y)
            if region != 'cell': return
            col = self.accounts_tree.identify_column(event.x)
            if col != f"#{len(acc_columns)}": return
            row_id = self.accounts_tree.identify_row(event.y)
            if not row_id: return
            label = self.accounts_tree.item(row_id, 'values')[0]
            current = self.accounts.get(label, {}).get('automount', False)
            self.accounts[label]['automount'] = not current
            self._save_state()
            self.refresh_accounts()
        self.accounts_tree.bind('<Button-1>', on_automount_click)
        self.accounts_tree.bind('<Double-1>', self.on_label_edit_start)
        
        # --- Frame de gestión de cuentas (botones inferiores) ---
        acc_buttons_frame = tk.Frame(self.accounts_frame)
        acc_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        center_frame = tk.Frame(acc_buttons_frame)
        center_frame.pack(anchor="center")
        
        self.btn_delete_account = tk.Button(center_frame, text=_("Eliminar Cuenta"), image=self.delete_account_icon, compound=tk.LEFT, command=self.account_mgr.delete_account)
        self.btn_delete_account.pack(side=tk.LEFT, padx=10, pady=2)

        self.btn_reautorizar = tk.Button(center_frame, text=_("Reautorizar"), image=self.reauthorize_account_icon, compound=tk.LEFT, command=self.account_mgr.reauthorize_account, state="disabled")
        self.btn_reautorizar.pack(side=tk.LEFT, padx=10, pady=2)

        self.btn_update_list = tk.Button(center_frame, text=_("Actualizar Lista"), image=self.update_list_icon, compound=tk.LEFT, command=self.refresh_accounts)
        self.btn_update_list.pack(side=tk.LEFT, padx=10, pady=2)
        
        self.btn_restore_account = tk.Button(center_frame, text=_("Restaurar Cuenta"), image=self.restore_account_icon, compound=tk.LEFT, command=self.account_mgr.restore_account)
        self.btn_restore_account.pack(side=tk.LEFT, padx=10, pady=2)

        def on_account_select(event):
            selection = self.accounts_tree.selection()
            if not selection:
                self.btn_reautorizar.config(state="disabled")
                return
            item = self.accounts_tree.item(selection[0])
            estado = item['values'][2]
            if estado in (_("Pendiente"), _("Error")):
                self.btn_reautorizar.config(state="normal")
            else:
                self.btn_reautorizar.config(state="disabled")
            self._update_accounts_tab_button_states()

        self.accounts_tree.bind("<<TreeviewSelect>>", on_account_select)

    def _update_credential_fields_state(self, locked=False):
        """Controla el estado (editable/bloqueado) de los campos de credenciales."""
        if locked:
           
            self.client_id_entry.config(state="readonly")
            self.client_secret_entry.config(state="readonly")
            self.btn_cargar_json.config(state="disabled")
            self.btn_limpiar_credenciales.config(state="normal")
        else:
           
            self.label_entry.delete(0, tk.END)
            self.client_id_entry.config(state="normal")
            self.client_secret_entry.config(state="normal")
            self.client_id_entry.delete(0, tk.END)
            self.client_secret_entry.delete(0, tk.END)
            self.btn_cargar_json.config(state="normal")
            self.btn_limpiar_credenciales.config(state="disabled")

    def on_label_edit_start(self, event):
        """Inicia la edición de una etiqueta de cuenta con doble clic."""
        region = self.accounts_tree.identify('region', event.x, event.y)
        if region != 'cell':
            return

        column_id = self.accounts_tree.identify_column(event.x)
        if column_id != '#1':
            return

        row_id = self.accounts_tree.identify_row(event.y)
        if not row_id:
            return

        # Obtener la etiqueta actual y verificar si está montada
        old_label = self.accounts_tree.item(row_id, 'values')[0]
        if old_label in self.mounted_accounts:
            messagebox.showwarning(_("Cuenta Montada"), _("No puedes cambiar el nombre de '{}' mientras esté montada. Desmóntala primero.").format(old_label))
            return

        # Obtener las coordenadas de la celda para superponer el Entry
        x, y, width, height = self.accounts_tree.bbox(row_id, column_id)

        # Crear y configurar el campo de edición temporal
        entry = ttk.Entry(self.accounts_tree, justify='center')
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, old_label)
        entry.focus_force()

        def on_focus_out(event):
            """Cancela la edición si se pierde el foco."""
            entry.destroy()

        def on_confirm_edit(event):
            """Guarda el nuevo nombre al pulsar Enter."""
            new_label = entry.get().strip()
            entry.destroy()

            # Validaciones
            if not new_label or new_label == old_label:
                return 
            if new_label in self.accounts:
                messagebox.showerror(_("Error"), _("La etiqueta '{}' ya existe.").format(new_label))
                return

            old_gdfuse_path = os.path.expanduser(os.path.join(GDFUSE_DIR, old_label))
            new_gdfuse_path = os.path.expanduser(os.path.join(GDFUSE_DIR, new_label))

            if os.path.exists(old_gdfuse_path):
                try:
                    shutil.move(old_gdfuse_path, new_gdfuse_path)
                except Exception as e:
                    messagebox.showerror(_("Error"), _('''No se pudo renombrar la carpeta de configuración de ocamlfuse:\n{} a {}\n\nError: {}\n\nLa etiqueta se ha actualizado en la aplicación, pero es posible que necesites corregir la carpeta manualmente para evitar problemas.''').format(old_gdfuse_path, new_gdfuse_path, e))
                    return

            self.accounts[new_label] = self.accounts.pop(old_label)
            if old_label in self.deleted_accounts:
                self.deleted_accounts[new_label] = self.deleted_accounts.pop(old_label)
            
            self._save_state()
            self.refresh_accounts()
            messagebox.showinfo(_("Éxito"), _("La cuenta '{}' ha sido renombrada a '{}'.").format(old_label, new_label))

        entry.bind("<Return>", on_confirm_edit)
        entry.bind("<FocusOut>", on_focus_out)
    
    def create_menu(self):
        """Crear menú en la barra superior"""
        menubar = tk.Menu(self.root)
        
        # Menú Archivo
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label=_("Salir"), command=self.quit_application, accelerator="Alt+F4")
        menubar.add_cascade(label=_("Archivo"), menu=filemenu, underline=0)

        # Menú Edición
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label=_("Copiar"), accelerator="Ctrl+C", command=self.copiar_entry_focused)
        edit_menu.add_command(label=_("Pegar"), accelerator="Ctrl+V", command=self.pegar_entry_focused)
        edit_menu.add_command(label=_("Cortar"), accelerator="Ctrl+X", command=self.cortar_entry_focused)
        edit_menu.add_separator()
        edit_menu.add_command(label=_("Limpiar campos"), accelerator="Ctrl+L", command=self.limpiar_campos_credenciales)
        menubar.add_cascade(label=_("Edición"), menu=edit_menu, underline=0)

        # Menú Preferencias
        preferences_menu = tk.Menu(menubar, tearoff=0)
        preferences_menu.add_checkbutton(
            label=_("Iniciar con el sistema"),
            variable=self.autostart_var,
            command=self.toggle_autostart
        )
        preferences_menu.add_separator()
        preferences_menu.add_command(label=_("Restaurar configuración"), command=self.restore_config)

        # Submenú de Idioma
        self.language_var = tk.StringVar(value=i18n_instance.lang)  # Añade esto al inicio del método o en __init__

        language_menu = tk.Menu(preferences_menu, tearoff=0)
        language_menu.add_radiobutton(
            label=_("Español"),
            variable=self.language_var,
            value="es",
            command=lambda: self.change_language("es")
        )
        language_menu.add_radiobutton(
            label=_("English"),
            variable=self.language_var,
            value="en",
            command=lambda: self.change_language("en")
        )
        preferences_menu.add_cascade(label=_("Idioma"), menu=language_menu)

        menubar.add_cascade(label=_("Preferencias"), menu=preferences_menu, underline=0)
        

        # Menú Ayuda
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label=_("Acerca de..."), command=self.show_about_dialog)
        menubar.add_cascade(label=_("Ayuda"), menu=helpmenu, underline=2)

        self.root.config(menu=menubar)

        # Enlazar atajos de teclado a los métodos
        self.root.bind_all("<Control-c>", lambda e: self.copiar_entry_focused())
        self.root.bind_all("<Control-v>", lambda e: self.pegar_entry_focused())
        self.root.bind_all("<Control-x>", lambda e: self.cortar_entry_focused())
        self.root.bind_all("<Control-l>", lambda e: self.limpiar_campos_credenciales())

    #funciones de foco de los campos de entrada
    def get_focused_entry(self):
        widget = self.root.focus_get()
        if widget in [self.label_entry, self.client_id_entry, self.client_secret_entry]:
            return widget
        return None

    def copiar_entry_focused(self):
        entry = self.get_focused_entry()
        if entry:
            self.root.clipboard_clear()
            self.root.clipboard_append(entry.get())

    def pegar_entry_focused(self):
        entry = self.get_focused_entry()
        if entry:
            try:
                entry.delete(0, tk.END)
                entry.insert(0, self.root.clipboard_get())
            except tk.TclError:
                pass

    def cortar_entry_focused(self):
        entry = self.get_focused_entry()
        if entry:
            self.root.clipboard_clear()
            self.root.clipboard_append(entry.get())
            entry.delete(0, tk.END)

    def limpiar_campos_credenciales(self):
        self.label_entry.delete(0, tk.END)
        self.client_id_entry.delete(0, tk.END)
        self.client_secret_entry.delete(0, tk.END)

    #utilidad grafica para verificar e instalar ocamlfuse
    def check_installation(self):
        estado, mensaje, color = verificar_ocamlfuse()
        if hasattr(self.status_label, 'configure'):
            self.status_label.config(text=mensaje)
            self.status_label.configure(foreground=color)
        if estado:
            return True
        else:
            respuesta = messagebox.askyesno(
                _("Instalar ocamlfuse"),
                _("google-drive-ocamlfuse no está instalado.\n\n"
                  "¿Deseas instalarlo automáticamente ahora?\n\n"
                  "Se requerirá tu contraseña de administrador."),
                icon=messagebox.QUESTION,
                parent=self.root
            )
            if respuesta:
                return self.instalar_ocamlfuse()
            else:
                messagebox.showinfo(
                    _("Instalación manual"),
                    _("Puedes instalar google-drive-ocamlfuse manually:\n\n"
                      "1. Abre una terminal\n"
                      "2. Sigue las instrucciones en:\n"
                      "   https://github.com/astrada/google-drive-ocamlfuse\n\n"
                      "Después de instalar, reinicia esta aplicación."),
                    parent=self.root
                )
                return False

    def instalar_ocamlfuse(self):
        distro_id = detectar_distro_id()
        install_cmd = ""
        ppa_choice = "normal"
        if distro_id in ["ubuntu", "debian", "linuxmint", "pop"]:
            # Diálogo para elegir PPA
            ppa_dialog = tk.Toplevel(self.root)
            ppa_dialog.title(_("Seleccionar una versión de PPA"))
            ppa_dialog.geometry("490x260")  
            ppa_dialog.withdraw()
            centrar_ventana(ppa_dialog, self.root)
            ppa_dialog.deiconify()
            tk.Label(ppa_dialog, text=_("¿Qué versión deseas instalar?"), font=("Arial", 11)).pack(pady=18)

            radio_frame = tk.Frame(ppa_dialog)
            radio_frame.pack(pady=10, fill="x")
            ppa_var = tk.StringVar(value="normal")
            tk.Radiobutton(ppa_dialog, text=_("Estable (ppa:alessandro-strada/ppa)"), variable=ppa_var, value="normal").pack(anchor="w", padx=30)
            tk.Radiobutton(ppa_dialog, text=_("Beta (ppa:alessandro-strada/google-drive-ocamlfuse-beta)"), variable=ppa_var, value="beta").pack(anchor="w", padx=30)
            btn_frame = tk.Frame(ppa_dialog)
            btn_frame.pack(pady=18)
            def seleccionar():
                nonlocal ppa_choice
                ppa_choice = ppa_var.get()
                ppa_dialog.destroy()
            ttk.Button(btn_frame, text=_("Continuar"), command=seleccionar).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text=_("Cancelar"), command=ppa_dialog.destroy).pack(side=tk.LEFT, padx=10)
            ppa_dialog.transient(self.root)
            ppa_dialog.grab_set()
            self.root.wait_window(ppa_dialog)
            if not ppa_choice:
                return False
            install_cmd = obtener_comando_instalacion_ocamlfuse(distro_id, ppa_choice)
        else:
            install_cmd = obtener_comando_instalacion_ocamlfuse(distro_id)
            if not install_cmd:
                messagebox.showerror(
                    _("Distribución no soportada"),
                    _("No se pudo determinar tu distribución o no es soportada para instalación automática.\n\n") +
                    _("Por favor instala google-drive-ocamlfuse manualmente."),
                    parent=self.root
                )
                return False

        # Crear diálogo de progreso
        dialog = tk.Toplevel(self.root)
        dialog.title(_("Proceso de instalación"))
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.withdraw()
        centrar_ventana(dialog, self.root)
        dialog.deiconify()

        tk.Label(dialog, text=_("Instalando google-drive-ocamlfuse..."), font=("Arial", 12)).pack(pady=15)

        status_label = tk.Label(dialog, text=_("Preparando instalación..."))
        status_label.pack(pady=5)

        progress = ttk.Progressbar(dialog, mode='indeterminate')
        progress.pack(fill='x', padx=20, pady=10)
        progress.start()

        output_frame = tk.Frame(dialog)
        output_frame.pack(fill='both', expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(output_frame)
        scrollbar.pack(side='right', fill='y')

        output_text = tk.Text(output_frame, height=10, yscrollcommand=scrollbar.set)
        output_text.pack(fill='both', expand=True)
        scrollbar.config(command=output_text.yview)

        output_text.insert('end', _("Ejecutando comandos de instalación...\n"))
        output_text.see('end')

        # --- Define aquí los callbacks antes de llamar a instalar_ocamlfuse_async ---
        def output_callback(line):
            output_text.insert('end', line)
            output_text.see('end')

        def status_callback(text):
            status_label.config(text=text)

        def finish_callback(returncode):
            if returncode == 0:
                status_label.config(text=_("Instalación completada con éxito!"))
                output_text.insert('end', "\n✓ Instalación exitosa!\n")
                messagebox.showinfo(
                    _("Instalación exitosa"),
                    _("google-drive-ocamlfuse se instaló correctamente.\n\n"
                      "Reinicia la aplicación para continuar."),
                    parent=dialog
                )
                self.root.destroy()  # Forzar reinicio
            else:
                status_label.config(text=_("Error en la instalación"))
                output_text.insert('end', f"\n✗ Error en instalación (código {returncode})\n")
                messagebox.showerror(
                    _("Error de instalación"),
                    _("Ocurrió un error durante la instalación.\n\n"
                      "Consulta la salida para más detalles."),
                    parent=dialog
                )

       # llama a la función de utilidades
        instalar_ocamlfuse_async(install_cmd, output_callback, status_callback, finish_callback)

        return False
        
    
    def setup_account(self):
        """Configurar cuenta y limpiar el formulario al finalizar con éxito."""
        label = self.label_entry.get().strip()
        client_id = self.client_id_entry.get().strip()
        client_secret = self.client_secret_entry.get().strip()
        self.account_mgr.accounts = self.accounts
        ok, msg = self.account_mgr.validate_account_data(label, client_id, client_secret)
        if not ok:
            messagebox.showerror(_("Error"), msg)
            return

        try:
            cancel_event = threading.Event()
            progress_dialog = self.show_progress_dialog(_("Esperando autorización..."), cancel_event)

            success, email, error = self.account_mgr.setup_account_logic(
                label, client_id, client_secret, cancel_event
            )

            progress_dialog.destroy()

            if not success:
                error_messages = {
                    "server_error": _( "No se pudo iniciar el servidor OAuth"),
                    "cancelled": _( "Configuración cancelada por el usuario."),
                    "user_cancel": _( "Configuración cancelada por el usuario."),
                    "timeout": _( "No se recibió el código de autorización a tiempo"),
                    "oauth_error": _( "Error al completar la configuración OAuth"),
                    "duplicate_email": _("Ya existe una cuenta configurada con el correo '{email}'.").format(email=email or ""),
                }
                messagebox.showwarning(
                    _( "cancelled"),
                    error_messages.get(error, _( "La cuenta no fue configurada completamente.")),
                    parent=self.root
                )
                return

            if success:
                self.refresh_accounts()
                messagebox.showinfo(_("Éxito"), _("Cuenta '{label}' configurada correctamente").format(label=label))
                # Limpiar y resetear el formulario para la siguiente cuenta
                self.label_entry.delete(0, tk.END)
                self._update_credential_fields_state(locked=False)

        except Exception as e:
            messagebox.showerror(_("Error inesperado"), str(e))

    def show_progress_dialog(self, message, cancel_event=None):
        dialog = tk.Toplevel(self.root)
        dialog.title(_("Configurando cuenta"))
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)  
        dialog.withdraw()
        centrar_ventana(dialog, self.root)
        dialog.deiconify()
        tk.Label(dialog, text=message, font=("Arial", 10)).pack(pady=20)
        progress = ttk.Progressbar(dialog, mode='indeterminate')
        progress.pack(pady=10, padx=20, fill='x')
        progress.start()
        
        tk.Label(dialog, text=_("Autoriza la aplicación en tu navegador..."), 
                 font=("Arial", 9), fg="gray").pack(pady=5)

        # Añadir botón de cancelación si se proporciona el evento
        if cancel_event is not None:
            def cancel():
                cancel_event.set()
                dialog.destroy()
            ttk.Button(dialog, text=_("Cancelar"), command=cancel).pack(pady=10)
        # Permitir que el callback de OAuth también cierre y cancele
        dialog._cancel_event = cancel_event
        def close_and_cancel():
            if dialog.winfo_exists():
                cancel_event.set()
                dialog.destroy()
        dialog.close_and_cancel = close_and_cancel
        dialog.update()
        return dialog



    def mount_account(self):
        _ = i18n_instance.gettext  # Asegura función de traducción
        """Montar una cuenta seleccionada """
        if not self.accounts:
            messagebox.showwarning(_("Advertencia"), _("No hay cuentas configuradas"))
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(_("Seleccionar Cuenta a Montar"))
        dialog.geometry("380x320") 
        dialog.resizable(False, False)
        tk.Label(dialog, text=_("Selecciona la cuenta que deseas montar:")).pack(pady=12)
        dialog.withdraw()
        centrar_ventana(dialog, self.root)
        dialog.deiconify()

        tree = ttk.Treeview(dialog, columns=("cuenta",), show="", height=8)
        tree.column("cuenta", anchor="center")
        tree.heading("cuenta", text="")
        tree.tag_configure('disabled', foreground='gray')

        for name, data in self.accounts.items():
            is_configured = data.get("configured", False) and data.get("client_id") and data.get("client_secret")
            is_mounted = name in self.mounted_accounts

            if is_mounted:
                tree.insert("", tk.END, values=(f"{name} ({_('Montada')})",), iid=name, tags=('disabled',))
            elif not is_configured:
                tree.insert("", tk.END, values=(f"{name} ({_('No configurada')})",), iid=name, tags=('disabled',))
            else:
                tree.insert("", tk.END, values=(name,), iid=name)
        
        tree.pack(padx=16, pady=8, fill=tk.BOTH, expand=True)

        def on_tree_click(event):
            item_id = tree.identify_row(event.y)
            if item_id and 'disabled' in tree.item(item_id, 'tags'):
                return "break"
        tree.bind("<Button-1>", on_tree_click)

        # --- Checkbox para abrir carpeta ---
        open_folder_var = tk.BooleanVar(value=True)
        chk_open_folder = ttk.Checkbutton(dialog, text=_("Abrir carpeta al montar"), variable=open_folder_var)
        chk_open_folder.pack(pady=(5, 0))

        selected_account = {"value": None}

        def on_select():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(_("Advertencia"), _("Selecciona una cuenta para montar"), parent=dialog)
                return
            selected_account["value"] = selection[0]
            dialog.destroy()

        btn = ttk.Button(dialog, text=_("Montar"), command=on_select)
        btn.pack(pady=(8, 16), ipadx=10, ipady=4)
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

        account = selected_account["value"]
        if not account:
            return

        data = self.accounts[account]
        if not (data.get("configured", False) and data.get("client_id") and data.get("client_secret")):
            messagebox.showerror(
                _("Error"),
                _("La cuenta '{account}' no está configurada correctamente.").format(account=account)
            )            
            return

        if account in self.mounted_accounts and os.path.ismount(self.mounted_accounts[account]):
            messagebox.showinfo(
                _("Información"),
                _("La cuenta '{account}' ya está montada en {mount_point}").format(account=account, mount_point=self.mounted_accounts[account])
            )

            return

        mount_point = data.get('mount_point')
        if not mount_point:
            default_path = os.path.expanduser(f"~/{account}")
            os.makedirs(default_path, exist_ok=True)
            mount_point = default_path
            self.accounts[account]['mount_point'] = mount_point
            self._save_state()

        try:
            mount_cmd = [
                "google-drive-ocamlfuse",
                "-label", account,
                mount_point
            ]
            result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                self.mounted_accounts[account] = mount_point
                self.accounts[account]['mount_point'] = mount_point
                self._save_state()
                self.refresh_mounts()
                messagebox.showinfo(
                    _("Éxito"),
                    _("Cuenta '{account}' montada en {mount_point}").format(account=account, mount_point=mount_point)
                )
                # --- Abrir carpeta solo si el checkbox está marcado ---
                if open_folder_var.get():
                    self.open_folder(mount_point)
            else:
                messagebox.showerror(
                    _("Error"),
                    _("Error al montar:\n{stderr}").format(stderr=result.stderr)
                )
        except subprocess.TimeoutExpired:
            messagebox.showerror(_("Error"), _("Timeout al montar la cuenta"))
        except Exception as e:
            messagebox.showerror(_("Error"), _("Error inesperado: {}").format(str(e)))

    def unmount_selected(self):
        """Desmontar cuenta seleccionada"""
        selection = self.mounted_tree.selection()
        if not selection:
            messagebox.showwarning(_("Advertencia"), _("Selecciona una cuenta para desmontar"))
            return

        item = self.mounted_tree.item(selection[0])
        account = item['values'][0]
        mount_point = item['values'][2]

        self.mount_mgr.unmount_account(account, mount_point)
        self.refresh_mounts()

    def unmount_all(self):
        """Desmontar todas las cuentas y actualizar tabla"""
        if not self.mounted_accounts:
            messagebox.showinfo(_("Info"), _("No hay cuentas montadas"))
            return

        if messagebox.askyesno(_("Confirmar"), _("¿Desmontar todas las cuentas?")):
            errores = []
            for account, mount_point in list(self.mounted_accounts.items()):
                ok = self.mount_mgr.unmount_account(account, mount_point)
                if not ok:
                    errores.append(account)
            self.refresh_mounts()

            if errores:
                messagebox.showwarning(
                    _("Algunas cuentas no se desmontaron"),
                    _("No se pudieron desmontar las siguientes cuentas:\n{errores_str}\n"
                      "Verifica que no estén en uso.").format(errores_str=', '.join(errores))
                )
            else:
                messagebox.showinfo(_("Éxito"), _("Todas las cuentas fueron desmontadas correctamente."))

    def open_mount_folder(self):
        """Abrir carpeta de montaje seleccionada"""
        selection = self.mounted_tree.selection()
        if not selection:
            messagebox.showwarning(_("Advertencia"), _("Selecciona una cuenta montada"))
            return

        item = self.mounted_tree.item(selection[0])
        mount_point = item['values'][2]
        self.open_folder(mount_point)

    def open_folder(self, path):
        """Abrir carpeta con el gestor de archivos del sistema"""
        try:
            if sys.platform == "linux":
                subprocess.run(['xdg-open', path], check=True, timeout=10)
        except Exception as e:
            print(_("Error al abrir la carpeta {}: {}").format(path, e))

    def delete_account(self):
        self.account_mgr.delete_account()
        self.refresh_accounts()  

    def restore_config(self):
        """Restablece la configuración a valores de fábrica"""
        config_path = os.path.expanduser("~/.gdrive_manager_config.json")
        if messagebox.askyesno(
            _("Restaurar configuración"),
            _("¿Seguro que quieres restaurar la configuración?\nSe perderán todas las cuentas y preferencias guardadas.")
        ):
            try:
                if os.path.isfile(config_path):
                    os.remove(config_path)
                self.accounts = {}
                self.mounted_accounts = {}
                self.deleted_accounts = {}
                self.autostart_enabled = True
                self.ask_before_delete = True
                self._save_state()
                messagebox.showinfo(_("Restaurado"), _("Configuración restaurada. Reinicia la aplicación para aplicar los cambios."))
            except Exception as e:
                messagebox.showerror(_("Error"), _('''No se pudo restaurar la configuración:\n{}''').format(e))

    def restore_account(self):
        self.account_mgr.restore_account()
        self.refresh_accounts() 

    def reauthorize_account(self):
        self.account_mgr.reauthorize_account()

    def complete_oauth_setup(self, label, client_id, client_secret, redirect_url, auth_code):
        try:
            cmd = [
                "google-drive-ocamlfuse",
                "-headless",
                "-id", client_id,
                "-secret", client_secret,
                "-label", label,
                "-redirect_uri", redirect_url
            ]
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=auth_code + '\n', timeout=30)
            
            if process.returncode == 0:
                print(f"OAuth completado para {label}")
                return True
            else:
                print(f"Error en OAuth: {stderr}")
                return False
        except Exception as e:
            print(f"Error al completar OAuth: {e}")
            return False

    def refresh_accounts(self):
        _ = i18n_instance.gettext  # Asegura función de traducción
        """Actualizar lista de cuentas, incluyendo las detectadas externamente en ~/.gdfuse, sin duplicados"""
        # Limpiar el treeview
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)

        # Detectar cuentas externas en ~/.gdfuse
        gdfuse_path = os.path.expanduser(GDFUSE_DIR)
        cuentas_externas = {}
        combinaciones = set()  # Para evitar duplicados (label, client_id
        
        if os.path.isdir(gdfuse_path):
            for label in os.listdir(gdfuse_path):
                config_file = os.path.join(gdfuse_path, label, "config")
                if os.path.isfile(config_file):
                    client_id = ""
                    client_secret = ""
                    try:
                        with open(config_file, "r") as f:
                            for line in f:
                                if line.startswith("client_id="):
                                    client_id = line.split("=", 1)[1].strip()
                                elif line.startswith("client_secret="):
                                    client_secret = line.split("=", 1)[1].strip()
                        
                      
                        if client_id and (label, client_id) not in combinaciones:
                            cuentas_externas[label] = {
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "configured": True,
                                "externally_detected": True
                            }
                            combinaciones.add((label, client_id))
                    except Exception as e:
                        print(f"Error leyendo config de {label}: {e}")

            # Eliminar de cuentas_externas las que estén en la blacklist
        for label in list(cuentas_externas.keys()):
            if label in self.deleted_accounts and self.deleted_accounts[label].get("blacklist"):
                del cuentas_externas[label]

        cuentas_finales = dict(self.accounts)  
        for label, data in cuentas_externas.items():
            if label in cuentas_finales:
                if not cuentas_finales[label].get("configured", False):
                    continue
                data = dict(data)  
                for key in ["automount", "mount_point"]:
                    if key in cuentas_finales[label]:
                        data[key] = cuentas_finales[label][key]
            cuentas_finales[label] = data

       
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)

        # Mostrar en el treeview
        for label, data in cuentas_finales.items():
            if not data.get("configured", False):
                status = _("Pendiente")
            elif data.get("externally_detected", False) and label not in self.accounts:
                status = _("Importada")
            else:
                status = _("Configurada")

            client_id_short = data.get("client_id", "")[:20] + "..." if len(data.get("client_id", "")) > 20 else data.get("client_id", "")
            automount = data.get('automount', False)
            check = "✓" if automount else "□"
            self.accounts_tree.insert("", tk.END, values=(label, client_id_short, status, check))

        # Actualizar self.accounts y guardar
        self.accounts = cuentas_finales
        self._save_state()
        self._update_accounts_tab_button_states()

    def refresh_mounts(self):
        """Actualizar lista de montajes sin duplicados"""
        for item in self.mounted_tree.get_children():
            self.mounted_tree.delete(item)

        # Crear un mapa de puntos de montaje a etiquetas desde la configuración
        mount_point_to_label_map = {
            data.get('mount_point'): label
            for label, data in self.accounts.items() if data.get('mount_point')
        }

        seen_mount_points = set()
        active_mounts = {}

        try:
            result = subprocess.run(["mount"], capture_output=True, text=True, timeout=10)
            mount_lines = result.stdout.split('\n')

            for line in mount_lines:
                if 'google-drive-ocamlfuse' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mount_point = parts[2]
                        seen_mount_points.add(mount_point)

                        # 1. Buscar la etiqueta en nuestro mapa de configuración
                        label = mount_point_to_label_map.get(mount_point)

                        # 2. Si no se encuentra, usar métodos de fallback
                        if not label:
                            label = self.mount_mgr.get_label_from_mount_point(mount_point)
                            if label == _("Desconocido"):
                                device = parts[0]
                                if '@' in device and 'google-drive-ocamlfuse' in device:
                                    label = device.split('@')[0]

                        active_mounts[mount_point] = label or _("Desconocido")

        except Exception as e:
            print(f"Error al ejecutar el comando 'mount': {e}")

        # Limpiar y reconstruir self.mounted_accounts
        self.mounted_accounts.clear()
        for mount_point, label in active_mounts.items():
            self.mounted_accounts[label] = mount_point

        for label, mount_point in self.mounted_accounts.items():
            status = _("Montado") if os.path.ismount(mount_point) else _("Error")
            self.mounted_tree.insert("", tk.END, values=(label, label, mount_point, status))
            self._save_state()
            self._update_main_tab_button_states()

    def _update_main_tab_button_states(self):
        """Habilita o deshabilita los botones de la pestaña principal según si hay cuentas montadas."""
        has_mounted_accounts = bool(self.mounted_tree.get_children())

        # Botones que siempre deben estar activos
        self.btn_mount_account.config(state="normal")
        self.btn_refresh_mounts.config(state="normal")

        # Botones que dependen de si hay cuentas montadas
        if has_mounted_accounts:
            self.btn_unmount_selected.config(state="normal")
            self.btn_unmount_all.config(state="normal")
            self.btn_open_folder.config(state="normal")
        else:
            self.btn_unmount_selected.config(state="disabled")
            self.btn_unmount_all.config(state="disabled")
            self.btn_open_folder.config(state="disabled")

    def _update_accounts_tab_button_states(self):
        """Habilita o deshabilita el botón de restaurar cuenta según si hay cuentas eliminadas."""
        if self.deleted_accounts:
            self.btn_restore_account.config(state="normal")
        else:
            self.btn_restore_account.config(state="disabled")

        if self.accounts_tree.selection():
            self.btn_delete_account.config(state="normal")
        else:
            self.btn_delete_account.config(state="disabled")
        


    def automount_accounts(self):
        """Montar automáticamente las cuentas marcadas como 'automount' al iniciar la app."""
        for label, data in self.accounts.items():
            if label in self.deleted_accounts and self.deleted_accounts[label].get("blacklist"):
                continue
            if (
                data.get("automount", False)
                and data.get("configured", False)
                and data.get("client_id")
                and data.get("client_secret")
            ):
                mount_point = data.get('mount_point')
                if not mount_point:
                    mount_point = os.path.expanduser(f"~/{label}")
                    os.makedirs(mount_point, exist_ok=True)
                    self.accounts[label]['mount_point'] = mount_point
                    self._save_state()
                if label not in self.mounted_accounts or not os.path.ismount(mount_point):
                    try:
                        mount_cmd = [
                            "google-drive-ocamlfuse",
                            "-label", label,
                            mount_point
                        ]
                        result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)
                        if result.returncode == 0:
                            self.mounted_accounts[label] = mount_point
                            self.accounts[label]['mount_point'] = mount_point
                            self._save_state()
                            self.refresh_mounts()
                        else:
                            error_msg = result.stderr.strip()
                            if "access_token" in error_msg or "invalid_grant" in error_msg:
                                print(_("No se monta '{}' porque el token OAuth no es válido o ha caducado. Por favor, reautoriza la cuenta.").format(label))
                            else:
                                print(_("Error al montar '{}': {}").format(label, error_msg))
                    except Exception as e:
                        print(_("Error al montar '{}': {}").format(label, e))

    def show_about_dialog(self):
        """Mostrar información de la aplicación y enlaces en pestañas."""
        top = tk.Toplevel(self.root)
        top.title(_("Acerca de Easy Ocamlfuse"))
        top.geometry("500x400")
        top.resizable(False, False)
        top.withdraw()
        centrar_ventana(top, self.root)
        top.deiconify()

        notebook = ttk.Notebook(top)
        notebook.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- Pestaña "Acerca de" ---
        about_frame = ttk.Frame(notebook)
        notebook.add(about_frame, text=_("Acerca de"))

        # Frame para el contenido principal (todo menos el botón de actualizar)
        main_content_frame = ttk.Frame(about_frame)
        main_content_frame.pack(fill=tk.BOTH, expand=True)

        # Frame para el icono a la izquierda
        icon_frame = tk.Frame(main_content_frame)
        icon_frame.pack(side=tk.LEFT, fill=tk.Y, anchor="n", padx=(10,0), pady=(10,0))

        icon_img = self._load_icon("assets/icons/gdrive_logo.png", size=(64, 64))
        if icon_img:
            icon_label = tk.Label(icon_frame, image=icon_img)
            icon_label.image = icon_img  # Mantener referencia
            icon_label.pack()

        # Frame para el texto a la derecha del icono
        text_frame = tk.Frame(main_content_frame)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        tk.Label(text_frame, text="Easy Ocamlfuse", font=("Arial", 16, "bold")).pack(pady=(10, 4), anchor="center")
        tk.Label(text_frame, text=_("Gestor gráfico para Google Drive Ocamlfuse"), font=("Arial", 11)).pack(pady=(0, 10), anchor="center")
        tk.Label(text_frame, text=_("Versión: {}").format(APP_VERSION), font=("Arial", 10)).pack(pady=(0, 10), anchor="center")
        tk.Label(text_frame, text=_("Repositorio y descargas en:"), font=("Arial", 10)).pack(anchor="center")
        
        enlace1 = tk.Label(text_frame, text="https://github.com/ayalarol/Easy-ocamlfuse", 
                          fg="blue", cursor="hand2", font=("Arial", 10, "underline"))
        enlace1.pack(anchor="center")
        enlace1.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/ayalarol/Easy-ocamlfuse"))
        
        tk.Label(text_frame, text=_("Basado en el software original:"), font=("Arial", 10)).pack(pady=(14, 0), anchor="center")
        
        enlace2 = tk.Label(text_frame, text="https://github.com/astrada/google-drive-ocamlfuse", 
                          fg="blue", cursor="hand2", font=("Arial", 10, "underline"))
        enlace2.pack(anchor="center")
        enlace2.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/astrada/google-drive-ocamlfuse"))
        
        # Botón de Actualizar, empaquetado en la parte inferior del about_frame
        update_button = ttk.Button(about_frame, text=_("Buscar actualizaciones"), command=self.check_for_updates_manual)
        update_button.pack(side=tk.BOTTOM, pady=19)
        
        # --- Pestaña "Créditos" ---
        credits_frame = ttk.Frame(notebook)
        notebook.add(credits_frame, text=_("Créditos"))

        tk.Label(credits_frame, text=_("Autor: ayalarol"), font=("Arial", 12, "bold")).pack(pady=20)
        tk.Label(credits_frame, text=_("¡Gracias por usar Easy Ocamlfuse!"), font=("Arial", 10)).pack()

        paypal_url = "https://www.paypal.com/donate/?hosted_button_id=N2M3P5A24QKF4"
        paypal_label = tk.Label(
            credits_frame,
            text=_("¿Te gusta el proyecto? ¡Dame energías con un café en PayPal! :D"),
            fg="blue", cursor="hand2", font=("Arial", 10, "underline")
        )
        paypal_label.pack(pady=(10, 0))
        paypal_label.bind("<Button-1>", lambda e: webbrowser.open(paypal_url))

        # --- Pestaña "Licencia" ---
        license_frame = ttk.Frame(notebook)
        notebook.add(license_frame, text=_("Licencia"))

        license_text_frame = tk.Frame(license_frame, bg="#f7f7f7")
        license_text_frame.pack(fill=tk.BOTH, padx=10, pady=10, expand=True)
        
        license_path = os.path.join(os.path.dirname(__file__), "assets/resources", "LICENSE.txt")
        license_text = ""
        try:
            with open(license_path, "r") as f:
                license_text = f.read()
        except Exception as e:
            license_text = f"Error al cargar la licencia: {e}"

        # Widget Text con Scrollbar, sin traducción, más vistoso
        text_frame = tk.Frame(license_text_frame, bg="#f7f7f7")
        text_frame.pack(fill=tk.BOTH, expand=True)
        license_label = tk.Text(text_frame, wrap="word", font=("Consolas", 10), height=12, bg="#f7f7f7", relief=tk.FLAT, borderwidth=0)
        license_label.insert(tk.END, license_text.strip())
        license_label.config(state="disabled")
        license_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0), pady=(0, 0))

        license_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=license_label.yview)
        license_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        license_label.config(yscrollcommand=license_scrollbar.set)

    def check_for_updates_manual(self):
        update_info = check_for_updates()
        if update_info:
            if messagebox.askyesno(_("Actualización disponible"), 
                                f"{_('Hay una nueva versión disponible:')} {update_info['version']}\n\n{update_info['notes']}\n\n{_('¿Desea ir a la página de descarga?')}"):
                webbrowser.open(update_info['url'])
        else:
            messagebox.showinfo(_("Sin actualizaciones"), _("Tu versión está actualizada."))

    def check_for_updates_on_startup(self):
        threading.Thread(target=self._check_for_updates_background, daemon=True).start()

    def _check_for_updates_background(self):
        update_info = check_for_updates()
        if update_info:
            self.show_update_notification(update_info)

    def show_update_notification(self, update_info):
        message = f"{_('Nueva versión disponible:')} {update_info['version']}. {_('Haz clic en Ayuda -> Acerca de para más detalles.')}"
        self.show_notification_banner(message)

    def show_notification_banner(self, message):
        banner = tk.Label(self.root, text=message, bg="yellow", fg="black", font=("Helvetica", 10, "bold"), cursor="hand2")
        banner.pack(fill=tk.X, side=tk.BOTTOM)
        
        def open_about_and_hide():
            self.show_about_dialog()
            banner.pack_forget()

        banner.bind("<Button-1>", lambda e: open_about_and_hide())
        self.root.after(15000, lambda: banner.pack_forget() if banner.winfo_exists() else None)

    def quit_application(self, icon=None, item=None):
        """Salir de la aplicación"""
        if icon:  # Si se llama desde la bandeja del sistema
            # Mostrar ventana temporalmente para el diálogo
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            
            if not messagebox.askyesno(_("Salir"), _("¿Deseas cerrar la aplicación?")):
                self.root.withdraw()  # Ocultar ventana si cancela
                return
        
        if self.tray_mgr.tray_icon:
            try:
                self.tray_mgr.tray_icon.stop()
            except Exception as e:
                print(f"Error al detener la bandeja del sistema: {e}")
        
        self.root.quit()
        self.root.destroy()
        
        # Forzar salida del proceso si es necesario
        try:
            import sys
            sys.exit(0)
        except:
            pass

    def change_language(self, lang):
        i18n_instance.lang = lang
        i18n_instance.translation = i18n_instance._setup_translation()
        global _
        _ = i18n_instance.gettext
        self.language_var.set(lang)  # <-- Añade esto
        self._save_state()
        self.refresh_ui_texts() 
        messagebox.showinfo(
            _("Idioma cambiado"),
            _("El idioma se ha cambiado. Reinicia la aplicación para aplicar todos los cambios.")
        )

    def refresh_ui_texts(self):
        """Actualiza los textos de los widgets de la UI."""
        # Actualizar título de la ventana principal
        self.root.title(_("Easy Ocamlfuse"))
        # Actualizar título de la ventana principal
        self.root.title(_("Easy Ocamlfuse"))

        # Actualizar textos de las pestañas del Notebook
        self.notebook.tab(0, text=_("Gestión Principal"))
        self.notebook.tab(1, text=_("Gestión de Cuentas"))

        # Actualizar textos en la pestaña principal
        self.status_frame.config(text=_("Estado del Sistema"))
        self.status_label.config(text=_("Verificando instalación..."))
        self.mounted_frame.config(text=_("Cuentas Montadas"))
        
        # Actualizar encabezados del Treeview de montajes
        columns = (_("Cuenta"), _( "Etiqueta"), _( "Punto de Montaje"), _( "Estado"))
        for i, col_text in enumerate(columns):
            self.mounted_tree.heading(self.mounted_tree["columns"][i], text=col_text)

        self.btn_mount_account.config(text=_("Montar Cuenta"))
        self.btn_unmount_selected.config(text=_("Desmontar Seleccionada"))
        self.btn_unmount_all.config(text=_("Desmontar Todas"))
        self.btn_refresh_mounts.config(text=_("Actualizar"))
        self.btn_open_folder.config(text=_("Abrir Carpeta"))

        # Actualizar textos en la pestaña de cuentas
        self.new_account_frame.config(text=_("Agregar Nueva Cuenta"))
        self.label_label.config(text=_("Etiqueta:"))
        self.client_id_label.config(text=_("Client ID:"))
        self.client_secret_label.config(text=_("Client Secret:"))
        
        # Actualizar ToolTips (requiere recrearlos o actualizar su texto si la clase ToolTip lo permite)
        # Por simplicidad, aquí solo se actualizan los textos de los botones
        self.btn_cargar_json.config(text=_("Cargar JSON"))
        self.btn_config_cuenta.config(text=_("Configurar Cuenta"))
        self.btn_limpiar_credenciales.config(text=_("Limpiar"))
        self.btn_ayuda.config(text=_("Ayuda"))

        self.accounts_list_frame.config(text=_("Cuentas Configuradas"))
        
        # Actualizar encabezados del Treeview de cuentas
        acc_columns = (_("Etiqueta"), _( "Client ID"), _( "Estado"), _( "Montar al iniciar"))
        for i, col_text in enumerate(acc_columns):
            self.accounts_tree.heading(self.accounts_tree["columns"][i], text=col_text)

        self.btn_delete_account.config(text=_("Eliminar Cuenta"))
        self.btn_reautorizar.config(text=_("Reautorizar"))
        self.btn_update_list.config(text=_("Actualizar Lista"))
        self.btn_restore_account.config(text=_("Restaurar Cuenta"))

     
        self.create_menu() 

        self.check_installation()

        # Actualizar las listas de cuentas y montajes
        self.refresh_accounts()
        self.refresh_mounts()
    def run(self):
        self.root.mainloop()