import os
from flask import Flask, render_template, request, redirect, url_for
import libsql_client
from dotenv import load_dotenv
from datetime import datetime

# Cargar credenciales
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

app = Flask(__name__)

# Ruta 1: Mostrar el panel principal (Ya la teníamos)
@app.route('/')
def inicio():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
        lista_incidencias = resultado.rows
        cliente.close()
    except Exception as e:
        lista_incidencias = []
        print(f"Error base de datos: {e}")

    return render_template('index.html', incidencias=lista_incidencias)

# Ruta 2: Mostrar el formulario y guardar los datos (NUEVA)
@app.route('/nuevo', methods=['GET', 'POST'])
def nuevo_registro():
    if request.method == 'POST':
        # 1. Obtener los datos que el usuario escribió en la web
        titulo = request.form['titulo']
        equipo = request.form['equipo']
        area = request.form['area']
        categoria = request.form['categoria']
        descripcion = request.form['descripcion']
        prioridad = request.form['prioridad']
        reportado_por = request.form['reportado_por']
        
        # 2. Agregar datos automáticos
        estado = "Pendiente"
        fecha_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 3. Guardar en Turso
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            sql = """
            INSERT INTO incidencias (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cliente.execute(sql, (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte))
            cliente.close()
        except Exception as e:
            print(f"Error al guardar: {e}")

        # 4. Regresar a la pantalla principal automáticamente
        return redirect(url_for('inicio'))

    # Si entra normal (GET), solo le mostramos el formulario
    return render_template('nuevo.html')

if __name__ == '__main__':
    app.run(debug=True)