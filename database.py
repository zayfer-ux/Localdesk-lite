import os
from dotenv import load_dotenv
import libsql_client

# Cargar las variables ocultas del archivo .env
load_dotenv()

# Obtener las credenciales
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

def probar_conexion():
    print("Intentando conectar con Turso...")
    try:
        # Abrir la conexión
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        print("¡Conexión a Turso exitosa!")
        
        # Cerrar la conexión por ahora
        cliente.close()
    except Exception as e:
        print(f"Error al conectar con la base de datos: {e}")

# Esta condición permite probar el archivo ejecutándolo directamente
if __name__ == "__main__":
    probar_conexion()