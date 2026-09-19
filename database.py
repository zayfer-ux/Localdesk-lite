import os
from dotenv import load_dotenv
import libsql_client

# Cargar las variables ocultas del archivo .env
load_dotenv()

# Obtener las credenciales
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

def preparar_base_datos():
    print("Conectando a Turso para configurar la base de datos...")
    try:
        # Abrir la conexión
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        
        # Sentencia SQL para crear la tabla de incidencias si no existe
        sql = """
        CREATE TABLE IF NOT EXISTS incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            equipo TEXT NOT NULL,
            area TEXT NOT NULL,
            categoria TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            prioridad TEXT NOT NULL DEFAULT 'Media',
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            reportado_por TEXT NOT NULL,
            solucion TEXT,
            fecha_reporte TEXT NOT NULL,
            fecha_solucion TEXT
        );
        """
        
        # Ejecutar la orden
        cliente.execute(sql)
        print("¡Tabla 'incidencias' creada y lista para usarse!")
        
        # Cerrar la conexión
        cliente.close()
    except Exception as e:
        print(f"Error al configurar la base de datos: {e}")

if __name__ == "__main__":
    preparar_base_datos()