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
from werkzeug.utils import secure_filename

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secreto_futurista_123")

app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logeado' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# NOTIFICACIONES GLOBALES (CAMPANITA)
# ==========================================
@app.context_processor
def inyectar_notificaciones():
    if 'logeado' in session:
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            res = cliente.execute("SELECT COUNT(id) FROM notificaciones WHERE usuario_id = ? AND leida = 0", (session['id_usuario'],))
            pendientes = res.rows[0][0] if res.rows else 0
            cliente.close()
            return dict(noti_pendientes=pendientes)
        except: return dict(noti_pendientes=0)
    return dict(noti_pendientes=0)

@app.route('/api/notificaciones_count')
@login_required
def api_notificaciones_count():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        res = cliente.execute("SELECT COUNT(id) FROM notificaciones WHERE usuario_id = ? AND leida = 0", (session['id_usuario'],))
        pendientes = res.rows[0][0] if res.rows else 0
        cliente.close()
        return jsonify({'count': pendientes})
    except:
        return jsonify({'count': 0})

@app.route('/notificaciones')
@login_required
def centro_notificaciones():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE notificaciones SET leida = 1 WHERE usuario_id = ?", (session['id_usuario'],))
        res = cliente.execute("SELECT texto, enlace, fecha FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC LIMIT 20", (session['id_usuario'],))
        notifs = res.rows
        cliente.close()
    except: notifs = []
    return render_template('notificaciones.html', notificaciones=notifs)

# ==========================================
# AUTENTICACIÓN Y PERFIL
# ==========================================
def enviar_codigo_registro(destinatario, codigo, nombre_usuario):
    msg = MIMEMultipart('alternative')
    msg['From'] = f'"LocalDesk Soporte" <{MAIL_USERNAME}>' 
    msg['To'] = destinatario
    msg['Subject'] = "Verifica tu cuenta - LocalDesk"
    cuerpo_html = f"""<!DOCTYPE html><html lang="es"><head><style>body {{ font-family: sans-serif; background-color: #F5F5F7; padding: 40px; text-align: center; }} .box {{ background: white; padding: 40px; border-radius: 12px; }} .code {{ font-size: 32px; letter-spacing: 8px; color: #0071E3; background: #F5F5F7; padding: 16px; border-radius: 8px; display: inline-block; font-weight: bold; margin: 24px 0; }}</style></head><body><div class="box"><h2 style="color: #1D1D1F;">Hola, {nombre_usuario}</h2><p style="color: #86868B;">Utiliza este código para activar tu cuenta.</p><div class="code">{codigo}</div></div></body></html>"""
    msg.attach(MIMEText(cuerpo_html, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except: return False

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            user_data = cliente.execute("SELECT id, nombre, usuario, password, rol, email, telefono, foto FROM usuarios WHERE email = ?", (request.form.get('email'),)).rows
            cliente.close()
            if user_data and check_password_hash(user_data[0][3], request.form.get('password')):
                session['logeado'], session['id_usuario'], session['nombre'], session['usuario'], session['rol'], session['email'], session['foto'] = True, user_data[0][0], user_data[0][1], user_data[0][2], user_data[0][4], user_data[0][5], user_data[0][7]
                return redirect(url_for('inicio'))
            else: flash('Correo o contraseña incorrectos.', 'danger')
        except: flash('Error de conexión.', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre, usuario, email, password = request.form.get('nombre'), request.form.get('usuario'), request.form.get('email'), request.form.get('password')
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            if cliente.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).rows:
                cliente.close()
                flash('Este correo ya está registrado.', 'danger')
                return redirect(url_for('registro'))
            cliente.close()
        except: pass

        session['reg_temp'] = { 'nombre': nombre, 'usuario': usuario, 'email': email, 'password': generate_password_hash(password), 'otp': str(random.randint(100000, 999999)) }
        if enviar_codigo_registro(email, session['reg_temp']['otp'], nombre): return redirect(url_for('verificar_registro'))
        else: flash('Error al enviar el correo.', 'danger')
    return render_template('registro.html')

@app.route('/verificar_registro', methods=['GET', 'POST'])
def verificar_registro():
    if 'reg_temp' not in session: return redirect(url_for('registro'))
    if request.method == 'POST':
        if request.form.get('codigo') == session['reg_temp']['otp']:
            datos = session['reg_temp']
            try:
                cliente = libsql_client.create_client_sync(url=url, auth_token=token)
                cliente.execute("INSERT INTO usuarios (nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, 'Soporte Técnico')", (datos['nombre'], datos['usuario'], datos['email'], datos['password']))
                cliente.close()
                session.pop('reg_temp', None)
                flash('¡Cuenta verificada!', 'success')
                return redirect(url_for('login'))
            except: flash('Error en BD.', 'danger')
        else: flash('Código incorrecto.', 'danger')
    return render_template('verificar_registro.html', email=session['reg_temp']['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    if request.method == 'POST':
        try:
            cliente.execute("UPDATE usuarios SET telefono = ?, foto = ? WHERE id = ?", (request.form.get('telefono'), request.form.get('foto'), session.get('id_usuario')))
            session['foto'] = request.form.get('foto')
        except: pass
        return redirect(url_for('perfil'))
    datos_perfil = cliente.execute("SELECT nombre, usuario, email, rol, telefono, foto FROM usuarios WHERE id = ?", (session.get('id_usuario'),)).rows[0]
    cliente.close()
    return render_template('perfil.html', perfil=datos_perfil)

# ==========================================
# MENSAJERÍA DIRECTA (CHAT INTERNO)
# ==========================================
@app.route('/chat')
@app.route('/chat/<int:dest_id>')
@login_required
def chat_interno(dest_id=None):
    mi_id = session.get('id_usuario')
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    
    usuarios = cliente.execute("SELECT id, nombre, rol, foto FROM usuarios WHERE id != ? ORDER BY nombre ASC", (mi_id,)).rows
    mensajes = []
    destinatario = None
    
    if dest_id:
        dest_data = cliente.execute("SELECT nombre, rol, foto FROM usuarios WHERE id = ?", (dest_id,)).rows
        if dest_data:
            destinatario = {'id': dest_id, 'nombre': dest_data[0][0], 'rol': dest_data[0][1], 'foto': dest_data[0][2]}
            sql = """
                SELECT m.mensaje, m.archivo, m.fecha, m.remitente_id, u.nombre, u.foto 
                FROM mensajes_privados m
                JOIN usuarios u ON m.remitente_id = u.id
                WHERE (m.remitente_id = ? AND m.destinatario_id = ?) 
                   OR (m.remitente_id = ? AND m.destinatario_id = ?)
                ORDER BY m.fecha ASC
            """
            mensajes = cliente.execute(sql, (mi_id, dest_id, dest_id, mi_id)).rows
            
    cliente.close()
    return render_template('chat.html', usuarios=usuarios, mensajes=mensajes, destinatario=destinatario, mi_id=mi_id)

@app.route('/enviar_privado/<int:dest_id>', methods=['POST'])
@login_required
def enviar_privado(dest_id):
    mi_id = session.get('id_usuario')
    mensaje = request.form.get('mensaje')
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    archivo_url = None
    if 'archivo' in request.files:
        file = request.files['archivo']
        if file.filename != '':
            filename = secure_filename(file.filename)
            filename = f"{int(datetime.now().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            archivo_url = f"/static/uploads/{filename}"
            
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("INSERT INTO mensajes_privados (remitente_id, destinatario_id, mensaje, archivo, fecha) VALUES (?, ?, ?, ?, ?)", (mi_id, dest_id, mensaje, archivo_url, fecha))
        texto_noti = f"Tienes un nuevo mensaje privado de {session.get('nombre')}"
        enlace = f"/chat/{mi_id}"
        cliente.execute("INSERT INTO notificaciones (usuario_id, texto, enlace, fecha) VALUES (?, ?, ?, ?)", (dest_id, texto_noti, enlace, fecha))
        cliente.close()
    except Exception as e: print(e)
    
    return redirect(url_for('chat_interno', dest_id=dest_id))

@app.route('/vaciar_chat/<int:dest_id>', methods=['POST'])
@login_required
def vaciar_chat(dest_id):
    mi_id = session.get('id_usuario')
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        sql = "DELETE FROM mensajes_privados WHERE (remitente_id = ? AND destinatario_id = ?) OR (remitente_id = ? AND destinatario_id = ?)"
        cliente.execute(sql, (mi_id, dest_id, dest_id, mi_id))
        cliente.close()
    except: pass
    return redirect(url_for('chat_interno', dest_id=dest_id))

# ==========================================
# RUTAS DEL SISTEMA PRINCIPAL (INCIDENCIAS)
# ==========================================
@app.route('/')
@login_required
def inicio():
    busqueda = request.args.get('q', '')
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        todas = cliente.execute("SELECT * FROM incidencias").rows
        stats = {
            'total': len(todas), 'pendientes': sum(1 for i in todas if i[7] == 'Pendiente'),
            'revision': sum(1 for i in todas if i[7] == 'En revisión'), 'resueltas': sum(1 for i in todas if i[7] == 'Resuelta')
        }
        categorias = { 'Hardware': sum(1 for i in todas if i[4] == 'Hardware'), 'Software': sum(1 for i in todas if i[4] == 'Software'), 'Red': sum(1 for i in todas if i[4] == 'Red'), 'Otro': sum(1 for i in todas if i[4] == 'Otro') }
        if busqueda:
            lista_incidencias = cliente.execute("SELECT * FROM incidencias WHERE CAST(id AS TEXT) LIKE ? OR titulo LIKE ? OR equipo LIKE ? OR reportado_por LIKE ? ORDER BY id DESC", (f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%")).rows
        else: lista_incidencias = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC").rows
        cliente.close()
    except:
        lista_incidencias = []
        stats, categorias = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}, {'Hardware': 0, 'Software': 0, 'Red': 0, 'Otro': 0}
    return render_template('index.html', incidencias=lista_incidencias, stats=stats, categorias=json.dumps(categorias), busqueda=busqueda)

@app.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_registro():
    if request.method == 'POST':
        try:
            cliente = libsql_client.create_client_sync(url=url, auth_token=token)
            cliente.execute("INSERT INTO incidencias (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte) VALUES (?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)", (request.form['titulo'], request.form['equipo'], request.form['area'], request.form['categoria'], request.form['descripcion'], request.form['prioridad'], request.form['reportado_por'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            cliente.close()
        except: pass
        return redirect(url_for('inicio'))
    return render_template('nuevo.html')

@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        incidencia = cliente.execute("SELECT * FROM incidencias WHERE id = ?", (id,)).rows[0]
        mensajes = cliente.execute("SELECT m.mensaje, m.tipo, m.fecha, u.nombre, u.foto, u.rol, m.archivo FROM mensajes m JOIN usuarios u ON m.usuario_id = u.id WHERE m.incidencia_id = ? ORDER BY m.fecha ASC", (id,)).rows
        cliente.close()
        return render_template('detalle.html', incidencia=incidencia, mensajes=mensajes)
    except: return "<h1>Error: Incidencia no encontrada</h1>", 404

@app.route('/enviar_mensaje/<int:id>', methods=['POST'])
@login_required
def enviar_mensaje(id):
    archivo_url = None
    if 'archivo' in request.files and request.files['archivo'].filename != '':
        file = request.files['archivo']
        filename = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        archivo_url = f"/static/uploads/{filename}"
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("INSERT INTO mensajes (incidencia_id, usuario_id, mensaje, tipo, archivo, fecha) VALUES (?, ?, ?, ?, ?, ?)", (id, session.get('id_usuario'), request.form.get('mensaje'), request.form.get('tipo', 'chat'), archivo_url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cliente.execute("INSERT INTO notificaciones (usuario_id, texto, enlace, fecha) VALUES (1, ?, ?, ?)", (f"{session.get('nombre')} actualizó el Ticket #{id}", f"/incidencia/{id}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cliente.close()
    except: pass
    return redirect(url_for('ver_detalle', id=id))

@app.route('/actualizar_estado/<int:id>', methods=['POST'])
@login_required
def actualizar_estado(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE incidencias SET estado = ? WHERE id = ?", (request.form['nuevo_estado'], id))
        cliente.close()
    except: pass
    return redirect(url_for('ver_detalle', id=id))

@app.route('/resolver/<int:id>', methods=['POST'])
@login_required
def resolver_incidencia(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE incidencias SET solucion = ?, estado = 'Resuelta', fecha_solucion = ? WHERE id = ?", (f"{request.form['solucion']}\n\n✅ Atendido por: {session.get('nombre')} ({session.get('rol')})", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id))
        cliente.close()
    except: pass
    return redirect(url_for('ver_detalle', id=id))

@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_incidencia(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("DELETE FROM incidencias WHERE id = ?", (id,))
        cliente.execute("DELETE FROM mensajes WHERE incidencia_id = ?", (id,))
        cliente.close()
    except: pass
    return redirect(url_for('inicio'))


# ==========================================
# REPORTE PDF - ESTILO CORPORATIVO AVANZADO
# ==========================================
@app.route('/exportar_pdf')
@login_required
def exportar_pdf():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    incidencias = cliente.execute("SELECT id, titulo, equipo, categoria, estado, prioridad, reportado_por FROM incidencias ORDER BY id DESC").rows
    cliente.close()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=40)
    elementos = []
    estilos = getSampleStyleSheet()
    
    # 1. Bloque de título principal (fondo azul, texto blanco)
    titulo_data = [[Paragraph("<font color='white'><b>Reporte General de Incidencias - LocalDesk</b></font>", ParagraphStyle('Tit', parent=estilos['Normal'], fontSize=16, alignment=0))]]
    tabla_titulo = Table(titulo_data, colWidths=[550])
    tabla_titulo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#23a5f7')), # Azul claro estilo reporte
        ('PADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
    ]))
    elementos.append(tabla_titulo)
    elementos.append(Spacer(1, 20))
    
    # 2. Subtítulo y Fecha (Separados del título principal)
    fecha_actual = datetime.now().strftime("%d/%m/%Y")
    hora_actual = datetime.now().strftime("%H:%M")
    
    info_data = [
        [Paragraph("<font color='#40c0cb'><b>Detalle de Incidencias Registradas</b></font>", ParagraphStyle('Sub', parent=estilos['Normal'], fontSize=12))],
        [Paragraph(f"<font color='#808080'>Generado el: {fecha_actual} a las {hora_actual}</font>", ParagraphStyle('Fec', parent=estilos['Normal'], fontSize=9))]
    ]
    tabla_info = Table(info_data, colWidths=[550])
    tabla_info.setStyle(TableStyle([('PADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 5)]))
    elementos.append(tabla_info)
    elementos.append(Spacer(1, 15))
    
    # 3. Preparación de datos de la tabla con colores en los estados
    data = [["ID", "PROBLEMA", "EQUIPO", "CATEGORÍA", "ESTADO", "PRIORIDAD", "REPORTADO POR"]]
    
    for item in incidencias:
        titulo = str(item[1])
        if len(titulo) > 22: titulo = titulo[:19] + "..."
        
        # Aplicar colores llamativos al estado
        estado_texto = str(item[4])
        if estado_texto == 'Resuelta':
            estado_formateado = Paragraph("<font color='#34C759'><b>Resuelta</b></font>", estilos['Normal'])
        elif estado_texto == 'En revisión':
            estado_formateado = Paragraph("<font color='#FF9500'><b>En revisión</b></font>", estilos['Normal'])
        else:
            estado_formateado = Paragraph("<font color='#FF3B30'><b>Pendiente</b></font>", estilos['Normal'])
            
        data.append([str(item[0]), titulo, str(item[2]), str(item[3]), estado_formateado, str(item[5]), str(item[6])])
        
    tabla = Table(data, colWidths=[25, 120, 80, 75, 75, 65, 110])
    
    # 4. Estilos de tabla intercalada fina
    estilo_tabla = TableStyle([
        # Cabecera (Azul muy claro con texto azul oscuro/grisáceo)
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dcf2f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#5c8c9e')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        # Contenido
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        
        # Líneas de cuadrícula muy finas y claras
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e6e6e6')),
    ])
    
    # Color de fondo intercalado para las filas
    for i in range(1, len(data)):
        if i % 2 == 0:
            estilo_tabla.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f9f9f9'))
            
    tabla.setStyle(estilo_tabla)
    elementos.append(tabla)
    
    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype="application/pdf", headers={"Content-Disposition": f"attachment;filename=Reporte_LocalDesk.pdf"})


@app.route('/exportar')
@login_required
def exportar_csv():
    cliente = libsql_client.create_client_sync(url=url, auth_token=token)
    incidencias = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC").rows
    cliente.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Problema', 'Equipo', 'Area', 'Categoria', 'Descripcion', 'Prioridad', 'Estado', 'Reportado Por', 'Solucion', 'Fecha Reporte', 'Fecha Solucion'])
    for item in incidencias: writer.writerow(item)
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=Reporte.csv"})

@app.route('/areas')
@login_required
def vista_areas():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        areas = cliente.execute("SELECT area, COUNT(id) as total, SUM(CASE WHEN estado != 'Resuelta' THEN 1 ELSE 0 END) as pendientes FROM incidencias GROUP BY area ORDER BY area ASC").rows
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
        try: cliente.execute("INSERT INTO usuarios (nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, ?)", (request.form.get('nombre'), request.form.get('usuario'), request.form.get('email'), generate_password_hash(request.form.get('password')), request.form.get('rol')))
        except: pass
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