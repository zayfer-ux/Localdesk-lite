import os
import libsql_client
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

try:
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    print("Conectado a Turso. Actualizando tabla 'usuarios'...")
    
    # Intentamos agregar las nuevas columnas (Ignora los errores si ya existen)
    try: cliente.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    except: pass
    try: cliente.execute("ALTER TABLE usuarios ADD COLUMN telefono TEXT")
    except: pass
    try: cliente.execute("ALTER TABLE usuarios ADD COLUMN foto TEXT")
    except: pass
    
    # Le asignamos un correo por defecto al admin para que pueda iniciar sesión
    cliente.execute("UPDATE usuarios SET email = 'admin@localdesk.com' WHERE usuario = 'admin' AND email IS NULL")
    
    print("✅ Base de datos actualizada. ¡Lista para perfiles de usuario!")
    cliente.close()
except Exception as e:
    print(f"Error: {e}")