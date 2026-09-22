import os
from flask import Flask, render_template
import libsql_client
from dotenv import load_dotenv

# Cargar credenciales
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

app = Flask(__name__)

@app.route('/')
def inicio():
    try:
        # Conectar a Turso y obtener todos los registros
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
        lista_incidencias = resultado.rows
        cliente.close()
    except Exception as e:
        lista_incidencias = []
        print(f"Error al conectar con la base de datos: {e}")

    # Enviar los datos al archivo HTML
    return render_template('index.html', incidencias=lista_incidencias)

if __name__ == '__main__':
    app.run(debug=True)