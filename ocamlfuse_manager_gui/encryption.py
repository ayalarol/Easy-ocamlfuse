# -*- coding: utf-8 -*-
from cryptography.fernet import Fernet
import os
import stat
import shutil

class EncryptionManager:
    def __init__(self, key_dir="~/.gdrivemanagerconfig/.secure_key", key_name="easyocamlfusemanager.key"):
        self.key_dir = os.path.expanduser(key_dir)
        self.key_path = os.path.join(self.key_dir, key_name)
        self.key = None
        self.fernet = None
        # Crear la carpeta con permisos si no existe
        if not os.path.exists(self.key_dir):
            os.makedirs(self.key_dir, exist_ok=True)
            os.chmod(self.key_dir, stat.S_IRWXU)  # Solo usuario
        
        # lógica para manejar duplicados de carpetas
        parent_dir = os.path.dirname(self.key_dir)
        for item in os.listdir(parent_dir):
            item_path = os.path.join(parent_dir, item)
            if item == ".secure_key" and item_path != self.key_dir and os.path.isdir(item_path):
                # Fusionar archivos que no existan
                for fname in os.listdir(item_path):
                    src = os.path.join(item_path, fname)
                    dst = os.path.join(self.key_dir, fname)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                shutil.rmtree(item_path)
        if os.path.exists(self.key_path):
            self._load_key()

    def _load_key(self):
        with open(self.key_path, 'rb') as f:
            self.key = f.read()
            self.fernet = Fernet(self.key)

    def _generate_and_store_key(self):
        os.makedirs(self.key_dir, exist_ok=True)
        os.chmod(self.key_dir, stat.S_IRWXU)
        key = Fernet.generate_key()
        with open(self.key_path, 'wb') as f:
            f.write(key)
        os.chmod(self.key_path, stat.S_IRUSR | stat.S_IWUSR)  # Solo usuario
        self.key = key
        self.fernet = Fernet(self.key)

    def encrypt(self, data):
        if self.key is None or self.fernet is None:
            if not os.path.exists(self.key_path):
                self._generate_and_store_key()
            else:
                self._load_key()
        if isinstance(data, str):
            data = data.encode('utf-8')
        return self.fernet.encrypt(data).decode('utf-8')

    def decrypt(self, encrypted_data):
        if self.key is None or self.fernet is None:
            if not os.path.exists(self.key_path):
                raise RuntimeError("No existe clave de cifrado para descifrar datos.")
            self._load_key()
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.encode('utf-8')
        return self.fernet.decrypt(encrypted_data).decode('utf-8')
