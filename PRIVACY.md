# Política de Privacidad de Easy Ocamlfuse

Última actualización: 28 de marzo de 2026

Easy Ocamlfuse es una aplicación de escritorio de código abierto diseñada para facilitar la gestión de montajes de Google Drive en sistemas Linux utilizando la herramienta subyacente `google-drive-ocamlfuse`.

## 1. Recopilación de Información
Easy Ocamlfuse **no recopila, almacena ni transmite ningún dato personal** a servidores externos controlados por los desarrolladores. Toda la información necesaria para el funcionamiento de la aplicación se gestiona de forma local en el equipo del usuario.

## 2. Uso de la API de Google Drive
La aplicación utiliza la API de Google Drive para permitir el acceso a sus archivos y carpetas con el fin de montarlos como una unidad de red local.
- **Tokens de Acceso:** Durante el proceso de autenticación OAuth, se obtiene un token de acceso y un token de actualización directamente desde Google.
- **Almacenamiento Local:** Estos tokens se almacenan de forma segura y **únicamente en su computadora local**, generalmente en los directorios de configuración de `google-drive-ocamlfuse` (por ejemplo, en `~/.gdfuse/`).
- **Transferencia de Datos:** Los datos de sus archivos de Google Drive se transfieren directamente entre los servidores de Google y su sistema local a través de `google-drive-ocamlfuse`. La aplicación Easy Ocamlfuse no actúa como intermediario ni tiene acceso a la transferencia de estos contenidos.

## 3. Seguridad
Dado que toda la configuración y las credenciales se almacenan localmente, la seguridad de sus datos depende de la seguridad de su propio sistema operativo y equipo físico. Se recomienda mantener su sistema actualizado y no compartir sus archivos de configuración locales.

## 4. Servicios de Terceros
Al utilizar esta aplicación para acceder a Google Drive, usted también está sujeto a la [Política de Privacidad de Google](https://policies.google.com/privacy).

## 5. Cambios en esta Política
Podemos actualizar nuestra Política de Privacidad de vez en cuando. Se le notificará de cualquier cambio mediante la publicación de la nueva política en el repositorio oficial de GitHub.

## 6. Contacto
Si tiene alguna pregunta sobre esta Política de Privacidad, puede abrir un "issue" en el repositorio oficial de GitHub: [https://github.com/ayalarol/Easy-ocamlfuse](https://github.com/ayalarol/Easy-ocamlfuse).
