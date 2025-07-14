
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

import sys
import os
import socket
import tkinter as tk
from gi.repository import GLib

# Añadir el directorio 'vendor' a la ruta de búsqueda de Python para las dependencias empaquetadas
base_dir = os.path.dirname(os.path.abspath(__file__))
vendor_dir = os.path.join(base_dir, 'vendor')
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

from ocamlfuse_manager_gui.gui import GoogleDriveManager

# Variable global para mantener el socket de bloqueo
lock_socket = None

def is_another_instance_running():
    """
    Verifica si ya hay otra instancia de la aplicación en ejecución
    utilizando un socket de dominio Unix.
    """
    global lock_socket
    socket_name = "\0easy_ocamlfuse_lock"
    
    try:
        # Crear un socket de dominio Unix
        lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Intentar enlazar el socket al nombre abstracto
        lock_socket.bind(socket_name)
        return False
    except socket.error:
        # Si el enlace falla, es probable que otra instancia ya esté en ejecución.
        return True

def main():
    # Verificar si ya hay una instancia en ejecución
    if is_another_instance_running():
        print("Easy Ocamlfuse ya se está ejecutando. Saliendo.")
        sys.exit(0)

    main_loop = GLib.MainLoop()

    try:
        # Esta es la primera instancia, iniciar la aplicación
        app = GoogleDriveManager(main_loop=main_loop)
        
        # Iniciar tareas en segundo plano después de que la UI esté lista
        app.root.after(100, app.start_background_tasks)
        
        # Bucle principal de Tkinter gestionado por GLib
        def tkinter_update():
            try:
                if app.root.winfo_exists():
                    app.root.update()
                    return True # Mantener el bucle
                else:
                    if not main_loop.is_running():
                        main_loop.quit()
                    return False # Detener el bucle
            except tk.TclError:
                if not main_loop.is_running():
                    main_loop.quit()
                return False # Detener el bucle

        GLib.idle_add(tkinter_update)
        main_loop.run()

    except Exception as e:
        print(f"Error inesperado al iniciar la aplicación: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()