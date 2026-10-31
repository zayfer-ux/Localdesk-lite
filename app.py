import os
import io
import csv
import string
import random
import smtplib
from datetime import datetime
import json
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
import libsql_client
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secreto_futurista_123")

app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==========================================
# FUNCIONES BASE MULTI-EMPRESA (V2.0)
# ==========================================
def get_db():
    return libsql_client.create_client_sync(url=url, auth_token=token)

def org_id():
    return session.get('org_id')

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logeado' not in session:
                return redirect(url_for('login'))
            if session.get('rol') not in roles:
                flash('Acceso denegado: Tu rol no tiene permisos para esta acción.', 'danger')
                return redirect(url_for('inicio'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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
            cliente = get_db()
            res = cliente.execute("SELECT COUNT(id) FROM notificaciones WHERE org_id = ? AND usuario_id = ? AND leida = 0", (org_id(), session['id_usuario'])).rows
            pendientes = res[0][0] if res else 0
            cliente.close()
            return dict(noti_pendientes=pendientes)
        except: return dict(noti_pendientes=0)
    return dict(noti_pendientes=0)

@app.route('/api/notificaciones_count')
@login_required
def api_notificaciones_count():
    try:
        cliente = get_db()
        res = cliente.execute("SELECT COUNT(id) FROM notificaciones WHERE org_id = ? AND usuario_id = ? AND leida = 0", (org_id(), session['id_usuario'])).rows
        pendientes = res[0][0] if res else 0
        cliente.close()
        return jsonify({'count': pendientes})
    except:
        return jsonify({'count': 0})

@app.route('/notificaciones')
@login_required
def centro_notificaciones():
    try:
        cliente = get_db()
        cliente.execute("UPDATE notificaciones SET leida = 1 WHERE org_id = ? AND usuario_id = ?", (org_id(), session['id_usuario']))
        res = cliente.execute("SELECT texto, enlace, fecha FROM notificaciones WHERE org_id = ? AND usuario_id = ? ORDER BY id DESC LIMIT 20", (org_id(), session['id_usuario'])).rows
        notifs = res
        cliente.close()
    except: notifs = []
    return render_template('notificaciones.html', notificaciones=notifs)

# ==========================================
# AUTENTICACIÓN Y REGISTRO (V2.0 - MULTI-EMPRESA)
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
            cliente = get_db()
            user_data = cliente.execute("SELECT id, org_id, nombre, usuario, password, rol, email, telefono, foto FROM usuarios WHERE email = ?", (request.form.get('email'),)).rows
            cliente.close()
            if user_data and check_password_hash(user_data[0][4], request.form.get('password')):
                session['logeado'] = True
                session['id_usuario'] = user_data[0][0]
                session['org_id'] = user_data[0][1]
                session['nombre'] = user_data[0][2]
                session['usuario'] = user_data[0][3]
                session['rol'] = user_data[0][5]
                session['email'] = user_data[0][6]
                session['foto'] = user_data[0][8]
                return redirect(url_for('inicio'))
            else: flash('Correo o contraseña incorrectos.', 'danger')
        except Exception as e:
            print(e)
            flash('Error de conexión con la base de datos.', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        tipo_registro = request.form.get('tipo_registro') # 'crear' o 'unirse'
        codigo_invitacion = request.form.get('codigo_invitacion')
        nombre_empresa = request.form.get('nombre_empresa')
        
        nombre = request.form.get('nombre')
        usuario = request.form.get('usuario')
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            cliente = get_db()
            if cliente.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).rows:
                cliente.close()
                flash('Este correo ya está registrado.', 'danger')
                return redirect(url_for('registro'))
                
            org_id_unirse = None
            if tipo_registro == 'unirse':
                res_org = cliente.execute("SELECT id FROM organizaciones WHERE codigo_invitacion = ?", (codigo_invitacion,)).rows
                if not res_org:
                    cliente.close()
                    flash('Código de invitación inválido o no existe.', 'danger')
                    return redirect(url_for('registro'))
                org_id_unirse = res_org[0][0]
            cliente.close()
        except Exception as e:
            print(e)
            flash('Error al conectar con la base de datos.', 'danger')
            return redirect(url_for('registro'))

        session['reg_temp'] = { 
            'tipo_registro': tipo_registro,
            'codigo_invitacion': codigo_invitacion,
            'nombre_empresa': nombre_empresa,
            'org_id_unirse': org_id_unirse,
            'nombre': nombre, 
            'usuario': usuario, 
            'email': email, 
            'password': generate_password_hash(password), 
            'otp': str(random.randint(100000, 999999)) 
        }
        if enviar_codigo_registro(email, session['reg_temp']['otp'], nombre): 
            return redirect(url_for('verificar_registro'))
        else: flash('Error al enviar el correo.', 'danger')
    return render_template('registro.html')

@app.route('/verificar_registro', methods=['GET', 'POST'])
def verificar_registro():
    if 'reg_temp' not in session: return redirect(url_for('registro'))
    if request.method == 'POST':
        if request.form.get('codigo') == session['reg_temp']['otp']:
            datos = session['reg_temp']
            try:
                cliente = get_db()
                if datos['tipo_registro'] == 'crear':
                    # Generar código aleatorio de 8 caracteres
                    codigo_inv = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    res_org = cliente.execute("INSERT INTO organizaciones (nombre, codigo_invitacion) VALUES (?, ?) RETURNING id", (datos['nombre_empresa'], codigo_inv)).rows
                    nuevo_org_id = res_org[0][0]
                    
                    # El creador es Propietario
                    cliente.execute("INSERT INTO usuarios (org_id, nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, ?, 'Propietario')", (nuevo_org_id, datos['nombre'], datos['usuario'], datos['email'], datos['password']))
                    
                    # Generar configuración base de la empresa
                    for cat in ['Hardware', 'Software', 'Red', 'Otro']:
                        cliente.execute("INSERT INTO categorias (org_id, nombre) VALUES (?, ?)", (nuevo_org_id, cat))
                    cliente.execute("INSERT INTO areas (org_id, nombre) VALUES (?, 'General')", (nuevo_org_id,))
                    
                elif datos['tipo_registro'] == 'unirse':
                    # Entra como Solicitante por defecto
                    cliente.execute("INSERT INTO usuarios (org_id, nombre, usuario, email, password, rol) VALUES (?, ?, ?, ?, ?, 'Solicitante')", (datos['org_id_unirse'], datos['nombre'], datos['usuario'], datos['email'], datos['password']))
                    
                cliente.close()
                session.pop('reg_temp', None)
                flash('¡Cuenta creada y verificada con éxito!', 'success')
                return redirect(url_for('login'))
            except Exception as e: 
                print(e)
                flash('Error en BD al registrar la cuenta.', 'danger')
        else: flash('Código incorrecto.', 'danger')
    return render_template('verificar_registro.html', email=session['reg_temp']['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    cliente = get_db()
    if request.method == 'POST':
        try:
            cliente.execute("UPDATE usuarios SET telefono = ?, foto = ? WHERE id = ? AND org_id = ?", (request.form.get('telefono'), request.form.get('foto'), session.get('id_usuario'), org_id()))
            session['foto'] = request.form.get('foto')
        except: pass
        return redirect(url_for('perfil'))
    try:
        datos_perfil = cliente.execute("SELECT nombre, usuario, email, rol, telefono, foto FROM usuarios WHERE id = ? AND org_id = ?", (session.get('id_usuario'), org_id())).rows[0]
    except: datos_perfil = None
    cliente.close()
    return render_template('perfil.html', perfil=datos_perfil)

# ==========================================
# RUTAS EN TRANSICIÓN (No se caerán, pero se adaptarán en el Paso 5)
# ==========================================
@app.route('/chat')
@app.route('/chat/<int:dest_id>')
@login_required
def chat_interno(dest_id=None):
    return "Fase 5 en construcción..."

@app.route('/')
@login_required
def inicio():
    # Bloque try/except para evitar que la página se caiga con la nueva BD
    try:
        cliente = get_db()
        todas = cliente.execute("SELECT * FROM incidencias WHERE org_id = ?", (org_id(),)).rows
        cliente.close()
        stats = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}
        categorias = {'Hardware': 0, 'Software': 0, 'Red': 0, 'Otro': 0}
        return render_template('index.html', incidencias=[], stats=stats, categorias=json.dumps(categorias), busqueda='')
    except:
        stats = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}
        categorias = {'Hardware': 0, 'Software': 0, 'Red': 0, 'Otro': 0}
        return render_template('index.html', incidencias=[], stats=stats, categorias=json.dumps(categorias), busqueda='')

@app.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_registro():
    return render_template('nuevo.html')

@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    return "Fase 5 en construcción..."

@app.route('/exportar_pdf')
@login_required
def exportar_pdf():
    return "Fase 5 en construcción..."

@app.route('/exportar')
@login_required
def exportar_csv():
    return "Fase 5 en construcción..."

@app.route('/areas')
@login_required
def vista_areas():
    return render_template('areas.html', areas=[])

@app.route('/tecnicos', methods=['GET', 'POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def gestion_tecnicos():
    return render_template('tecnicos.html', tecnicos=[])

if __name__ == '__main__':
    app.run(debug=True)