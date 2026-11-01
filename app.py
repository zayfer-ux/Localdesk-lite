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
# RUTAS DEL SISTEMA PRINCIPAL (INCIDENCIAS V2.0)
# ==========================================
@app.route('/')
@login_required
def inicio():
    busqueda = request.args.get('q', '')
    try:
        cliente = get_db()
        
        # Consultar con JOINs para obtener nombres de áreas y categorías en lugar de sus IDs
        query_base = """
            SELECT i.id, i.numero, i.titulo, i.activo_ubicacion, 
                   a.nombre as area, c.nombre as categoria, 
                   i.prioridad, i.estado, u.nombre as solicitante, i.fecha_reporte
            FROM incidencias i
            JOIN areas a ON i.area_id = a.id
            JOIN categorias c ON i.categoria_id = c.id
            JOIN usuarios u ON i.solicitante_id = u.id
            WHERE i.org_id = ?
        """
        parametros = [org_id()]

        if busqueda:
            query_base += " AND (CAST(i.numero AS TEXT) LIKE ? OR i.titulo LIKE ? OR i.activo_ubicacion LIKE ? OR u.nombre LIKE ?)"
            parametros.extend([f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"])
            
        query_base += " ORDER BY i.numero DESC"
        
        lista_incidencias = cliente.execute(query_base, parametros).rows
        
        # Estadísticas exclusivas de esta empresa
        todas = cliente.execute("SELECT i.estado, c.nombre FROM incidencias i JOIN categorias c ON i.categoria_id = c.id WHERE i.org_id = ?", (org_id(),)).rows
        
        stats = {
            'total': len(todas),
            'pendientes': sum(1 for i in todas if i[0] == 'Pendiente'),
            'revision': sum(1 for i in todas if i[0] == 'En revisión'),
            'resueltas': sum(1 for i in todas if i[0] == 'Resuelta')
        }
        
        categorias_stats = {}
        for i in todas:
            cat = i[1]
            categorias_stats[cat] = categorias_stats.get(cat, 0) + 1
            
        cliente.close()
    except Exception as e:
        print("Error en inicio:", e)
        lista_incidencias = []
        stats = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}
        categorias_stats = {}

    return render_template('index.html', incidencias=lista_incidencias, stats=stats, categorias=json.dumps(categorias_stats), busqueda=busqueda)

@app.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_registro():
    cliente = get_db()
    if request.method == 'POST':
        try:
            # Calcular el siguiente número consecutivo de la empresa (LD-XXXX)
            res_max = cliente.execute("SELECT MAX(numero) FROM incidencias WHERE org_id = ?", (org_id(),)).rows
            siguiente_numero = (res_max[0][0] or 0) + 1 if res_max else 1

            cliente.execute("""
                INSERT INTO incidencias (org_id, numero, titulo, activo_ubicacion, area_id, categoria_id, descripcion, prioridad, estado, solicitante_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)
            """, (org_id(), siguiente_numero, request.form['titulo'], request.form['activo_ubicacion'], 
                  request.form['area_id'], request.form['categoria_id'], request.form['descripcion'], 
                  request.form['prioridad'], session['id_usuario']))
            
            # Registrar en la nueva tabla de historial
            res_id = cliente.execute("SELECT last_insert_rowid()").rows
            nuevo_id = res_id[0][0]
            cliente.execute("INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion) VALUES (?, ?, ?, ?)",
                            (org_id(), nuevo_id, session['id_usuario'], 'Ticket Creado'))

            cliente.close()
            return redirect(url_for('inicio'))
        except Exception as e:
            print("Error al crear:", e)
            flash('Error al crear el ticket', 'danger')

    # Cargar áreas y categorías dinámicas para el formulario HTML
    areas = cliente.execute("SELECT id, nombre FROM areas WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    categorias = cliente.execute("SELECT id, nombre FROM categorias WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    cliente.close()
    return render_template('nuevo.html', areas=areas, categorias=categorias)

@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    try:
        cliente = get_db()
        # 1. Seguridad: Validar que el ticket pertenezca a la empresa
        incidencia_raw = cliente.execute("""
            SELECT i.id, i.numero, i.titulo, i.activo_ubicacion, 
                   a.nombre as area, c.nombre as categoria, 
                   i.prioridad, i.estado, u.nombre as solicitante, i.solucion, i.fecha_reporte, i.fecha_solucion, i.descripcion
            FROM incidencias i
            JOIN areas a ON i.area_id = a.id
            JOIN categorias c ON i.categoria_id = c.id
            JOIN usuarios u ON i.solicitante_id = u.id
            WHERE i.id = ? AND i.org_id = ?
        """, (id, org_id())).rows
        
        if not incidencia_raw:
            cliente.close()
            return "<h1>Error 404: Incidencia no encontrada o no pertenece a tu empresa</h1>", 404
            
        incidencia = incidencia_raw[0]
        
        # 2. Consultar mensajes del chat aislando las notas internas para los Solicitantes
        query_mensajes = """
            SELECT m.mensaje, m.es_nota_interna, m.fecha, u.nombre, u.foto, u.rol, m.archivo 
            FROM mensajes m 
            JOIN usuarios u ON m.usuario_id = u.id 
            WHERE m.incidencia_id = ? AND m.org_id = ?
        """
        
        if session.get('rol') == 'Solicitante':
            query_mensajes += " AND m.es_nota_interna = 0"
            
        query_mensajes += " ORDER BY m.fecha ASC"
        
        mensajes = cliente.execute(query_mensajes, (id, org_id())).rows
        cliente.close()
        return render_template('detalle.html', incidencia=incidencia, mensajes=mensajes)
    except Exception as e:
        print(e)
        return "<h1>Error interno</h1>", 500

@app.route('/enviar_mensaje/<int:id>', methods=['POST'])
@login_required
def enviar_mensaje(id):
    archivo_url = None
    if 'archivo' in request.files and request.files['archivo'].filename != '':
        file = request.files['archivo']
        filename = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        archivo_url = f"/static/uploads/{filename}"
        
    tipo = request.form.get('tipo', 'chat')
    es_nota = 1 if tipo == 'nota' else 0
    
    # Validar permisos estrictos para crear nota interna
    if es_nota and session.get('rol') == 'Solicitante':
        flash('No tienes permisos para crear notas internas.', 'danger')
        return redirect(url_for('ver_detalle', id=id))

    try:
        cliente = get_db()
        check = cliente.execute("SELECT id FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id())).rows
        if check:
            cliente.execute("""
                INSERT INTO mensajes (org_id, incidencia_id, usuario_id, mensaje, es_nota_interna, archivo) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (org_id(), id, session.get('id_usuario'), request.form.get('mensaje'), es_nota, archivo_url))
            
            cliente.execute("INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion) VALUES (?, ?, ?, ?)",
                            (org_id(), id, session['id_usuario'], 'Mensaje agregado'))
        cliente.close()
    except Exception as e: print(e)
    return redirect(url_for('ver_detalle', id=id))

@app.route('/actualizar_estado/<int:id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def actualizar_estado(id):
    nuevo_estado = request.form['nuevo_estado']
    try:
        cliente = get_db()
        check = cliente.execute("SELECT estado FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id())).rows
        if check and check[0][0] != nuevo_estado:
            cliente.execute("UPDATE incidencias SET estado = ? WHERE id = ? AND org_id = ?", (nuevo_estado, id, org_id()))
            cliente.execute("INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                            (org_id(), id, session['id_usuario'], 'Cambio de estado', f"A {nuevo_estado}"))
        cliente.close()
    except Exception as e: print(e)
    return redirect(url_for('ver_detalle', id=id))

@app.route('/resolver/<int:id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def resolver_incidencia(id):
    try:
        cliente = get_db()
        cliente.execute("""
            UPDATE incidencias 
            SET solucion = ?, estado = 'Resuelta', fecha_solucion = CURRENT_TIMESTAMP, resuelto_por = ? 
            WHERE id = ? AND org_id = ?
        """, (f"{request.form['solucion']}\n\n✅ Atendido por: {session.get('nombre')} ({session.get('rol')})", session.get('id_usuario'), id, org_id()))
        
        cliente.execute("INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion) VALUES (?, ?, ?, ?)",
                            (org_id(), id, session['id_usuario'], 'Ticket Resuelto'))
        cliente.close()
    except Exception as e: print(e)
    return redirect(url_for('ver_detalle', id=id))
    
@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def eliminar_incidencia(id):
    try:
        cliente = get_db()
        cliente.execute("DELETE FROM mensajes WHERE incidencia_id = ? AND org_id = ?", (id, org_id()))
        cliente.execute("DELETE FROM historial_incidencias WHERE incidencia_id = ? AND org_id = ?", (id, org_id()))
        cliente.execute("DELETE FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id()))
        cliente.close()
    except Exception as e: print(e)
    return redirect(url_for('inicio'))

# RUTAS PENDIENTES DE ADAPTAR (PASO 6, 7 y 8)
@app.route('/exportar_pdf')
@login_required
def exportar_pdf(): return "Fase 8 en construcción..."
@app.route('/exportar')
@login_required
def exportar_csv(): return "Fase 8 en construcción..."
@app.route('/areas')
@login_required
def vista_areas(): return "Fase 8 en construcción..."
@app.route('/tecnicos', methods=['GET', 'POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def gestion_tecnicos(): return render_template('tecnicos.html', tecnicos=[])

if __name__ == '__main__':
    app.run(debug=True)