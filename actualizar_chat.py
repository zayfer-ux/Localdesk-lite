import os
import libsql_client
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

try:
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    print("Conectando a Turso...")
    
    # Crear tabla para la mensajería privada entre usuarios
    cliente.execute("""
    CREATE TABLE IF NOT EXISTS mensajes_privados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        remitente_id INTEGER NOT NULL,
        destinatario_id INTEGER NOT NULL,
        mensaje TEXT NOT NULL,
        archivo TEXT,
        fecha DATETIME NOT NULL
    )
    """)
    print("✅ Tabla 'mensajes_privados' creada. ¡Lista para mensajes directos!")
    cliente.close()
except Exception as e:
    print(f"❌ Error: {e}")