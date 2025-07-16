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
    Función para avisar al usuario si hay una nueva versión del binario lanzado en releases de la pagina de github
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
    ventana.update_idletasks()
    ventana.geometry("+0+0")
    ventana.update_idletasks() 

    if respecto_a:
        ventana.transient(respecto_a)
        ventana.update_idletasks() 
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
    #Devuelve (estado, mensaje, color)
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
    #Detecta la distribución de Linux y su versión.
    distro_id = "unknown"
    version_id = "0"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    distro_id = line.split("=")[1].strip().replace('"', '')
                elif line.startswith("VERSION_ID="):
                    version_id = line.split("=")[1].strip().replace('"', '')
    except Exception:
        pass
    return distro_id, version_id

def obtener_comando_instalacion_ocamlfuse(distro_id, version_id, ppa_choice="normal"):
    #Devuelve el comando de instalación adecuado para la distro.
    if distro_id == 'debian':
        command = (
            'apt update && '
            'apt install -y software-properties-common dirmngr && '
            'echo "deb http://ppa.launchpad.net/alessandro-strada/ppa/ubuntu bionic main" >> /etc/apt/sources.list.d/alessandro-strada-ubuntu-ppa-bionic.list && '
            'echo "deb-src http://ppa.launchpad.net/alessandro-strada/ppa/ubuntu bionic main" >> /etc/apt/sources.list.d/alessandro-strada-ubuntu-ppa-bionic.list && '
            'apt-key adv --keyserver keyserver.ubuntu.com --recv-keys AD5F235DF639B041 && '
            'apt-get update && '
            'groupadd -f fuse && '
            'adduser $(whoami) fuse && '
            'apt-get install -y google-drive-ocamlfuse'
        )
        return command
    elif distro_id in ["ubuntu", "linuxmint", "pop"]:
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
    Ejecuta el comando de instalación de ocamlfuse
    Devuelve el código de retorno del proceso.
    """
    try:
        full_cmd = ["pkexec", "sh", "-c", install_cmd]
        if status_callback:
            status_callback(_("Solicitando permisos..."))
        if output_callback:
            output_callback(_("> Solicitando permisos de administrador...\n"))

        process = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Cambiado a PIPE para capturar stderr por separado
            text=True,
            # Añadir env=os.environ para asegurar que se hereden las variables de entorno
            env=os.environ
        )

        if status_callback:
            status_callback(_("Instalando..."))
        if output_callback:
            output_callback(_("> Ejecutando: ") + install_cmd + "\n")

        # Leer salida en tiempo real y capturar stderr
        stdout_lines = []
        stderr_lines = []
        
        # Usar select para leer de ambos pipes sin bloquear
        import select
        
        while True:
            reads = [process.stdout.fileno(), process.stderr.fileno()]
            ret = select.select(reads, [], [])
            
            for fd in ret[0]:
                if fd == process.stdout.fileno():
                    line = process.stdout.readline()
                    if line:
                        stdout_lines.append(line)
                        if output_callback:
                            output_callback(line)
                if fd == process.stderr.fileno():
                    line = process.stderr.readline()
                    if line:
                        stderr_lines.append(line)
                        if output_callback: # También mostrar stderr en la salida
                            output_callback(_("[ERROR] ") + line)
            
            if process.poll() is not None: # Proceso terminado
                # Leer cualquier salida restante
                for line in process.stdout.readlines():
                    if line:
                        stdout_lines.append(line)
                        if output_callback:
                            output_callback(line)
                for line in process.stderr.readlines():
                    if line:
                        stderr_lines.append(line)
                        if output_callback:
                            output_callback(_("[ERROR] ") + line)
                break

        returncode = process.returncode
        
        if returncode != 0 and stderr_lines:
            # Si hay un error y stderr no está vacío, añadirlo al output
            if output_callback:
                output_callback(_("\n--- Errores de pkexec/instalación ---\n"))
                for line in stderr_lines:
                    output_callback(line)
                output_callback(_("-------------------------------------\n"))

        return returncode
    except Exception as e:
        if output_callback:
            output_callback(_("\n✗ Error inesperado: ") + str(e) + "\n")
        return -1

def instalar_ocamlfuse_async(install_cmd, output_callback=None, status_callback=None, finish_callback=None):
    
    #Ejecuta la instalación de ocamlfuse en un hilo aparte.
    
    def worker():
        returncode = ejecutar_instalacion_ocamlfuse(install_cmd, output_callback, status_callback)
        if finish_callback:
            finish_callback(returncode)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
