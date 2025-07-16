#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2025 ayalarol
#
# Este programa es software libre: puedes redistribuirlo y/o modificarlo
# bajo los términos de la Licencia Pública General GNU tal como ha sido
# publicada por la Free Software Foundation
# Este programa se distribuye con la esperanza de que sea útil, pero
# SIN GARANTÍA ALGUNA; ni siquiera la garantía implícita
# MERCANTIL o de APTITUD PARA UN PROPÓSITO PARTICULAR.
# Consulta los detalles de la Licencia Pública General GNU para más información ve a /assets/resources/LICENSE.txt
# Debes haber recibido una copia de la Licencia Pública General GNU
# junto a este programa. En caso contrario, consulta <http://www.gnu.org/licenses/>.

import os
import re
import json
import threading
import subprocess
import webbrowser
import random
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from .utils import centrar_ventana
from .oauth import OAuthServer
from .constants import GDFUSE_DIR, OAUTH_PORT
from .i18n import i18n_instance
from .encryption import EncryptionManager
_ = i18n_instance.gettext


class AccountManager:
    def __init__(self, main_app, accounts, deleted_accounts, save_cb, refresh_cb, ask_before_delete):
        self.main_app = main_app
        self.root = main_app.root
        self.accounts = accounts
        self.deleted_accounts = deleted_accounts
        self.save_config = save_cb
        self.refresh_accounts_ui = refresh_cb
        self.ask_before_delete = ask_before_delete
        self.encryption_manager = EncryptionManager()

    def validate_account_data(self, label, client_id, client_secret):
        label = label.strip()
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        
        if not label:
            return False, _("La etiqueta no puede estar vacía. Escribe un nombre único para la cuenta.")

        if label in self.accounts:
            return False, _(f"Ya existe una cuenta con la etiqueta '{label}'. Usa otra diferente.")

        if not all((client_id, client_secret)):
            return False, _("Client ID y Client Secret son obligatorios")

        if not re.match(r"^[0-9]+-[0-9a-zA-Z]+\.apps\.googleusercontent\.com$", client_id):
            return False, _("El Client ID debe tener el formato:\n1234567890-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com")

        if len(client_secret) < 24 or not re.match(r"^[a-zA-Z0-9_-]{24,}$", client_secret):
            return False, _("El Client Secret debe ser una cadena alfanumérica de al menos 24 caracteres.")

        # Validar Client ID único (ignorando espacios y mayúsculas)
        for cuenta in self.accounts.values():
            if cuenta.get("client_id", "").strip().lower() == client_id.lower():
                return False, _(
                    _("Ya existe una cuenta configurada con este Client ID.\n") +
                    _("No puedes usar el mismo archivo de credenciales para varias cuentas.\n") +
                    _("Si quieres acceder a diferentes Google Drive, crea credenciales distintas en Google Cloud Console.")
                )

        return True, None

    def show_progress_dialog(self, message, cancel_event=None):
        dlg = tk.Toplevel(self.root)
        dlg.title(_("Configurando cuenta"))
        dlg.geometry("400x230")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)
        dlg.withdraw()
        from .utils import centrar_ventana
        centrar_ventana(dlg, self.root)
        dlg.deiconify()
        
        tk.Label(dlg, text=message, font=("Arial", 10)).pack(pady=20)
        
        pb = ttk.Progressbar(dlg, mode='indeterminate')
        pb.pack(fill='x', padx=20, pady=10)
        pb.start()
        
        tk.Label(dlg, text=_("Autoriza en navegador..."), font=("Arial", 9), fg="gray").pack(pady=5)
        
        if cancel_event:
            def cancel():
                cancel_event.set()
                dlg.destroy()
            ttk.Button(dlg, text=_("Cancelar"), command=cancel).pack(pady=10)
        
        dlg.update()
        return dlg

    

    def complete_oauth_setup(self, label, client_id, client_secret, redirect_url, auth_code):
        try:
            # Asegurarse de que el client_secret esté descifrado antes de usarlo
            try:
                client_secret_plain = self.encryption_manager.decrypt(client_secret)
            except Exception:
                client_secret_plain = client_secret
            cmd = [
                "google-drive-ocamlfuse", "-headless",
                "-id", client_id, "-secret", client_secret_plain,
                "-label", label, "-redirect_uri", redirect_url
            ]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            out, err = proc.communicate(input=auth_code + "\n", timeout=30)
            if proc.returncode != 0:
                print(f"Error OAuth: {err}")
                return False, None
            tokens_path = os.path.expanduser(f"~/.gdfuse/{label}/tokens.json")
            access_token = ""
            if os.path.isfile(tokens_path):
                with open(tokens_path, "r") as f:
                    tokens = json.load(f)
                    access_token = tokens.get("access_token", "")
            email = self.get_email_from_token(access_token) if access_token else None
            return True, email
        except Exception as e:
            print(f"Error OAuth: {e}")
            return False, None

    def reauthorize_account(self):
        sel = self.main_app.accounts_tree.selection()
        if not sel:
            messagebox.showwarning(_("Advertencia"), _( "Selecciona una cuenta"))
            return
        lbl = self.main_app.accounts_tree.item(sel[0])['values'][0]
        data = self.accounts.get(lbl)
        if not data:
            messagebox.showerror(_("Error"), _( "Cuenta no encontrada"))
            return

        try:
            client_secret = self.encryption_manager.decrypt(self._ensure_encrypted(data['client_secret']))
        except Exception as e:
            messagebox.showerror(_("Error de Cifrado"), _("No se pudo descifrar el client_secret. La clave de cifrado puede haber cambiado o el archivo estar corrupto."))
            return

        try:
            from . import oauth
            cancel_evt = threading.Event()
            dlg = self.show_progress_dialog(_("Reautorizando..."), cancel_evt)
            
            auth_code, error = oauth.authenticate(
                data['client_id'], client_secret, OAUTH_PORT, cancel_evt, timeout=120
            )
            dlg.destroy()

            if error:
                error_messages = {
                    "server_error": _("No se pudo iniciar el servidor OAuth"),
                    "cancelled": _("Reautorización cancelada por el usuario."),
                    "user_cancel": _("Reautorización cancelada por el usuario."),
                    "timeout": _("No se recibió el código de autorización a tiempo"),
                    "oauth_error": _("Error al completar la reautorización OAuth"),
                }
                messagebox.showerror(_("Error"), error_messages.get(error, _("Error desconocido")))
                return

            redirect_url = f"http://localhost:{OAUTH_PORT}"
            ok, email = self.complete_oauth_setup(
                lbl, data['client_id'], client_secret, redirect_url, auth_code
            )
            if ok:
                self.accounts[lbl] = self._account_to_dict(
                    lbl, data['client_id'], client_secret, configured=True, externally_detected=data.get('externally_detected', False), email=email
                )
                self.save_config()
                self.refresh_accounts_ui()
                self.main_app.root.update_idletasks()
                messagebox.showinfo(_("Éxito"), _("'La cuenta{lbl}' ha sido reautorizada").format(lbl=lbl))
            else:
                messagebox.showerror(_("Error"), _("Reautorización falló"))
        finally:
            pass

    def refresh_accounts(self):
        """Lee ~/.gdfuse, fusiona con self.accounts, filtra blacklist, actualiza Treeview y sincroniza con la app principal."""
        gdfp = os.path.expanduser(GDFUSE_DIR)
        ext = {}
        combinaciones = set()
        if os.path.isdir(gdfp):
            for lbl in os.listdir(gdfp):
                cfg = os.path.join(gdfp, lbl, "config")
                if os.path.isfile(cfg):
                    client_id = ""
                    client_secret = ""
                    try:
                        with open(cfg, "r") as f:
                            for line in f:
                                if line.startswith("client_id="):
                                    client_id = line.split("=", 1)[1].strip()
                                elif line.startswith("client_secret="):
                                    client_secret = line.split("=", 1)[1].strip()
                        if client_id and (lbl, client_id) not in combinaciones:
                            # Solo marcar como importada si no existe ya como interna
                            ext[lbl] = self._account_to_dict(
                                lbl, client_id, client_secret, configured=True, externally_detected=True
                            )
                            combinaciones.add((lbl, client_id))
                    except Exception as e:
                        print(f"Error leyendo config de {lbl}: {e}")

        # Filtrar blacklist en externas
        for lbl in list(ext):
            if lbl in self.deleted_accounts and self.deleted_accounts[lbl].get("blacklist"):
                del ext[lbl]

        # Fusionar externas con internas, pero nunca agregar cuentas en blacklist
        merged = dict(self.accounts)
        for lbl, data in ext.items():
            if lbl in self.deleted_accounts and self.deleted_accounts[lbl].get("blacklist"):
                continue  # No agregar cuentas en blacklist
            if lbl in merged:
                # Si la cuenta ya existe internamente no cambiar a externally
                data["externally_detected"] = merged[lbl].get("externally_detected", data.get("externally_detected", True))
                data["configured"] = merged[lbl].get("configured", data.get("configured", True))
                if merged[lbl].get("automount"):
                    data["automount"] = merged[lbl].get("automount")
                if merged[lbl].get("mount_point"):
                    data["mount_point"] = merged[lbl].get("mount_point")
            merged[lbl] = data

       
        for lbl in list(merged):
            if lbl in self.deleted_accounts and self.deleted_accounts[lbl].get("blacklist"):
                del merged[lbl]

        self.accounts = merged
        self.main_app.accounts = self.accounts
        self.main_app.deleted_accounts = self.deleted_accounts
        self.root.after(0, self.save_config)
        self.main_app.root.update_idletasks()  

    def delete_account(self):
        """Eliminar cuenta seleccionada, guardando el punto de montaje para asegurar su posible eliminación."""
        selection = self.main_app.accounts_tree.selection()
        if not selection:
            mensajes = [
                _("¡Hey! Primero selecciona una cuenta antes de intentar borrarla, no borres el aire :)."),
                _("¿Intentas eliminar el vacío? Selecciona una cuenta real, por favor."),
                _("¡Ups! No hay ninguna cuenta seleccionada para eliminar. ¡Elige una primero!"),
                _("Nada seleccionado, nada eliminado. ¡Así de simple!"),
                _("Selecciona una cuenta antes de hacerla desaparecer como por arte de magia.")
            ]
            messagebox.showwarning(_("Advertencia"), random.choice(mensajes))
            return

        item = self.main_app.accounts_tree.item(selection[0])
        account = item['values'][0]

        # Verificar si la cuenta está montada
        if account in self.main_app.mounted_accounts:
            messagebox.showwarning(
                _( "Cuenta Montada"),
                _("La cuenta '{account}' está actualmente montada. Por favor, desmonta la unidad antes de eliminar la cuenta.").format(account=account)
            )
            return
        
        # Guardar el punto de montaje antes de cualquier operación
        mount_point_to_delete = self.accounts.get(account, {}).get('mount_point')

       
        if not mount_point_to_delete:
            #Intentar encontrarlo si está actualmente montado
            try:
                result = subprocess.run(['mount'], capture_output=True, text=True, check=True)
                for line in result.stdout.splitlines():
                    if 'google-drive-ocamlfuse' in line and account in line:
                        parts = line.split()
                        if len(parts) > 2 and os.path.isdir(parts[2]):
                            mount_point_to_delete = parts[2]
                            print(f"Punto de montaje encontrado en el sistema (activo): {mount_point_to_delete}")
                            break
            except Exception as e:
                print(f"No se pudo verificar los montajes del sistema: {e}")

        # Si aún no se encontró, usar la ubicación por defecto (~/label) si existe la carpeta
        if not mount_point_to_delete:
            default_mount_path = os.path.expanduser(f"~/{account}")
            if os.path.isdir(default_mount_path):
                mount_point_to_delete = default_mount_path
                print(f"Punto de montaje por defecto encontrado: {mount_point_to_delete}")

        mensajes_confirm = [
            _("¿Seguro que quieres eliminar la cuenta '{account}'? ¡No hay marcha atrás en la montaña!").format(account=account),
            _("¿Eliminar '{account}'? ¡Que los dioses de la nube lo aprueban!").format(account=account),
            _("¿Vas a eliminar '{account}'? ¡Que no te tiemble el pulso!").format(account=account),
            _("Eliminar '{account}' es como borrar huellas en la nieve... ¿Estás seguro?").format(account=account),
            _("¿Estás listo para decirle adiós a '{account}'? ¡Despedidas en la cima!").format(account=account)
        ]

        if messagebox.askyesno(_("Confirmar"), random.choice(mensajes_confirm)):
            
            if account in self.main_app.mounted_accounts:
               
                active_mount_point = self.main_app.mounted_accounts[account]
                if os.path.ismount(active_mount_point): 
                    if not self.main_app.mount_mgr.unmount_account(account, active_mount_point):
                        messagebox.showwarning(_("Advertencia"), _("No se pudo desmontar la unidad. La carpeta de montaje podría estar en uso. Se intentará eliminar la carpeta de todas formas si confirmas."))
                else:
                    # Si está en mounted_accounts pero no realmente montado, eliminarlo de mounted_accounts
                    del self.main_app.mounted_accounts[account]
                    self.main_app._save_state() 

            # Confirmar eliminación física de ~/.gdfuse/<label>
            gdfuse_path = os.path.expanduser(f"~/.gdfuse/{account}")
            if os.path.isdir(gdfuse_path):
                confirm_fisico = messagebox.askyesno(
                    _("Eliminar del sistema"),
                    _(
                        "¿También quieres eliminar la configuración real de la cuenta en:\n{gdfuse_path}\n\n"
                        "Esto borrará los tokens y configuraciones de google-drive-ocamlfuse para esta cuenta.\n\n"
                        "¿Eliminar del sistema?"
                    ).format(gdfuse_path=gdfuse_path)
                )
                if confirm_fisico:
                    try:
                        shutil.rmtree(gdfuse_path)
                        print(f"Carpeta {gdfuse_path} eliminada del sistema.")
                    except Exception as e:
                        print(f"Error al eliminar carpeta {gdfuse_path}: {e}")
                        messagebox.showerror(_("Error"), _(f"No se pudo eliminar la carpeta:\n{gdfuse_path}\n\n{e}"))
                        return

            # Eliminar carpeta de montaje
            if mount_point_to_delete and os.path.isdir(mount_point_to_delete):
                if self.main_app.ask_before_delete:
                    dialog = tk.Toplevel(self.root)
                    dialog.title(_("Eliminar punto de montaje"))
                    dialog.geometry("400x200")
                    dialog.resizable(False, False)
                    dialog.withdraw()
                    from .utils import centrar_ventana
                    centrar_ventana(dialog, self.root)
                    dialog.deiconify()

                    msg = _(
                        "¿También quieres eliminar la carpeta de montaje local?\n{mount_point}\n\n"
                        "¡ADVERTENCIA! Esto eliminará la carpeta y TODO su contenido de forma permanente."
                    ).format(mount_point=mount_point_to_delete)
                    tk.Label(dialog, text=msg, wraplength=380).pack(pady=10)

                    var = tk.BooleanVar(value=True)
                    chk = tk.Checkbutton(dialog, text=_("No volver a preguntar"), variable=var)
                    chk.pack(pady=5)

                    result = {"delete": False}

                    def on_yes():
                        result["delete"] = True
                        if not var.get():
                            self.main_app.ask_before_delete = False
                            self.main_app._save_state()
                        dialog.destroy()

                    def on_no():
                        dialog.destroy()

                    btn_frame = tk.Frame(dialog)
                    btn_frame.pack(pady=10)
                    ttk.Button(btn_frame, text=_("Sí"), command=on_yes).pack(side=tk.LEFT, padx=10)
                    ttk.Button(btn_frame, text=_("No"), command=on_no).pack(side=tk.LEFT, padx=10)

                    dialog.transient(self.root)
                    dialog.grab_set()
                    self.root.wait_window(dialog)

                    confirm_mount_point_delete = result["delete"]
                else:
                    confirm_mount_point_delete = True

                if confirm_mount_point_delete:
                    try:
                        shutil.rmtree(mount_point_to_delete)
                        print(f"Carpeta de montaje {mount_point_to_delete} eliminada.")
                        if account in self.accounts and 'mount_point' in self.accounts[account]:
                            del self.accounts[account]['mount_point']
                    except Exception as e:
                        print(f"Error al eliminar la carpeta de montaje {mount_point_to_delete}: {e}")
                        messagebox.showerror(_("Error"), _("No se pudo eliminar la carpeta de montaje:\n{}\n\n{}").format(mount_point_to_delete, e))
            # mover a blacklist
            if account in self.accounts:
                cuenta = self.accounts[account]
                cuenta["blacklist"] = True
                self.deleted_accounts[account] = cuenta
                del self.accounts[account]
                self.save_config()
                self.main_app.accounts = self.accounts
                self.main_app.deleted_accounts = self.deleted_accounts
                self.refresh_accounts_ui()
                mensajes_exito = [
                _("¡Cuenta '{account}' eliminada! Ahora hay más espacio en la nube").format(account=account),
                _("'{account}' ha sido eliminada. ¡Desapareció como un copo de nieve al sol!").format(account=account),
                _("¡Listo! '{account}' ya no está entre nosotros.").format(account=account),
                _("La cuenta '{account}' fue eliminada con éxito. ¡Hasta la vista, baby!").format(account=account),
                _("¡Puf! '{account}' se ha ido. ¡Así de fácil!").format(account=account)
                ]
                messagebox.showinfo(_("Éxito"), random.choice(mensajes_exito))
    
    

    def restore_account(self):
        """Permite restaurar una cuenta eliminada"""
        if not self.deleted_accounts:
            messagebox.showinfo(_("Restaurar cuenta"), _( "No hay cuentas eliminadas para restaurar."))
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(_("Restaurar Cuenta Eliminada"))
        dialog.geometry("350x280")
        dialog.resizable(False, False)
        tk.Label(dialog, text=_("Selecciona la cuenta a restaurar:")).pack(pady=12)
        dialog.withdraw()
        centrar_ventana(dialog, self.root)
        dialog.deiconify()

        
        tree = ttk.Treeview(dialog, columns=("cuenta",), show="", height=8)
        tree.column("cuenta", anchor="center")
        tree.heading("cuenta", text=_("Cuenta"))
        
        deleted_names = list(self.deleted_accounts.keys())
        for name in deleted_names:
            tree.insert("", tk.END, values=(name,), iid=name)
        tree.pack(padx=16, pady=8, fill=tk.BOTH, expand=True)

        selected_account = {"value": None}

        def on_restore():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(_("Advertencia"), _( "Selecciona una cuenta para restaurar"), parent=dialog)
                return
            selected_account["value"] = selection[0]
            dialog.destroy()
        def on_delete_forever():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning(_("Advertencia"), _("Selecciona una cuenta para eliminar"), parent=dialog)
                return
            account = selection[0]
            if messagebox.askyesno(
                _("Eliminar definitivamente"),
                _("¿Eliminar '{account}' de la lista de restaurables de forma permanente?\n\nEsta acción no se puede deshacer.").format(account=account),
                parent=dialog
            ):
                del self.deleted_accounts[account]
                self.save_config()
                tree.delete(selection[0])
                if not tree.get_children():
                    dialog.destroy()
                messagebox.showinfo(
                    _("Eliminada"),
                    _("La cuenta '{account}' fue eliminada definitivamente.").format(account=account)

                )
                self.refresh_accounts()
                self.main_app._update_accounts_tab_button_states()
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=(8, 16))
        ttk.Button(btn_frame, text=_("Restaurar"), command=on_restore).pack(side=tk.LEFT, padx=8, ipadx=10, ipady=4)
        ttk.Button(btn_frame, text=_("Eliminar definitivamente"), command=on_delete_forever).pack(side=tk.LEFT, padx=8, ipadx=10, ipady=4)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

        account = selected_account["value"]
        if not account:
            return
        
        restored_partially = False
       
        gdfuse_path = os.path.expanduser(f"~/.gdfuse/{account}")
        if not os.path.isdir(gdfuse_path):
            respuesta = messagebox.askyesnocancel(
                _( "Carpeta de configuración no encontrada"),
                _(
                    "La carpeta real de configuración para '{account}' no existe en:\n{gdfuse_path}\n\n"
                    "¿Deseas reconfigurar la cuenta ahora (recomendado)?\n"
                    "Si eliges 'No', solo se restaurará la configuración interna, pero no podrás montar la cuenta hasta reconfigurarla.\n"
                    "Podrás usar el botón 'Reautorizar' para completar la configuración más adelante."
                ).format(account=account, gdfuse_path=gdfuse_path),
                icon=messagebox.QUESTION,
                parent=self.root
            )
            if respuesta is None:
                self.main_app.limpiar_campos_credenciales()
                return
            elif respuesta:
                cuenta = self.deleted_accounts[account]
                self.main_app.label_entry.delete(0, tk.END)
                self.main_app.client_id_entry.delete(0, tk.END)
                self.main_app.client_secret_entry.delete(0, tk.END)
                self.main_app.label_entry.insert(0, account)
                self.main_app.client_id_entry.insert(0, cuenta.get("client_id", ""))
                try:
                    decrypted_secret = self.encryption_manager.decrypt(self._ensure_encrypted(cuenta.get("client_secret", "")))
                    self.main_app.client_secret_entry.insert(0, decrypted_secret)
                except Exception as e:
                    messagebox.showerror(_("Error de Cifrado"), _("No se pudo descifrar el client_secret para la restauración."))
                    self.main_app.client_secret_entry.insert(0, "")
                messagebox.showinfo(
                    _( "Reconfigurar cuenta"),
                    _( "Se han precargado los datos de la cuenta. Completa el flujo de configuración OAuth para restaurar completamente la cuenta."),
                    parent=self.root
                )
                success, email, error = self.setup_account_logic(
                    account, cuenta.get("client_id", ""), cuenta.get("client_secret", ""), threading.Event()
                )

                if success:
                    if account in self.deleted_accounts:
                        del self.deleted_accounts[account]
                    self.save_config()
                    self.refresh_accounts_ui()
                    self.main_app.root.update_idletasks()
                    messagebox.showinfo(
                        _( "Restaurada"),
                        _( "La cuenta '{account}' ha sido restaurada completamente.").format(account=account)
                    ) 
                    self.refresh_accounts()
                    self.main_app.limpiar_campos_credenciales()
                    return
                else:
                    error_messages = {
                        "server_error": _("No se pudo iniciar el servidor OAuth"),
                        "cancelled": _("Restauración cancelada por el usuario."),
                        "user_cancel": _("Restauración cancelada por el usuario."),
                        "timeout": _("No se recibió el código de autorización a tiempo"),
                        "oauth_error": _("Error al completar la restauración OAuth"),
                        "duplicate_email": _("Ya existe una cuenta configurada con el correo '{email}'."),
                    }
                    messagebox.showwarning(
                        _( "Restauración incompleta"),
                        error_messages.get(error, _( "La cuenta no fue reconfigurada completamente. Sigue en la lista de eliminadas.")),
                        parent=self.root
                    )
                    self.main_app.limpiar_campos_credenciales()
                return
            else:
                self.deleted_accounts[account]["configured"] = False
                self.deleted_accounts[account].pop("externally_detected", None)
                messagebox.showwarning(
                    _( "Restauración parcial"),
                    _( "La cuenta se restaurará solo en la configuración interna, pero no podrá montarse hasta que la reautorices.\n\n"
                      "Puedes usar el botón 'Reautorizar' cuando lo desees."),
                    parent=self.root
                )
                restored_partially = True
                self.main_app._update_accounts_tab_button_states()
        
        client_id_restaurar = self.deleted_accounts[account].get("client_id", "").strip().lower()
        for acc in self.accounts.values():
            if acc.get("client_id", "").strip().lower() == client_id_restaurar:
                messagebox.showerror(
                    _("Error"),
                    _(
                        "Ya existe una cuenta activa con el mismo Client ID.\n"
                        "No puedes restaurar '{account}' mientras exista otra cuenta con el mismo Client ID."
                    ).format(account=account)
                )
                return
        
        # Eliminar claves conflictivas para evitar TypeError
        extra = {k: v for k, v in self.deleted_accounts[account].items() if k not in ["client_id", "client_secret", "blacklist", "configured", "externally_detected"]}
        self.accounts[account] = self._account_to_dict(
            account,
            self.deleted_accounts[account].get("client_id", ""),
            self.deleted_accounts[account].get("client_secret", ""),
            **extra,
            externally_detected=False, 
            configured=False
        )
        if "blacklist" in self.accounts[account]:
            del self.accounts[account]["blacklist"]
        del self.deleted_accounts[account]
        self.save_config()
        self.main_app.accounts = self.accounts
        self.main_app.deleted_accounts = self.deleted_accounts
        self.refresh_accounts_ui()
        self.main_app._update_accounts_tab_button_states()
        
        if not restored_partially:
            messagebox.showinfo(
                _( "Restaurada"),
                _( "La cuenta '{account}' ha sido restaurada completamente.").format(account=account)
            )  
    def cargar_credenciales_json(self):
        """Carga credenciales desde un archivo JSON y bloquea los campos, usando el gestor de archivos nativo si es posible."""
        carpeta = os.path.expanduser("~")
        file_path = ""
        
        # Estrategia: Probar Zenity, luego KDialog, y finalmente Tkinter.
        # Si el usuario cancela un diálogo (código de salida 1), no se intenta el siguiente.

        # Intento 1: Zenity (GTK)
        try:
            result = subprocess.run([
                'zenity', '--file-selection',
                '--title=Seleccionar archivo de credenciales JSON',
                '--file-filter=Archivos JSON | *.json',
                f'--filename={carpeta}/'
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                file_path = result.stdout.strip()
            elif result.returncode == 1:
                # El usuario canceló el diálogo de Zenity, no hacer nada más.
                return
            # Para otros códigos de error, se considera un fallo y se pasará al siguiente método.

        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Zenity no está instalado o no respondió, intentar con kdialog.
            pass

        # Intento 2: KDialog (KDE)
        if not file_path:
            try:
                # KDialog devuelve la ruta por stdout y código 0, o nada y código 1 si se cancela.
                result = subprocess.run([
                    'kdialog', '--getopenfilename',
                    carpeta,
                    'Archivos JSON (*.json)'
                ], capture_output=True, text=True, timeout=60)

                if result.returncode == 0:
                    file_path = result.stdout.strip()
                elif result.returncode == 1:
                    # El usuario canceló el diálogo de KDialog, no hacer nada más.
                    return

            except (FileNotFoundError, subprocess.TimeoutExpired):
                # Kdialog no está o no respondió, usar el de tkinter.
                pass

        # Fallback: Tkinter
        if not file_path:
            # askopenfilename devuelve una cadena vacía si el usuario cancela.
            file_path = filedialog.askopenfilename(
                title=_("Seleccionar archivo de credenciales JSON"),
                filetypes=[(_("Archivos JSON"), '*.json')],
                initialdir=carpeta
            )

        if not file_path:
            return

        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            
            cred = data.get("web") or data.get("installed") or {}
            client_id = cred.get("client_id", "")
            client_secret = cred.get("client_secret", "")

            if client_id and client_secret:
              
                self.main_app.client_id_entry.config(state="normal")
                self.main_app.client_secret_entry.config(state="normal")
                self.main_app.client_id_entry.delete(0, tk.END)
                self.main_app.client_id_entry.insert(0, client_id)
                self.main_app.client_secret_entry.delete(0, tk.END)
                self.main_app.client_secret_entry.insert(0, client_secret)
                
               
                self.main_app._update_credential_fields_state(locked=True)
                messagebox.showinfo(_("Éxito"), _("Credenciales cargadas correctamente"))
            else:
                messagebox.showerror(_("Error"), _("El archivo JSON no contiene client_id o client_secret válidos."))
        except Exception as e:
            messagebox.showerror(_("Error"), _("No se pudo leer el archivo:\n{e}").format(e=e))    
   
    def mostrar_guia_oauth(self):
        """Muestra una guía paso a paso para crear credenciales OAuth 2.0 en Google Cloud Console"""
        guia = _(
            "Guía para crear credenciales OAuth 2.0 (Aplicación web o Aplicación de escritorio):\n\n"
            "1. Ve a {credentials_url}\n"
            "2. Haz clic en 'Crear credenciales' > 'ID de cliente de OAuth'\n"
            "3. Selecciona 'Aplicación web' o 'Aplicación de escritorio' como tipo de aplicación.\n"
            "   - Si eliges 'Aplicación de escritorio', Google ya permite usar el flujo de redirección a localhost.\n"
            "4. Ponle un nombre (ejemplo: EasyOcamlfuse).\n"
            "5. En 'URIs de redireccionamiento autorizados' agrega:\n"
            "    {redirect_uri}\n"
            "6. Haz clic en 'Crear'\n"
            "7. Descarga el archivo JSON y usa el botón 'Cargar credenciales JSON' aquí.\n"
            "8. Si lo prefieres, copia el Client ID y Client Secret manualmente.\n\n"
            "Más información oficial:\n"
            "{official_docs}"
        ).format(
            credentials_url="https://console.cloud.google.com/apis/credentials",
            redirect_uri="http://localhost:8080",
            official_docs="https://github.com/astrada/google-drive-ocamlfuse#authentication"
        )

        url = "https://console.cloud.google.com/apis/credentials"
        top = tk.Toplevel(self.root)
        top.title(_("Guía para crear credenciales OAuth 2.0"))
        top.geometry("500x550")
        top.attributes("-topmost", True)
        top.withdraw()
        from .utils import centrar_ventana
        centrar_ventana(top, self.root)
        top.deiconify()

        # Menú de edición
        menubar = tk.Menu(top)
        editmenu = tk.Menu(menubar, tearoff=0)
        
        def copiar():
            try:
                sel = txt.selection_get()
                top.clipboard_clear()
                top.clipboard_append(sel)
                estado_label.config(text=_("Texto copiado al portapapeles"))
            except tk.TclError:
                pass
        
        editmenu.add_command(label=_("Copiar"), command=copiar)
        menubar.add_cascade(label=_("Edición"), menu=editmenu)
        top.config(menu=menubar)

        txt = tk.Text(top, wrap="word", font=("Arial", 10), cursor="arrow")
        txt.insert("1.0", guia)
        txt.config(state="disabled")
        txt.pack(expand=True, fill="both", padx=10, pady=10)

        # Hacer la URL de Google Cloud clickeable
        txt.config(state="normal")
        start_idx = txt.search(url, "1.0", tk.END)
        if start_idx:
            end_idx = f"{start_idx}+{len(url)}c"
            txt.tag_add("url", start_idx, end_idx)
            txt.tag_config("url", foreground="blue", underline=1)
            
            def abrir_url(event):
                webbrowser.open(url)
            
            txt.tag_bind("url", "<Button-1>", abrir_url)
        
        txt.config(state="disabled")

       
        estado_label = ttk.Label(top, text="", anchor="w", foreground="green")
        estado_label.pack(fill="x", padx=10, pady=(0, 8), side="bottom")

     
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

        btn = ttk.Button(top, text=_("Abrir Google Cloud Console"), command=lambda: webbrowser.open(url))
        btn.pack(pady=8)

    def get_email_from_token(self, access_token):
        """Obtiene el correo del usuario autenticado usando el token de acceso."""
        try:
            resp = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if resp.status_code == 200:
                return resp.json().get("email", "")
            else:
                print("Error al obtener email:", resp.text)
                return ""
        except Exception as e:
            print("Error al obtener email:", e)
            return ""

    def setup_account_logic(self, label, client_id, client_secret, cancel_event, timeout=120):
        from . import oauth
        # nos aseguramos de que el client_secret esté descifrado antes de usarlo
        try:
            client_secret_plain = self.encryption_manager.decrypt(client_secret)
        except Exception:
            client_secret_plain = client_secret
        auth_code, error = oauth.authenticate(client_id, client_secret_plain, OAUTH_PORT, cancel_event, timeout)
        if error:
            return False, None, error
        redirect_url = f"http://localhost:{OAUTH_PORT}"
        success, email = self.complete_oauth_setup(label, client_id, client_secret_plain, redirect_url, auth_code)
        if not success:
            return False, None, "oauth_error"
        for acc in self.accounts.values():
            if acc.get("email") == email and email:
                return False, email, "duplicate_email"
        self.accounts[label] = self._account_to_dict(
            label, client_id, client_secret, redirect_url=redirect_url, configured=True, externally_detected=False, email=email
        )
        self.save_config()
        return True, email, None

    def _ensure_encrypted(self, client_secret):
        """Asegura que el client_secret esté cifrado. Si ya lo está, lo retorna tal cual."""
        try:
            # Si descifrar no lanza excepción, ya está cifrado
            self.encryption_manager.decrypt(client_secret)
            return client_secret
        except Exception:
            # Si falla, significa que no está cifrado, así que lo ciframos
            return self.encryption_manager.encrypt(client_secret)

    def _account_to_dict(self, label, client_id, client_secret, **kwargs):
        """Devuelve el dict de cuenta, cifrando el client_secret si es necesario."""
        return {
            "client_id": client_id,
            "client_secret": self._ensure_encrypted(client_secret),
            **kwargs
        }

    def _dict_to_account(self, data):
        """Devuelve los datos de cuenta con el client_secret descifrado solo en memoria."""
        return {
            **data,
            "client_secret": self.encryption_manager.decrypt(data["client_secret"])
        }
