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

# Ruta 3: Ver los detalles de una incidencia específica
@app.route('/incidencia/<int:id>')
def ver_detalle(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        # Buscar el registro exacto usando el ID
        resultado = cliente.execute("SELECT * FROM incidencias WHERE id = ?", (id,))
        cliente.close()
        
        if resultado.rows:
            # Extraer la primera (y única) fila encontrada
            datos_incidencia = resultado.rows[0]
            return render_template('detalle.html', incidencia=datos_incidencia)
        else:
            return "<h1>Error: Incidencia no encontrada</h1>", 404
            
    except Exception as e:
        return f"<h1>Error al conectar con la base de datos: {e}</h1>"

# Ruta 4: Actualizar el estado a Pendiente o En revisión
@app.route('/actualizar_estado/<int:id>', methods=['POST'])
def actualizar_estado(id):
    nuevo_estado = request.form['nuevo_estado']
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE incidencias SET estado = ? WHERE id = ?", (nuevo_estado, id))
        cliente.close()
    except Exception as e:
        print(f"Error al actualizar estado: {e}")
        
    return redirect(url_for('ver_detalle', id=id))

# Ruta 5: Registrar solución y marcar como Resuelta
@app.route('/resolver/<int:id>', methods=['POST'])
def resolver_incidencia(id):
    solucion = request.form['solucion']
    fecha_solucion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        sql = "UPDATE incidencias SET solucion = ?, estado = 'Resuelta', fecha_solucion = ? WHERE id = ?"
        cliente.execute(sql, (solucion, fecha_solucion, id))
        cliente.close()
    except Exception as e:
        print(f"Error al resolver incidencia: {e}")
        
    return redirect(url_for('ver_detalle', id=id))

# Ruta 6: Eliminar registro
@app.route('/eliminar/<int:id>', methods=['POST'])
def eliminar_incidencia(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("DELETE FROM incidencias WHERE id = ?", (id,))
        cliente.close()
    except Exception as e:
        print(f"Error al eliminar incidencia: {e}")
        
    return redirect(url_for('inicio'))

if __name__ == '__main__':
    app.run(debug=True)