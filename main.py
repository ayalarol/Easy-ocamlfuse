import sys
import os
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

# Añadir el directorio 'vendor' a la ruta de búsqueda de Python
vendor_dir = os.path.dirname(os.path.abspath(__file__))
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

from ocamlfuse_manager_gui.gui import GoogleDriveManager

# Constantes para D-Bus
DBUS_SERVICE_NAME = 'org.easyocamlfuse.Manager'
DBUS_OBJECT_PATH = '/org/easyocamlfuse/Manager'
DBUS_INTERFACE_NAME = 'org.easyocamlfuse.ManagerInterface'

class EasyOcamlfuseDBusService(dbus.service.Object):
    def __init__(self, app_instance):
        super().__init__(dbus.SessionBus(), DBUS_OBJECT_PATH)
        self.app = app_instance

    @dbus.service.method(dbus_interface=DBUS_INTERFACE_NAME,
                         in_signature='', out_signature='')
    def ShowWindow(self):
        self.app.show_window()

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    main_loop = GLib.MainLoop()

    try:
        # Intentar adquirir el nombre del servicio D-Bus
        bus = dbus.SessionBus()
        name = dbus.service.BusName(DBUS_SERVICE_NAME, bus)
        
        # Si se adquiere el nombre, esta es la primera instancia
        app = GoogleDriveManager(main_loop=main_loop) # Pasa el main_loop a la aplicación
        service = EasyOcamlfuseDBusService(app)
        app.root.after(0, app.start_background_tasks)
        
        # Función para actualizar Tkinter dentro del bucle de GLib
        def tkinter_update():
            if not app.is_quitting and app.root.winfo_exists(): # Solo actualizar si la app no está cerrando y la ventana existe
                try:
                    app.root.update_idletasks()
                    app.root.update()
                except tk.TclError: # Manejar el error si la ventana ya ha sido destruida
                    return False # Detener el callback
            elif app.is_quitting: # Si la app está cerrando, detener el bucle de GLib
                main_loop.quit()
                return False
            return True # Continuar el callback

        # Ejecutar la actualización de Tkinter periódicamente
        GLib.idle_add(tkinter_update)

        # Iniciar el bucle principal de GLib
        main_loop.run()

    except dbus.exceptions.NameExistsException:
        print("La aplicación ya se está ejecutando. Enviando señal para mostrar la ventana.")
        try:
            bus = dbus.SessionBus()
            remote_object = bus.get_object(DBUS_SERVICE_NAME, DBUS_OBJECT_PATH)
            remote_object.ShowWindow(dbus_interface=DBUS_INTERFACE_NAME)
        except Exception as e:
            print(f"Error al intentar comunicar con la instancia existente: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"Error inesperado al iniciar la aplicación: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()