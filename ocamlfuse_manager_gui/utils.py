import tkinter as tk
import subprocess
import os
import threading
import requests
from ocamlfuse_manager_gui.constants import APP_VERSION
from .i18n import i18n_instance
_ = i18n_instance.gettext

def check_for_updates():
    """
    Checks for a new release of the application on GitHub.

    Returns:
        A dictionary with update information if a new version is available, otherwise None.
    """
    try:
        response = requests.get("https://api.github.com/repos/ayalarol/Easy-ocamlfuse/releases/latest")
        response.raise_for_status()
        latest_release = response.json()
        latest_version = latest_release.get("tag_name")

        # Simple version comparison
        if latest_version and latest_version.lstrip('v') > APP_VERSION:
            return {
                "version": latest_version,
                "url": latest_release.get("html_url"),
                "notes": latest_release.get("body")
            }
    except requests.RequestException as e:
        print(f"Error checking for updates: {e}")
    return None

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, _, cy = self.widget.bbox("insert") if hasattr(self.widget, "bbox") else (0, 0, 0, 0)
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "9", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

def centrar_ventana(ventana, respecto_a=None):
    # Asegurarse de que la ventana esté completamente dibujada y sus dimensiones sean finales
    ventana.update_idletasks()
    # Establecer una posición temporal para forzar al gestor de ventanas a "realizar" la ventana
    # Esto es crucial para obtener dimensiones correctas, especialmente en Linux/GTK
    ventana.geometry("+0+0")
    ventana.update_idletasks() # Forzar otra actualización después de la posición temporal

    if respecto_a:
        ventana.transient(respecto_a)
        ventana.update_idletasks() # Forzar actualización después de transient

    ancho = ventana.winfo_width()
    alto = ventana.winfo_height()

    # Calcular la posición para centrar la ventana
    if respecto_a:
        # Centrar con respecto a la ventana padre
        x_base = respecto_a.winfo_rootx()
        y_base = respecto_a.winfo_rooty()
        ancho_base = respecto_a.winfo_width()
        alto_base = respecto_a.winfo_height()
        x = x_base + (ancho_base // 2) - (ancho // 2)
        y = y_base + (alto_base // 2) - (alto // 2)
    else:
        # Centrar con respecto a la pantalla
        pantalla_ancho = ventana.winfo_screenwidth()
        pantalla_alto = ventana.winfo_screenheight()
        x = (pantalla_ancho // 2) - (ancho // 2)
        y = (pantalla_alto // 2) - (alto // 2)

    # Aplicar la nueva posición
    ventana.geometry(f"+{x}+{y}")

def verificar_ocamlfuse():
    """Devuelve (estado, mensaje, color) según la instalación de google-drive-ocamlfuse."""
    try:
        result = subprocess.run(['google-drive-ocamlfuse', "-version"],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, _("✓ google-drive-ocamlfuse instalado correctamente"), "green"
        else:
            return False, _("✗ Error al verificar google-drive-ocamlfuse"), "orange"
    except FileNotFoundError:
        return False, _("✗ google-drive-ocamlfuse no está instalado"), "red"
    except subprocess.TimeoutExpired:
        return False, _("✗ Timeout al verificar instalación"), "red"

def detectar_distro_id():
    """Detecta la distribución de Linux."""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=")[1].strip().replace('"', '')
    except Exception:
        pass
    return "unknown"

def obtener_comando_instalacion_ocamlfuse(distro_id, ppa_choice="normal"):
    """Devuelve el comando de instalación adecuado para la distro."""
    if distro_id in ["ubuntu", "debian", "linuxmint", "pop"]:
        if ppa_choice == "normal":
            ppa = "ppa:alessandro-strada/ppa"
        else:
            ppa = "ppa:alessandro-strada/google-drive-ocamlfuse-beta"
        return (
            "apt update && "
            "apt install -y software-properties-common apt-transport-https && "
            f"add-apt-repository {ppa} -y && "
            "apt update && "
            "apt install -y google-drive-ocamlfuse"
        )
    elif distro_id in ["arch", "manjaro", "endeavouros"]:
        return "pacman -Sy --noconfirm google-drive-ocamlfuse"
    elif distro_id in ["fedora", "centos", "rhel"]:
        return "dnf install -y google-drive-ocamlfuse"
    elif distro_id in ["opensuse", "sles"]:
        return "zypper install -y google-drive-ocamlfuse"
    else:
        return None

def ejecutar_instalacion_ocamlfuse(install_cmd, output_callback=None, status_callback=None):
    """
    Ejecuta el comando de instalación de ocamlfuse con permisos de administrador.
    Llama a output_callback(line) por cada línea de salida.
    Llama a status_callback(text) para actualizar el estado.
    Devuelve el código de retorno del proceso.
    """
    try:
        full_cmd = f"pkexec sh -c '{install_cmd}'"
        if status_callback:
            status_callback(_("Solicitando permisos..."))
        if output_callback:
            output_callback(_("> Solicitando permisos de administrador...\n"))

        process = subprocess.Popen(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        if status_callback:
            status_callback(_("Instalando..."))
        if output_callback:
            output_callback(_("> Ejecutando: ") + install_cmd + "\n")

        # Leer salida en tiempo real
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if output_callback:
                output_callback(line)

        process.wait()
        return process.returncode
    except Exception as e:
        if output_callback:
            output_callback(_("\n✗ Error inesperado: ") + str(e) + "\n")
        return -1

def instalar_ocamlfuse_async(install_cmd, output_callback=None, status_callback=None, finish_callback=None):
    """
    Ejecuta la instalación de ocamlfuse en un hilo aparte.
    - output_callback(line): recibe cada línea de salida del proceso.
    - status_callback(text): recibe mensajes de estado.
    - finish_callback(returncode): se llama al terminar, con el código de retorno (0=ok).
    """
    def worker():
        returncode = ejecutar_instalacion_ocamlfuse(install_cmd, output_callback, status_callback)
        if finish_callback:
            finish_callback(returncode)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread