
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
socket_name = "\0easy_ocamlfuse_lock"

def setup_instance_messaging(app):
    """
    Configura el socket para escuchar mensajes de otras instancias
    y mostrar la ventana de la aplicación si se recibe una señal.
    """
    global lock_socket
    lock_socket.setblocking(False)
    lock_socket.listen(1)

    def handle_new_connection(sock, condition):
        try:
            conn, addr = sock.accept()
            # La conexión es la señal. Mostrar la ventana.
            print("Recibida señal de otra instancia. Mostrando ventana.")
            app.show_window()
            conn.close()
        except Exception as e:
            print(f"Error al manejar la conexión de otra instancia: {e}")
        return True  # Mantener el watch activo

    GLib.io_add_watch(lock_socket, GLib.IO_IN, handle_new_connection)

def main():
    """
    Punto de entrada principal. Maneja la lógica de instancia única
    y lanza la aplicación.
    """
    global lock_socket
    
    try:
        # Intentar ser la instancia principal
        lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        lock_socket.bind(socket_name)
        
        # --- Esta es la instancia principal ---
        main_loop = GLib.MainLoop()
        try:
            app = GoogleDriveManager(main_loop=main_loop)
            
            # Configurar el listener para otras instancias
            setup_instance_messaging(app)
            
            # Iniciar tareas en segundo plano después de que la UI esté lista
            app.root.after(100, app.start_background_tasks)
            
            # Bucle principal de Tkinter gestionado por GLib
            def tkinter_update():
                try:
                    if app.root.winfo_exists():
                        app.root.update()
                        return True  # Mantener el bucle
                    else:
                        if main_loop.is_running():
                            main_loop.quit()
                        return False  # Detener el bucle
                except tk.TclError:
                    if main_loop.is_running():
                        main_loop.quit()
                    return False  # Detener el bucle

            GLib.idle_add(tkinter_update)
            main_loop.run()

        except Exception as e:
            print(f"Error inesperado al iniciar la aplicación: {e}")
            if main_loop.is_running():
                main_loop.quit()
            sys.exit(1)

    except socket.error:
        # --- Ya hay otra instancia en ejecución ---
        print("Easy Ocamlfuse ya se está ejecutando. Enviando señal para mostrar la ventana.")
        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.connect(socket_name)
            client_socket.close()
            print("Señal enviada correctamente.")
        except socket.error as e:
            print(f"No se pudo conectar a la instancia existente: {e}")
        
        sys.exit(0)  # Salir de la segunda instancia

if __name__ == "__main__":
    main()