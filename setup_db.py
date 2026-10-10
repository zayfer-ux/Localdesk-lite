import os
import libsql_client
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Cargar credenciales
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

print("Conectando a Turso...")

try:
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    
    # 1. Crear la tabla de usuarios
    print("Creando tabla 'usuarios'...")
    cliente.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        usuario TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        rol TEXT NOT NULL
    )
    """)
    
    # 2. Generar una contraseña encriptada (Hash) segura
    # Nunca se guarda "admin123" en texto plano, se guarda algo como "pbkdf2:sha256:260000$..."
    password_segura = generate_password_hash('admin123')
    
    # 3. Insertar el primer usuario administrador (Evitando duplicados si ya existe)
    print("Generando usuario administrador por defecto...")
    try:
        cliente.execute("""
        INSERT INTO usuarios (nombre, usuario, password, rol) 
        VALUES ('Administrador Principal', 'admin', ?, 'Admin')
        """, (password_segura,))
        print("✅ ¡Éxito! Base de datos lista. Usuario 'admin' y contraseña 'admin123' creados.")
    except Exception as e:
        print("ℹ️ El usuario 'admin' ya existía en la base de datos. Todo listo.")
        
    cliente.close()

except Exception as e:
    print(f"❌ Error al conectar con la base de datos: {e}")