# Easy Ocamlfuse - Gestor Gráfico para Google Drive

![Easy Ocamlfuse](https://imgur.com/gallery/easy-ocamlfuse-Yx3A1ax)

**Easy Ocamlfuse** es una aplicación de escritorio con interfaz gráfica (GUI) para gestionar `google-drive-ocamlfuse`, facilitando el montaje y la administración de tus cuentas de Google Drive en sistemas Linux.

La aplicación está desarrollada en Python con Tkinter y es compatible con múltiples idiomas (español e inglés por defecto).

---

## ✨ Características Principales

- **Gestión de Múltiples Cuentas**: Añade, configura y elimina múltiples cuentas de Google Drive.
- **Montaje y Desmontaje Sencillo**: Monta y desmonta tus unidades con un solo clic.
- **Automontaje al Inicio**: Configura tus cuentas para que se monten automáticamente al iniciar la aplicación.
- **Bandeja del Sistema**: Se integra con la bandeja del sistema para un acceso rápido y gestión en segundo plano.
- **Internacionalización**: Soporte para múltiples idiomas (español e inglés incluidos).
- **Detección Automática**: Detecta instalaciones existentes de `google-drive-ocamlfuse` y las importa.
- **Asistente de Instalación**: Si `google-drive-ocamlfuse` no está instalado, la aplicación te guiará para instalarlo automáticamente.
- **Restauración de Cuentas**: Permite restaurar cuentas eliminadas previamente.

---

## 📋 Requisitos

Asegúrate de tener las siguientes dependencias instaladas en tu sistema.

### Dependencias del Sistema
- **Python 3.x**
- **Tkinter**: Generalmente se instala con `python3-tk`.
- **google-drive-ocamlfuse**: El motor principal para montar las unidades.
- **FUSE**: Sistema de archivos en el espacio de usuario.
- **gettext**: Para la internacionalización.

En distribuciones basadas en Debian/Ubuntu, puedes instalar la mayoría con:
```bash
sudo apt update
sudo apt install python3-tk gettext fuse
```

### Dependencias de Python
Puedes instalarlas usando `pip`:
```bash
pip install notify2 Pillow pystray requests
```

---

## 🚀 Instalación y Ejecución

1.  **Clona el repositorio:**
    ```bash
    git clone https://github.com/tu-usuario/Easy-ocamlfuse.git
    cd Easy-ocamlfuse
    ```

2.  **Instala las dependencias de Python:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Nota: Asegúrate de crear un archivo `requirements.txt` con el contenido mencionado arriba).*

3.  **Ejecuta la aplicación:**
    Desde el directorio raíz del proyecto:
    ```bash
    python3 main.py
    ```
    o como módulo:
    ```bash
    python3 -m ocamlfuse_manager_gui.main
    ```

---

## 📖 Uso Básico

### 1. Añadir una Cuenta

1.  Ve a la pestaña **"Gestión de Cuentas"**.
2.  Para obtener tus credenciales de Google, haz clic en el botón **"Ayuda"**, que te guiará en el proceso de creación de un ID de Cliente y Secreto de Cliente en Google Cloud Console.
3.  Puedes cargar las credenciales desde el archivo `client_secrets.json` descargado usando el botón **"Cargar JSON"** o pegarlas manualmente.
4.  Asigna una **Etiqueta** única a tu cuenta (ej. "Personal", "Trabajo").
5.  Haz clic en **"Configurar Cuenta"**. Se abrirá una ventana en tu navegador para que autorices el acceso a tu cuenta de Google.

### 2. Montar una Cuenta

1.  Ve a la pestaña **"Gestión Principal"**.
2.  Haz clic en **"Montar Cuenta"**.
3.  Selecciona la cuenta que deseas montar de la lista.
4.  La unidad se montará en tu directorio `HOME` en una carpeta con el mismo nombre que la etiqueta.

### 3. Gestión desde la Bandeja del Sistema

- La aplicación se minimizará a la bandeja del sistema al cerrar la ventana.
- Desde el icono de la bandeja, puedes:
    - Mostrar la ventana principal.
    - Desmontar todas las unidades.
    - Salir de la aplicación.

---

## 🌍 Internacionalización (i18n)

El proyecto utiliza `gettext` para las traducciones. Los archivos de idioma se encuentran en `ocamlfuse_manager_gui/locale`.

Para actualizar o añadir un nuevo idioma:

1.  **Genera el archivo `.pot` (plantilla):**
    ```bash
    cd ocamlfuse_manager_gui
    xgettext --from-code=UTF-8 --language=Python --keyword=_ --output=locale/ocamlfuse_manager.pot --files-from=locale/POTFILES.in
    ```

2.  **Crea o actualiza el archivo `.po` para tu idioma (ej. `fr` para francés):**
    ```bash
    msginit -l fr -o locale/fr/LC_MESSAGES/ocamlfuse_manager.po -i locale/ocamlfuse_manager.pot
    # O para actualizar uno existente:
    msgmerge -U locale/fr/LC_MESSAGES/ocamlfuse_manager.po locale/ocamlfuse_manager.pot
    ```

3.  **Traduce los textos en el archivo `.po`**.

4.  **Compila el archivo `.mo`:**
    ```bash
    msgfmt locale/fr/LC_MESSAGES/ocamlfuse_manager.po -o locale/fr/LC_MESSAGES/ocamlfuse_manager.mo
    ```

---

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas! 

## 📜 Licencia

Este proyecto está bajo la Licencia GPL. Consulta el archivo [LICENSE.txt](ocamlfuse_manager_gui/assets/resources/LICENSE.txt) para más detalles.
