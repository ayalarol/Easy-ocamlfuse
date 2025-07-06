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

    def mount_account(self, label, mount_point):
        """Montar una cuenta específica"""
        os.makedirs(mount_point, exist_ok=True)
        try:
            mount_cmd = ["google-drive-ocamlfuse", "-label", label, mount_point]
            result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                self.mounted_accounts[label] = mount_point
                # --- GUARDAR EN LA CONFIGURACIÓN GLOBAL ---
                if hasattr(self, 'main_app') and hasattr(self.main_app, 'accounts'):
                    self.main_app.accounts[label]['mount_point'] = mount_point
                    self.main_app._save_state()
                elif hasattr(self, 'accounts'):
                    self.accounts[label]['mount_point'] = mount_point
                    if hasattr(self, '_save_state'):
                        self._save_state()
                messagebox.showinfo(_("Éxito"), _(f"Cuenta '{label}' montada en {mount_point}"))
                return True
            else:
                messagebox.showerror(_("Error"), _(f"Error al montar:\n{result.stderr}"))
                return False
        except subprocess.TimeoutExpired:
            messagebox.showerror(_("Error"), _( "Timeout al montar la cuenta"))
            return False
        except Exception as e:
            messagebox.showerror(_("Error"), _(f"Error inesperado: {str(e)}"))
            return False

    def unmount_account(self, account, mount_point):
        """Desmontar una cuenta específica con manejo de errores claro"""
        try:
            unmount_cmd = ["fusermount", "-u", mount_point]
            subprocess.check_call(unmount_cmd)
            return True
        except subprocess.CalledProcessError as e:
            messagebox.showerror(
                _( "Error al desmontar"),
                _(f"No se pudo desmontar '{account}' en '{mount_point}':\n"
                  "Asegúrate de que ningún archivo, terminal o ventana esté usando la carpeta de montaje.\n\n"
                  f"Detalle: {e}")
            )
            print(_(f"Error al desmontar {account} en {mount_point}: {e}"))
            return False
        except Exception as e:
            messagebox.showerror(
                _( "Error al desmontar"),
                _(f"Error inesperado al desmontar '{account}' en '{mount_point}':\n{e}")
            )
            print(_(f"Error al desmontar {account} en {mount_point}: {e}"))
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
                    _(f"No se pudieron desmontar las siguientes cuentas:\n{', '.join(errores)}\n"
                      "Verifica que no estén en uso.")
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
            print(_(f"Error al refrescar montajes: {e}"))
        
        for account, mount_point in list(self.mounted_accounts.items()):
            if mount_point not in seen_mount_points:
                try:
                    if os.path.ismount(mount_point):
                        seen_mount_points.add(mount_point)
                        active_mounts[mount_point] = account
                except Exception as e:
                    print(_(f"Error comprobando punto de montaje {mount_point}: {e}"))
            elif mount_point in active_mounts and active_mounts[mount_point] == UNKNOWN_LABEL:
                active_mounts[mount_point] = account
        
        self.mounted_accounts = {}
        for mount_point, label in active_mounts.items():
            self.mounted_accounts[label] = mount_point
        
        return self.mounted_accounts

    def automount_accounts(self, accounts):
        """Montar automáticamente las cuentas marcadas como 'automount' al iniciar la app."""
        for label, data in accounts.items():
            if data.get("automount", False):
                # Verifica si ya está montada
                mount_point = data.get('mount_point')
                if not mount_point:
                    mount_point = os.path.expanduser(f"~/{label}")
                    os.makedirs(mount_point, exist_ok=True)
                    data['mount_point'] = mount_point
                
                if label not in self.mounted_accounts or not os.path.ismount(mount_point):
                    try:
                        mount_cmd = ["google-drive-ocamlfuse", "-label", label, mount_point]
                        result = subprocess.run(mount_cmd, capture_output=True, text=True, timeout=30)
                        if result.returncode == 0:
                            self.mounted_accounts[label] = mount_point
                        else:
                            print(_(f"Error al montar '{label}': {result.stderr}"))
                    except Exception as e:
                        print(_(f"Error al montar '{label}': {e}"))

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
            print(_(f"Error obteniendo etiqueta: {e}"))
        return UNKNOWN_LABEL

    def start_mount_monitor(self, interval=5, on_unmount_callback=None):
        """
        Inicia un hilo que monitorea los puntos de montaje. Si detecta un desmontaje,
        llama al callback y termina su ciclo para que la GUI actualice el estado.
        """
        if hasattr(self, '_monitoring') and self._monitoring:
            return

        self._monitoring = True

        def monitor():
            while self._monitoring:
                time.sleep(interval)
                
                if not self.mounted_accounts:
                    continue

                accounts_snapshot = list(self.mounted_accounts.items())

                for label, mount_point in accounts_snapshot:
                    try:
                        if not os.path.ismount(mount_point):
                            if label in self.mounted_accounts:
                                if on_unmount_callback:
                                    on_unmount_callback(label, mount_point)
                                break
                    except Exception as e:
                        # En una aplicación real, esto debería ir a un archivo de log
                        print(_(f"Error in mount monitor while checking '{label}': {e}"))
        
        threading.Thread(target=monitor, daemon=True).start()

    def stop_mount_monitor(self):
        """Detiene el hilo de monitoreo."""
        self._monitoring = False
