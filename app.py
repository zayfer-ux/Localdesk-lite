import os
import io
import csv
import subprocess
import platform
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
import libsql_client
from dotenv import load_dotenv
from datetime import datetime
import json

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secreto_futurista_123")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logeado' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# FUNCIÓN PARA ENVIAR CORREO DE VERIFICACIÓN
# ==========================================
def enviar_codigo_registro(destinatario, codigo):
    msg = MIMEMultipart()
    msg['From'] = MAIL_USERNAME
    msg['To'] = destinatario
    msg['Subject'] = "Verifica tu cuenta - LocalDesk"
    
    cuerpo = f"""Hola,

Estás a un paso de unirte a LocalDesk. Tu código de verificación de 6 dígitos es:

{codigo}

Ingrésalo en la pantalla de registro para activar tu cuenta.
Si no solicitaste este registro, por favor ignora este mensaje.

Atentamente,
El equipo de LocalDesk"""

    msg.attach(MIMEText(cuerpo, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Error SMTP:", e)
        return False

# ==========================================
# RUTAS DE AUTENTICACIÓN, REGISTRO Y PERFIL
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            resultado = cliente.execute("SELECT id, nombre, usuario, password, rol, email, telefono, foto FROM usuarios WHERE email = ?", (email,))
            user_data = resultado.rows
            cliente.close()

            if user_data and check_password_hash(user_data[0][3], password):
                session['logeado'] = True
                session['id_usuario'] = user_data[0][0]
                session['nombre'] = user_data[0][1]
                session['usuario'] = user_data[0][2]
                session['rol'] = user_data[0][4]
                session['email'] = user_data[0][5]
                session['foto'] = user_data[0][7]
                return redirect(url_for('inicio'))
            else:
                flash('Correo o contraseña incorrectos.', 'danger')
        except Exception as e:
            flash('Error al conectar con la base de datos.', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        usuario = request.form.get('usuario')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 1. Verificar si el correo ya existe en la base de datos
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            res = cliente.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            cliente.close()
            if res.rows:
                flash('Este correo ya está registrado. Intenta iniciar sesión.', 'danger')
                return redirect(url_for('registro'))
        except:
            pass

        # 2. Generar el código OTP y encriptar contraseña
        password_segura = generate_password_hash(password)
        codigo_otp = str(random.randint(100000, 999999))
        
        # 3. Guardar datos temporalmente en la sesión
        session['reg_temp'] = {
            'nombre': nombre,
            'usuario': usuario,
            'email': email,
            'password': password_segura,
            'otp': codigo_otp
        }
        
        # 4. Enviar el correo
        if enviar_codigo_registro(email, codigo_otp):
            return redirect(url_for('verificar_registro'))
        else:
            flash('Error al enviar el correo. Revisa tu configuración.', 'danger')

    return render_template('registro.html')

@app.route('/verificar_registro', methods=['GET', 'POST'])
def verificar_registro():
    # Si entra aquí sin haber pasado por el formulario, lo regresamos
    if 'reg_temp' not in session:
        return redirect(url_for('registro'))

    if request.method == 'POST':
        codigo_ingresado = request.form.get('codigo')
        datos = session['reg_temp']

        if codigo_ingresado == datos['otp']:
            # ¡CÓDIGO CORRECTO! Guardamos al usuario en la BD
            try:
                cliente = libsql_client.create_client_sync(url=url, auth_token=token)
                sql = "INSERT INTO usuarios (nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, 'Soporte Técnico')"
                cliente.execute(sql, (datos['nombre'], datos['usuario'], datos['email'], datos['password']))
                cliente.close()
                
                # Borramos la sesión temporal
                session.pop('reg_temp', None)
                flash('¡Cuenta verificada y creada con éxito! Ya puedes iniciar sesión.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash('Error al guardar en la base de datos.', 'danger')
        else:
            flash('Código incorrecto. Revisa tu correo e intenta de nuevo.', 'danger')

    return render_template('verificar_registro.html', email=session['reg_temp']['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    id_user = session.get('id_usuario')
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    if request.method == 'POST':
        telefono = request.form.get('telefono')
        foto_url = request.form.get('foto')
        try:
            cliente.execute("UPDATE usuarios SET telefono = ?, foto = ? WHERE id = ?", (telefono, foto_url, id_user))
            session['foto'] = foto_url
        except: pass
        return redirect(url_for('perfil'))
    
    resultado = cliente.execute("SELECT nombre, usuario, email, rol, telefono, foto FROM usuarios WHERE id = ?", (id_user,))
    datos_perfil = resultado.rows[0] if resultado.rows else None
    cliente.close()
    return render_template('perfil.html', perfil=datos_perfil)

# ==========================================
# RUTAS DEL SISTEMA PRINCIPAL (INCIDENCIAS Y DEMÁS)
# ==========================================
@app.route('/')
@login_required
def inicio():
    busqueda = request.args.get('q', '')
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        res_total = cliente.execute("SELECT * FROM incidencias")
        todas = res_total.rows
        stats = {
            'total': len(todas),
            'pendientes': sum(1 for i in todas if i[7] == 'Pendiente'),
            'revision': sum(1 for i in todas if i[7] == 'En revisión'),
            'resueltas': sum(1 for i in todas if i[7] == 'Resuelta')
        }
        categorias = {
            'Hardware': sum(1 for i in todas if i[4] == 'Hardware'),
            'Software': sum(1 for i in todas if i[4] == 'Software'),
            'Red': sum(1 for i in todas if i[4] == 'Red'),
            'Otro': sum(1 for i in todas if i[4] == 'Otro')
        }
        if busqueda:
            param = f"%{busqueda}%"
            sql = "SELECT * FROM incidencias WHERE CAST(id AS TEXT) LIKE ? OR titulo LIKE ? OR equipo LIKE ? OR reportado_por LIKE ? ORDER BY id DESC"
            resultado = cliente.execute(sql, (param, param, param, param))
        else:
            resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
        lista_incidencias = resultado.rows
        cliente.close()
    except:
        lista_incidencias = []
        stats = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}
        categorias = {'Hardware': 0, 'Software': 0, 'Red': 0, 'Otro': 0}

    return render_template('index.html', incidencias=lista_incidencias, stats=stats, categorias=json.dumps(categorias), busqueda=busqueda)

@app.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_registro():
    if request.method == 'POST':
        titulo = request.form['titulo']
        equipo = request.form['equipo']
        area = request.form['area']
        categoria = request.form['categoria']
        descripcion = request.form['descripcion']
        prioridad = request.form['prioridad']
        reportado_por = request.form['reportado_por']
        estado = "Pendiente"
        fecha_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            sql = "INSERT INTO incidencias (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            cliente.execute(sql, (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte))
            cliente.close()
        except: pass
        return redirect(url_for('inicio'))
    return render_template('nuevo.html')

@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT * FROM incidencias WHERE id = ?", (id,))
        cliente.close()
        if resultado.rows: return render_template('detalle.html', incidencia=resultado.rows[0])
        else: return "<h1>Error: Incidencia no encontrada</h1>", 404
    except Exception as e: return f"<h1>Error: {e}</h1>"

@app.route('/actualizar_estado/<int:id>', methods=['POST'])
@login_required
def actualizar_estado(id):
    nuevo_estado = request.form['nuevo_estado']
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE incidencias SET estado = ? WHERE id = ?", (nuevo_estado, id))
        cliente.close()
    except: pass
    return redirect(url_for('ver_detalle', id=id))

@app.route('/resolver/<int:id>', methods=['POST'])
@login_required
def resolver_incidencia(id):
    solucion_redactada = request.form['solucion']
    fecha_solucion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tecnico = session.get('nombre', 'Técnico')
    rol = session.get('rol', 'TI')
    solucion_con_firma = f"{solucion_redactada}\n\n✅ Atendido por: {tecnico} ({rol})"
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        sql = "UPDATE incidencias SET solucion = ?, estado = 'Resuelta', fecha_solucion = ? WHERE id = ?"
        cliente.execute(sql, (solucion_con_firma, fecha_solucion, id))
        cliente.close()
    except: pass
    return redirect(url_for('ver_detalle', id=id))

@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_incidencia(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("DELETE FROM incidencias WHERE id = ?", (id,))
        cliente.close()
    except: pass
    return redirect(url_for('inicio'))

@app.route('/exportar')
@login_required
def exportar_csv():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
    incidencias = resultado.rows
    cliente.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Problema', 'Equipo', 'Area', 'Categoria', 'Descripcion', 'Prioridad', 'Estado', 'Reportado Por', 'Solucion', 'Fecha Reporte', 'Fecha Solucion'])
    for item in incidencias: writer.writerow(item)
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=Reporte_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.route('/exportar_pdf')
@login_required
def exportar_pdf():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    resultado = cliente.execute("SELECT id, titulo, equipo, categoria, estado, prioridad, reportado_por FROM incidencias ORDER BY id DESC")
    incidencias = resultado.rows
    cliente.close()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = [Paragraph("LocalDesk - Reporte de Incidencias", ParagraphStyle('Titulo', parent=getSampleStyleSheet()['Heading1'], fontName='Helvetica-Bold', fontSize=22, textColor=colors.HexColor('#1D1D1F'), spaceAfter=4))]
    data = [["ID", "Problema", "Equipo", "Categoría", "Estado", "Prioridad", "Reportado"]]
    for item in incidencias: data.append([str(item[0]), str(item[1]), str(item[2]), str(item[3]), str(item[4]), str(item[5]), str(item[6])])
    tabla = Table(data, colWidths=[30, 140, 75, 65, 65, 65, 100])
    tabla.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0071E3')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, 0), 9), ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F7')), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E5EA'))]))
    elementos.append(tabla)
    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename=Reporte_{datetime.now().strftime('%Y%m%d')}.pdf"})

@app.route('/diagnostico_red', methods=['POST'])
@login_required
def diagnostico_red():
    data = request.get_json()
    host = data.get('host', '').strip()
    if not host: return jsonify({'status': 'error', 'message': 'IP o Hostname vacío'})
    parametro = '-n' if platform.system().lower() == 'windows' else '-c'
    comando = ['ping', parametro, '1', host]
    try:
        resultado = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if resultado.returncode == 0: return jsonify({'status': 'online', 'message': f'¡En línea! El equipo responde.'})
        else: return jsonify({'status': 'offline', 'message': f'Desconectado. No hay respuesta.'})
    except: return jsonify({'status': 'error', 'message': 'Error de red.'})

@app.route('/areas')
@login_required
def vista_areas():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        sql = "SELECT area, COUNT(id) as total, SUM(CASE WHEN estado != 'Resuelta' THEN 1 ELSE 0 END) as pendientes FROM incidencias GROUP BY area ORDER BY area ASC"
        areas = cliente.execute(sql).rows
        cliente.close()
    except: areas = []
    return render_template('areas.html', areas=areas)

@app.route('/area/<nombre_area>')
@login_required
def detalle_area(nombre_area):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        incidencias = cliente.execute("SELECT * FROM incidencias WHERE area = ? ORDER BY id DESC", (nombre_area,)).rows
        cliente.close()
    except: incidencias = []
    return render_template('area_detalle.html', incidencias=incidencias, area=nombre_area)

@app.route('/tecnicos', methods=['GET', 'POST'])
@login_required
def gestion_tecnicos():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        usuario_nick = request.form.get('usuario')
        email = request.form.get('email')
        password = request.form.get('password')
        rol = request.form.get('rol')
        password_segura = generate_password_hash(password)
        try:
            sql = "INSERT INTO usuarios (nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, ?)"
            cliente.execute(sql, (nombre, usuario_nick, email, password_segura, rol))
        except Exception as e: print(e)
        return redirect(url_for('gestion_tecnicos'))
        
    try: tecnicos = cliente.execute("SELECT id, nombre, usuario, email, rol FROM usuarios ORDER BY id DESC").rows
    except: tecnicos = []
    cliente.close()
    return render_template('tecnicos.html', tecnicos=tecnicos)

@app.route('/eliminar_tecnico/<int:id>', methods=['POST'])
@login_required
def eliminar_tecnico(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        if id != 1: cliente.execute("DELETE FROM usuarios WHERE id = ?", (id,))
        cliente.close()
    except: pass
    return redirect(url_for('gestion_tecnicos'))

if __name__ == '__main__':
    app.run(debug=True)