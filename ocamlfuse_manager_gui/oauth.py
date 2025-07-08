import http.server
import socketserver
import urllib.parse
import threading
import time
import webbrowser
from .i18n import i18n_instance
_ = i18n_instance.gettext


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handler para capturar el código OAuth"""
    def __init__(self, oauth_manager, *args, **kwargs):
        self.oauth_manager = oauth_manager
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)

        common_style = """
        <style>
            body {
                background-color: #2d2d2d; /* Gris oscuro */
                color: white;
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                display: flex;
                justify-content: center; /* Centrado horizontal */
                align-items: flex-start; /* Alineado arriba */
                padding-top: 15vh; /* Espacio desde arriba */
                height: 100vh;
                text-align: center;
            }
        </style>
        """

        # Manejar cancelación explícita desde Google
        if 'error' in params:
            # Llamar al callback de la ventana si existe (para cerrar y setear evento)
            if hasattr(self.oauth_manager, 'on_cancel') and self.oauth_manager.on_cancel:
                try:
                    import tkinter
                    def safe_close():
                        try:
                            self.oauth_manager.on_cancel()
                        except Exception as e:
                            print(f"Error llamando a on_cancel: {e}")
                    # Si hay al menos una ventana Tk, usar after
                    if tkinter._default_root:
                        tkinter._default_root.after(0, safe_close)
                    else:
                        safe_close()
                except Exception as e:
                    print(f"Error llamando a on_cancel (after): {e}")
            self.oauth_manager.cancel_auth()
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html_response = f"""
            <html>
            <head>
                <title>{_("Autorización Cancelada")}</title>
                {common_style}
            </head>
            <body>
                <div>
                    <h2>✗ {_("Autorización Cancelada")}</h2>
                    <p>{_("Cancelaste el acceso en Google. Puedes cerrar esta ventana y volver a la aplicación.")}</p>
                </div>
                <script>setTimeout(function(){{window.close();}}, 3000);</script>
            </body>
            </html>
            """
            self.wfile.write(html_response.encode("utf-8"))
            return

        if self.path.startswith('/?code=') or self.path.startswith('/oauth2callback?code='):
            if 'code' in params:
                auth_code = params['code'][0]
                self.oauth_manager.set_auth_code(auth_code)
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                html_response = f"""
                <html>
                <head>
                    <title>{_("Autorización Completada")}</title>
                    {common_style}
                </head>
                <body>
                    <div>
                        <h2>✓ {_("Autorización Completada")}</h2>
                        <p>{_("El código de autorización ha sido capturado correctamente.")}</p>
                        <p>{_("Puedes cerrar esta ventana y volver a la aplicación.")}</p>
                    </div>
                    <script>setTimeout(function(){{window.close();}}, 3000);</script>
                </body>
                </html>
                """
                self.wfile.write(html_response.encode("utf-8"))
                
            else:
                self.send_error(400, _( "No se encontró el código de autorización"))
        else:
            self.send_error(404, _( "Página no encontrada"))
    
    def log_message(self, format, *args):
        pass

class OAuthServer:
    """Servidor OAuth para capturar códigos de autorización"""
    def __init__(self, port=8080):
        self.port = port
        self.server = None
        self.auth_code = None
        self.server_thread = None
        self.running = False
        self.stopped = False
        self.cancelled = False
    
    def start_server(self):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            handler = lambda *args, **kwargs: OAuthHandler(self, *args, **kwargs)
            self.server = socketserver.TCPServer(("", self.port), handler)
            self.running = True
            self.stopped = False  # Reinicia el flag al iniciar
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            print(_(f"Servidor OAuth iniciado en http://localhost:{self.port}"))
            return True
        except Exception as e:
            print(_(f"Error al iniciar servidor OAuth: {e}"))
            return False
    
    def stop_server(self):
        if self.server and self.running and not self.stopped:
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            self.stopped = True
            print(_("Servidor OAuth detenido"))
    
    def set_auth_code(self, code):
        self.auth_code = code
        print(_(f"Código OAuth capturado: {code[:10]}..."))
    
    def cancel_auth(self):
        self.cancelled = True
        print(_("Autorización cancelada por el usuario."))

    def wait_for_code(self, timeout=125):
        start_time = time.time()
        while self.auth_code is None and not self.cancelled and (time.time() - start_time < timeout):
            time.sleep(0.5)
        return self.auth_code

def authenticate(client_id, client_secret, port, cancel_event, timeout=120):
    oauth_server = OAuthServer(port=port)
    server_started = False
    try:
        if not oauth_server.start_server():
            return None, "server_error"
        server_started = True

        redirect_url = f"http://localhost:{oauth_server.port}"
        auth_url = (
            "https://accounts.google.com/o/oauth2/auth?"
            f"response_type=code&client_id={client_id}"
            f"&redirect_uri={redirect_url}"
            "&scope=https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email"
            "&access_type=offline"
            "&prompt=select_account"
            "&include_granted_scopes=true"
        )
        webbrowser.open(auth_url)

        start_time = time.time()
        auth_code = None
        while not cancel_event.is_set() and not oauth_server.cancelled and (time.time() - start_time < timeout):
            if oauth_server.auth_code is not None:
                auth_code = oauth_server.auth_code
                break
            time.sleep(0.2)

        if oauth_server.cancelled:
            return None, "cancelled"
        if cancel_event.is_set():
            return None, "user_cancel"
        if not auth_code:
            return None, "timeout"
        
        return auth_code, None
    finally:
        if server_started:
            oauth_server.stop_server()
            time.sleep(0.5)