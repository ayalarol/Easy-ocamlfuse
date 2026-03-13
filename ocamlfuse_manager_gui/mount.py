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
import subprocess
from tkinter import messagebox
import threading
import time
from .i18n import i18n_instance
_ = i18n_instance.gettext

UNKNOWN_LABEL = "__UNKNOWN__"

class MountManager:
    def __init__(self, mounted_accounts_ref):
        self.mounted_accounts = mounted_accounts_ref
        self._internal_unmounting = set() # Etiquetas que se están desmontando internamente

    def mount_account(self, label, mount_point):
        """Montar una cuenta específica con verificaciones de seguridad"""
        try:
            # Si el directorio no existe, crearlo
            if not os.path.exists(mount_point):
                os.makedirs(mount_point, exist_ok=True)
            
            # Verificar si ya está montado algo ahí
            if os.path.ismount(mount_point):
                # Si ya está montado, comprobamos si es nuestra cuenta
                self.refresh_mounts()
                if label in self.mounted_accounts and self.mounted_accounts[label] == mount_point:
                    messagebox.showinfo(_("Info"), _("La cuenta '{}' ya está montada en {}").format(label, mount_point))
                    return True
                else:
                    messagebox.showwarning(_("Aviso"), _("El punto de montaje {} ya está en uso por otro proceso.").format(mount_point))
                    return False

            # --- Obtener client_secret desencriptado si es necesario ---
            if hasattr(self, 'main_app') and hasattr(self.main_app, 'accounts'):
                account_data = self.main_app.accounts.get(label)
                if account_data:
                    from .encryption import EncryptionManager
                    enc_mgr = EncryptionManager()
                    try:
                        client_secret = enc_mgr.decrypt(account_data['client_secret'])
                    except Exception:
                        client_secret = account_data['client_secret']

            mount_cmd = ["google-drive-ocamlfuse", "-label", label, mount_point]
            # Ejecutamos el montaje
            result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=45)

            if result.returncode == 0:
                self.mounted_accounts[label] = mount_point
                
                # --- ACTUALIZAR ESTADO EN LA GUI ---
                if hasattr(self, 'main_app'):
                    if hasattr(self.main_app, 'mounted_accounts'):
                        self.main_app.mounted_accounts[label] = mount_point
                    
                    if hasattr(self.main_app, 'accounts') and label in self.main_app.accounts:
                        self.main_app.accounts[label]['mount_point'] = mount_point
                    
                    if hasattr(self.main_app, '_save_state'):
                        self.main_app._save_state()
                    
                    # Forzar refresco de la UI si existe el método
                    if hasattr(self.main_app, 'refresh_accounts_ui'):
                        self.main_app.refresh_accounts_ui()

                messagebox.showinfo(_("Éxito"), _("Cuenta '{}' montada en {}").format(label, mount_point))
                return True
            else:
                # Si falla porque el punto de montaje está "sucio" (transporte no conectado, etc)
                error_msg = result.stderr.lower()
                if "transport endpoint is not connected" in error_msg or "device or resource busy" in error_msg:
                    # Intentar un desmontaje forzado y reintentar una vez
                    subprocess.run(["fusermount", "-uz", mount_point], capture_output=True)
                    time.sleep(1)
                    result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        self.mounted_accounts[label] = mount_point
                        return True
                
                messagebox.showerror(_("Error"), _("Error al montar '{}':\n{}").format(label, result.stderr))
                return False
        except subprocess.TimeoutExpired:
            messagebox.showerror(_("Error"), _( "Timeout al montar la cuenta"))
            return False
        except Exception as e:
            messagebox.showerror(_("Error"), _("Error inesperado: {}").format(str(e)))
            return False

    def unmount_account(self, account, mount_point):
        """Desmontar una cuenta específica con verificación previa"""
        # Si ya no está montado (desmontaje externo previo), limpiar y salir
        if not os.path.exists(mount_point) or not os.path.ismount(mount_point):
            if account in self.mounted_accounts:
                del self.mounted_accounts[account]
            self._internal_unmounting.discard(account)
            # Refrescar UI si es posible
            if hasattr(self, 'main_app') and hasattr(self.main_app, 'refresh_mounts'):
                self.main_app.refresh_mounts()
            return True

        self._internal_unmounting.add(account)
        try:
            unmount_cmd = ["fusermount", "-u", mount_point]
            # Usamos subprocess.run para capturar el stderr
            result = subprocess.run(unmount_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                if account in self.mounted_accounts:
                    del self.mounted_accounts[account]
                # Damos un pequeño margen para que el monitor registre el cambio
                time.sleep(0.3)
                return True
            else:
                # Si el error es que no se encontró en mtab, lo tratamos como éxito (ya se desmontó)
                if "not found in /etc/mtab" in result.stderr or "no se encuentra en /etc/mtab" in result.stderr:
                    if account in self.mounted_accounts:
                        del self.mounted_accounts[account]
                    return True
                
                self._internal_unmounting.discard(account)
                messagebox.showerror(
                    _( "Error al desmontar"),
                    _("No se pudo desmontar '{}' en '{}':\nAsegúrate de que ningún archivo esté usando la carpeta.\n\nDetalle: {}").format(account, mount_point, result.stderr.strip())
                )
                return False
        except Exception as e:
            self._internal_unmounting.discard(account)
            messagebox.showerror(
                _( "Error al desmontar"),
                _("Error inesperado: {}").format(str(e))
            )
            return False

    def unmount_all(self):
        """Desmontar todas las cuentas y actualizar tabla"""
        if not self.mounted_accounts:
            messagebox.showinfo(_("Info"), _( "No hay cuentas montadas"))
            return

        if messagebox.askyesno(_("Confirmar"), _( "¿Desmontar todas las cuentas?")):
            errores = []
            for account, mount_point in list(self.mounted_accounts.items()):
                ok = self.unmount_account(account, mount_point)
                if not ok:
                    errores.append(account)
            
            if errores:
                messagebox.showwarning(
                    _( "Algunas cuentas no se desmontaron"),
                    _("No se pudieron desmontar las siguientes cuentas:\n{}\nVerifica que no estén en uso.").format(', '.join(errores))
                )
            else:
                messagebox.showinfo(_("Éxito"), _( "Todas las cuentas fueron desmontadas correctamente."))

    def refresh_mounts(self):
        """Actualizar lista de montajes sin duplicados"""
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
                        
                        label = self.get_label_from_mount_point(mount_point)
                        if label == _( "Desconocido"):
                            device = parts[0]
                            if '@' in device and 'google-drive-ocamlfuse' in device:
                                label = device.split('@')[0]
                            else:
                                label = UNKNOWN_LABEL
                        active_mounts[mount_point] = label
        except Exception as e:
            print(_("Error al refrescar montajes: {}").format(e))
        
        for account, mount_point in list(self.mounted_accounts.items()):
            if mount_point not in seen_mount_points:
                try:
                    if os.path.ismount(mount_point):
                        seen_mount_points.add(mount_point)
                        active_mounts[mount_point] = account
                except Exception as e:
                    print(_("Error comprobando punto de montaje {}: {}").format(mount_point, e))
            elif mount_point in active_mounts and active_mounts[mount_point] == UNKNOWN_LABEL:
                active_mounts[mount_point] = account
        
        self.mounted_accounts = {}
        for mount_point, label in active_mounts.items():
            self.mounted_accounts[label] = mount_point
        
        return self.mounted_accounts

    def automount_accounts(self, accounts):
        """Montar automáticamente las cuentas marcadas como 'automount' al iniciar"""
        from .encryption import EncryptionManager
        enc_mgr = EncryptionManager()
        for label, data in accounts.items():
            if data.get("automount", False):
                mount_point = data.get('mount_point')
                if not mount_point:
                    mount_point = os.path.expanduser(f"~/{label}")
                    os.makedirs(mount_point, exist_ok=True)
                    data['mount_point'] = mount_point
                if label not in self.mounted_accounts or not os.path.ismount(mount_point):
                    try:
                        # Desencriptar client_secret si es necesario (por si se usa en el futuro)
                        try:
                            client_secret = enc_mgr.decrypt(data['client_secret'])
                        except Exception:
                            client_secret = data['client_secret']
                        mount_cmd = ["google-drive-ocamlfuse", "-label", label, mount_point]
                        result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)
                        if result.returncode == 0:
                            self.mounted_accounts[label] = mount_point
                        else:
                            print(_("Error al montar '{}': {}").format(label, result.stderr))
                    except Exception as e:
                        print(_("Error al montar '{}': {}").format(label, e))

    def get_label_from_mount_point(self, mount_point):
        """Intentar obtener etiqueta real para un punto de montaje"""
        try:
            # Buscar en la configuración de google-drive-ocamlfuse
            config_path = os.path.expanduser("~/.gdfuse")
            if os.path.exists(config_path):
                for label in os.listdir(config_path):
                    config_file = os.path.join(config_path, label, "config")
                    if os.path.isfile(config_file):
                        with open(config_file, 'r') as f:
                            for line in f:
                                if line.startswith("mount_point="):
                                    config_mount = line.split('=')[1].strip()
                                    if config_mount == mount_point:
                                        return label
        except Exception as e:
            print(_("Error obteniendo etiqueta: {}").format(e))
        return UNKNOWN_LABEL

    def start_mount_monitor(self, interval=2, on_unmount_callback=None):
        """
        Inicia un hilo que monitorea los puntos de montaje. Si detecta un desmontaje,
        llama al callback y termina su ciclo para que la GUI actualice el estado.
        """
        if hasattr(self, '_monitoring') and self._monitoring:
            return

        self._monitoring = True
        self._already_encrypted = set() 
        
        # --- Pre-encriptar cuentas al inicio del monitor una sola vez ---
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'accounts'):
            from .encryption import EncryptionManager
            enc_mgr = EncryptionManager()
            for label, data in self.main_app.accounts.items():
                client_id = data.get('client_id')
                if client_id:
                    client_secret = data.get('client_secret')
                    try:
                        enc_mgr.decrypt(client_secret)
                        self._already_encrypted.add(client_id)
                    except Exception:
                        encrypted = enc_mgr.encrypt(client_secret)
                        data['client_secret'] = encrypted
                        self._already_encrypted.add(client_id)
            if hasattr(self.main_app, '_save_state'):
                self.main_app._save_state()

        def monitor():
            while self._monitoring:
                time.sleep(interval)

                if not self.mounted_accounts:
                    continue

                accounts_snapshot = list(self.mounted_accounts.items())
                unmounted_labels = []

                for label, mount_point in accounts_snapshot:
                    try:
                        if not os.path.ismount(mount_point):
                            # Si no está montado, comprobamos si fue un desmontaje interno
                            if label in self._internal_unmounting:
                                # Es interno, lo eliminamos de la lista sin notificar
                                self._internal_unmounting.discard(label)
                                if label in self.mounted_accounts:
                                    del self.mounted_accounts[label]
                                continue
                            
                            unmounted_labels.append((label, mount_point))
                    except Exception as e:
                        print(_("Error in mount monitor while checking '{}': {}").format(label, e))

                if unmounted_labels:
                    for label, mount_point in unmounted_labels:
                        if label in self.mounted_accounts:
                            del self.mounted_accounts[label]
                        
                        if on_unmount_callback:
                            on_unmount_callback(label, mount_point)
        
        threading.Thread(target=monitor, daemon=True).start()

    def stop_mount_monitor(self):
        self._monitoring = False
