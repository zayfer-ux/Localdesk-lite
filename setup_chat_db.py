import os
import libsql_client
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

try:
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    print("Conectando a Turso...")
    
    # 1. Crear tabla de Mensajes (Chat del Ticket)
    cliente.execute("""
    CREATE TABLE IF NOT EXISTS mensajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incidencia_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        mensaje TEXT NOT NULL,
        tipo TEXT DEFAULT 'chat', 
        archivo TEXT,
        fecha DATETIME NOT NULL
    )
    """)
    print("✅ Tabla 'mensajes' creada (Soporte para Chat y Notas Internas).")

    # 2. Crear tabla de Notificaciones (Alertas de la Campanita)
    cliente.execute("""
    CREATE TABLE IF NOT EXISTS notificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        texto TEXT NOT NULL,
        enlace TEXT,
        leida INTEGER DEFAULT 0,
        fecha DATETIME NOT NULL
    )
    """)
    print("✅ Tabla 'notificaciones' creada (Soporte para Alertas).")

    cliente.close()
    print("🎉 ¡Base de datos ejecutiva lista para el siguiente nivel!")

except Exception as e:
    print(f"❌ Error al conectar con la base de datos: {e}")