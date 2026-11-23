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

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def archivo_imagen_valido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

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
                return "<h1>403 Forbidden: Tu rol no tiene permisos para acceder a esta sección.</h1>", 403
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
            res = cliente.execute(
                "SELECT COUNT(id) FROM notificaciones WHERE org_id = ? AND usuario_id = ? AND leida = 0",
                (org_id(), session['id_usuario'])
            ).rows
            pendientes = res[0][0] if res else 0
            cliente.close()
            return dict(noti_pendientes=pendientes)
        except Exception:
            return dict(noti_pendientes=0)
    return dict(noti_pendientes=0)

@app.route('/api/notificaciones_count')
@login_required
def api_notificaciones_count():
    try:
        cliente = get_db()
        res = cliente.execute(
            "SELECT COUNT(id) FROM notificaciones WHERE org_id = ? AND usuario_id = ? AND leida = 0",
            (org_id(), session['id_usuario'])
        ).rows
        pendientes = res[0][0] if res else 0
        cliente.close()
        return jsonify({'count': pendientes})
    except Exception:
        return jsonify({'count': 0})

@app.route('/notificaciones')
@login_required
def centro_notificaciones():
    try:
        cliente = get_db()
        cliente.execute(
            "UPDATE notificaciones SET leida = 1 WHERE org_id = ? AND usuario_id = ?",
            (org_id(), session['id_usuario'])
        )
        res = cliente.execute(
            "SELECT texto, enlace, fecha FROM notificaciones WHERE org_id = ? AND usuario_id = ? ORDER BY id DESC LIMIT 20",
            (org_id(), session['id_usuario'])
        ).rows
        notifs = res
        cliente.close()
    except Exception:
        notifs = []
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
    except Exception:
        return False

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            cliente = get_db()
            user_data = cliente.execute(
                "SELECT id, org_id, nombre, usuario, password, rol, email, telefono, foto, activo FROM usuarios WHERE email = ?",
                (request.form.get('email'),)
            ).rows
            cliente.close()
            if user_data and check_password_hash(user_data[0][4], request.form.get('password')):
                if user_data[0][9] == 0:
                    flash('Tu cuenta está desactivada. Contacta al administrador de tu empresa.', 'danger')
                    return render_template('login.html')
                session['logeado'] = True
                session['id_usuario'] = user_data[0][0]
                session['org_id'] = user_data[0][1]
                session['nombre'] = user_data[0][2]
                session['usuario'] = user_data[0][3]
                session['rol'] = user_data[0][5]
                session['email'] = user_data[0][6]
                session['foto'] = user_data[0][8]
                return redirect(url_for('inicio'))
            else:
                flash('Correo o contraseña incorrectos.', 'danger')
        except Exception as e:
            print(e)
            flash('Error de conexión con la base de datos.', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        tipo_registro = request.form.get('tipo_registro')
        codigo_invitacion = request.form.get('codigo_invitacion', '').strip().upper()
        nombre_empresa = request.form.get('nombre_empresa', '').strip()

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
                res_org = cliente.execute(
                    "SELECT id FROM organizaciones WHERE codigo_invitacion = ?",
                    (codigo_invitacion,)
                ).rows
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
        else:
            flash('Error al enviar el correo.', 'danger')
    return render_template('registro.html')

@app.route('/verificar_registro', methods=['GET', 'POST'])
def verificar_registro():
    if 'reg_temp' not in session:
        return redirect(url_for('registro'))
    if request.method == 'POST':
        if request.form.get('codigo') == session['reg_temp']['otp']:
            datos = session['reg_temp']
            try:
                cliente = get_db()
                if datos['tipo_registro'] == 'crear':
                    codigo_inv = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    res_org = cliente.execute(
                        "INSERT INTO organizaciones (nombre, codigo_invitacion) VALUES (?, ?) RETURNING id",
                        (datos['nombre_empresa'], codigo_inv)
                    ).rows
                    nuevo_org_id = res_org[0][0]
                    cliente.execute(
                        "INSERT INTO usuarios (org_id, nombre, usuario, email, password, rol, verificado) VALUES (?, ?, ?, ?, ?, 'Propietario', 1)",
                        (nuevo_org_id, datos['nombre'], datos['usuario'], datos['email'], datos['password'])
                    )
                    for cat in ['Hardware', 'Software', 'Red', 'Otro']:
                        cliente.execute(
                            "INSERT INTO categorias (org_id, nombre) VALUES (?, ?)",
                            (nuevo_org_id, cat)
                        )
                    cliente.execute(
                        "INSERT INTO areas (org_id, nombre) VALUES (?, 'General')",
                        (nuevo_org_id,)
                    )
                elif datos['tipo_registro'] == 'unirse':
                    cliente.execute(
                        "INSERT INTO usuarios (org_id, nombre, usuario, email, password, rol, verificado) VALUES (?, ?, ?, ?, ?, 'Solicitante', 1)",
                        (datos['org_id_unirse'], datos['nombre'], datos['usuario'], datos['email'], datos['password'])
                    )
                cliente.close()
                session.pop('reg_temp', None)
                flash('¡Cuenta creada y verificada con éxito!', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                print(e)
                flash('Error en BD al registrar la cuenta.', 'danger')
        else:
            flash('Código incorrecto.', 'danger')
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
            actual = cliente.execute(
                "SELECT foto FROM usuarios WHERE id = ? AND org_id = ?",
                (session.get('id_usuario'), org_id())
            ).rows
            nueva_foto = actual[0][0] if actual else None

            if request.form.get('eliminar_foto') == '1':
                nueva_foto = None
            elif 'foto_archivo' in request.files and request.files['foto_archivo'].filename != '':
                file = request.files['foto_archivo']
                if not archivo_imagen_valido(file.filename):
                    cliente.close()
                    flash('Formato de imagen no válido. Usa PNG, JPG, JPEG, WEBP o GIF.', 'danger')
                    return redirect(url_for('perfil'))
                filename = f"perfil_{session.get('id_usuario')}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                nueva_foto = f"/static/uploads/{filename}"
            elif request.form.get('foto_url', '').strip():
                nueva_foto = request.form.get('foto_url').strip()

            cliente.execute(
                "UPDATE usuarios SET telefono = ?, foto = ? WHERE id = ? AND org_id = ?",
                (request.form.get('telefono'), nueva_foto, session.get('id_usuario'), org_id())
            )
            session['foto'] = nueva_foto
            flash('Tu perfil se actualizó correctamente.', 'success')
        except Exception as e:
            print(e)
            flash('No se pudieron guardar los cambios.', 'danger')
        cliente.close()
        return redirect(url_for('perfil'))

    try:
        datos_perfil = cliente.execute(
            "SELECT nombre, usuario, email, rol, telefono, foto FROM usuarios WHERE id = ? AND org_id = ?",
            (session.get('id_usuario'), org_id())
        ).rows[0]
    except Exception:
        datos_perfil = None
    cliente.close()
    return render_template('perfil.html', perfil=datos_perfil)

# ==========================================
# CHAT INTERNO PRIVADO V2.0 (AISLADO POR EMPRESA)
# ==========================================
@app.route('/chat')
@app.route('/chat/<int:dest_id>')
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def chat_interno(dest_id=None):
    mi_id = session.get('id_usuario')
    try:
        cliente = get_db()
        usuarios = cliente.execute(
            "SELECT id, nombre, rol, foto FROM usuarios WHERE org_id = ? AND id != ? AND rol != 'Solicitante' ORDER BY nombre ASC",
            (org_id(), mi_id)
        ).rows

        mensajes = []
        destinatario = None

        if dest_id:
            dest_data = cliente.execute(
                "SELECT id, nombre, rol, foto FROM usuarios WHERE id = ? AND org_id = ? AND rol != 'Solicitante'",
                (dest_id, org_id())
            ).rows
            if dest_data:
                destinatario = {
                    'id': dest_data[0][0],
                    'nombre': dest_data[0][1],
                    'rol': dest_data[0][2],
                    'foto': dest_data[0][3]
                }

                sql = """
                    SELECT m.mensaje, m.archivo, m.fecha, m.de_usuario, u.nombre, u.foto 
                    FROM mensajes_privados m
                    JOIN usuarios u ON m.de_usuario = u.id
                    WHERE m.org_id = ? AND ((m.de_usuario = ? AND m.a_usuario = ?) OR (m.de_usuario = ? AND m.a_usuario = ?))
                    ORDER BY m.fecha ASC
                """
                mensajes = cliente.execute(sql, (org_id(), mi_id, dest_id, dest_id, mi_id)).rows
        cliente.close()
    except Exception as e:
        print(e)
        usuarios, mensajes, destinatario = [], [], None

    return render_template('chat.html', usuarios=usuarios, mensajes=mensajes, destinatario=destinatario, mi_id=mi_id)

@app.route('/enviar_privado/<int:dest_id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def enviar_privado(dest_id):
    mi_id = session.get('id_usuario')
    mensaje = request.form.get('mensaje')
    archivo_url = None
    if 'archivo' in request.files and request.files['archivo'].filename != '':
        file = request.files['archivo']
        filename = f"{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        archivo_url = f"/static/uploads/{filename}"

    try:
        cliente = get_db()
        check = cliente.execute(
            "SELECT id FROM usuarios WHERE id = ? AND org_id = ? AND rol != 'Solicitante'",
            (dest_id, org_id())
        ).rows
        if check:
            cliente.execute(
                "INSERT INTO mensajes_privados (org_id, de_usuario, a_usuario, mensaje, archivo) VALUES (?, ?, ?, ?, ?)",
                (org_id(), mi_id, dest_id, mensaje, archivo_url)
            )
            texto_noti = f"Tienes un nuevo mensaje privado de {session.get('nombre')}"
            enlace = f"/chat/{mi_id}"
            cliente.execute(
                "INSERT INTO notificaciones (org_id, usuario_id, texto, enlace) VALUES (?, ?, ?, ?)",
                (org_id(), dest_id, texto_noti, enlace)
            )
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('chat_interno', dest_id=dest_id))

@app.route('/vaciar_chat/<int:dest_id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def vaciar_chat(dest_id):
    mi_id = session.get('id_usuario')
    try:
        cliente = get_db()
        sql = "DELETE FROM mensajes_privados WHERE org_id = ? AND ((de_usuario = ? AND a_usuario = ?) OR (de_usuario = ? AND a_usuario = ?))"
        cliente.execute(sql, (org_id(), mi_id, dest_id, dest_id, mi_id))
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('chat_interno', dest_id=dest_id))

# ==========================================
# RUTAS DEL SISTEMA PRINCIPAL (INCIDENCIAS V2.0)
# ==========================================
@app.route('/')
@login_required
def inicio():
    busqueda = request.args.get('q', '')
    es_solicitante = (session.get('rol') == 'Solicitante')
    try:
        cliente = get_db()
        query_base = """
            SELECT i.id, i.numero, i.titulo, i.activo_ubicacion, 
                   a.nombre as area, c.nombre as categoria, 
                   i.prioridad, i.estado, u.nombre as solicitante, i.fecha_reporte,
                   COALESCE(u2.nombre, 'Sin asignar') as asignado
            FROM incidencias i
            JOIN areas a ON i.area_id = a.id
            JOIN categorias c ON i.categoria_id = c.id
            JOIN usuarios u ON i.solicitante_id = u.id
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.org_id = ?
        """
        parametros = [org_id()]

        if es_solicitante:
            query_base += " AND i.solicitante_id = ?"
            parametros.append(session.get('id_usuario'))

        if busqueda:
            query_base += " AND (CAST(i.numero AS TEXT) LIKE ? OR i.titulo LIKE ? OR i.activo_ubicacion LIKE ? OR u.nombre LIKE ?)"
            parametros.extend([f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"])
        query_base += " ORDER BY i.numero DESC"

        lista_incidencias = cliente.execute(query_base, parametros).rows

        if es_solicitante:
            todas = cliente.execute(
                "SELECT i.estado, c.nombre FROM incidencias i JOIN categorias c ON i.categoria_id = c.id WHERE i.org_id = ? AND i.solicitante_id = ?",
                (org_id(), session.get('id_usuario'))
            ).rows
        else:
            todas = cliente.execute(
                "SELECT i.estado, c.nombre FROM incidencias i JOIN categorias c ON i.categoria_id = c.id WHERE i.org_id = ?",
                (org_id(),)
            ).rows

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
        lista_incidencias, stats, categorias_stats = [], {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}, {}

    return render_template('index.html', incidencias=lista_incidencias, stats=stats, categorias=json.dumps(categorias_stats), busqueda=busqueda)

@app.route('/mis-tickets')
@login_required
def mis_tickets():
    es_solicitante = (session.get('rol') == 'Solicitante')
    try:
        cliente = get_db()
        query = """
            SELECT i.id, i.numero, i.titulo, i.activo_ubicacion, 
                   a.nombre as area, c.nombre as categoria, 
                   i.prioridad, i.estado, u.nombre as solicitante, i.fecha_reporte,
                   COALESCE(u2.nombre, 'Sin asignar') as asignado
            FROM incidencias i
            JOIN areas a ON i.area_id = a.id
            JOIN categorias c ON i.categoria_id = c.id
            JOIN usuarios u ON i.solicitante_id = u.id
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.org_id = ?
        """
        if es_solicitante:
            query += " AND i.solicitante_id = ? ORDER BY i.numero DESC"
        else:
            query += " AND i.asignado_a = ? ORDER BY i.numero DESC"

        tickets = cliente.execute(query, (org_id(), session.get('id_usuario'))).rows
        cliente.close()
    except Exception as e:
        print("Error en mis_tickets:", e)
        tickets = []

    return render_template('mis_tickets.html', incidencias=tickets)

@app.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_registro():
    cliente = get_db()
    if request.method == 'POST':
        try:
            area_id = request.form['area_id']
            categoria_id = request.form['categoria_id']

            check_area = cliente.execute("SELECT id FROM areas WHERE id = ? AND org_id = ?", (area_id, org_id())).rows
            check_cat = cliente.execute("SELECT id FROM categorias WHERE id = ? AND org_id = ?", (categoria_id, org_id())).rows
            if not check_area or not check_cat:
                cliente.close()
                flash('Departamento o categoría inválidos.', 'danger')
                return redirect(url_for('nuevo_registro'))

            res_max = cliente.execute("SELECT MAX(numero) FROM incidencias WHERE org_id = ?", (org_id(),)).rows
            siguiente_numero = (res_max[0][0] or 0) + 1 if res_max else 1

            cliente.execute(
                "INSERT INTO incidencias (org_id, numero, titulo, activo_ubicacion, area_id, categoria_id, descripcion, prioridad, estado, solicitante_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?)",
                (org_id(), siguiente_numero, request.form['titulo'], request.form['activo_ubicacion'], area_id, categoria_id, request.form['descripcion'], request.form['prioridad'], session['id_usuario'])
            )
            res_id = cliente.execute("SELECT last_insert_rowid()").rows
            nuevo_id = res_id[0][0]
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), nuevo_id, session['id_usuario'], 'Ticket Creado', f"Prioridad: {request.form['prioridad']}")
            )

            equipo = cliente.execute(
                "SELECT id FROM usuarios WHERE org_id = ? AND rol IN ('Técnico', 'Administrador', 'Propietario') AND id != ?",
                (org_id(), session['id_usuario'])
            ).rows
            for miembro in equipo:
                cliente.execute(
                    "INSERT INTO notificaciones (org_id, usuario_id, texto, enlace) VALUES (?, ?, ?, ?)",
                    (org_id(), miembro[0], f"Nuevo ticket LD-{siguiente_numero:04d}: {request.form['titulo']}", f"/incidencia/{nuevo_id}")
                )

            cliente.close()
            return redirect(url_for('inicio'))
        except Exception as e:
            print("Error al crear:", e)
            flash('Error al crear el ticket', 'danger')

    areas = cliente.execute("SELECT id, nombre FROM areas WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    categorias = cliente.execute("SELECT id, nombre FROM categorias WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    cliente.close()
    return render_template('nuevo.html', areas=areas, categorias=categorias)

@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    try:
        cliente = get_db()
        incidencia_raw = cliente.execute("""
            SELECT i.id, i.numero, i.titulo, i.activo_ubicacion, 
                   a.nombre as area, c.nombre as categoria, 
                   i.prioridad, i.estado, u.nombre as solicitante, 
                   i.solucion, i.fecha_reporte, i.fecha_solucion, 
                   i.descripcion, i.solicitante_id, i.asignado_a,
                   COALESCE(u2.nombre, 'Sin asignar') as asignado_nombre
            FROM incidencias i 
            JOIN areas a ON i.area_id = a.id 
            JOIN categorias c ON i.categoria_id = c.id 
            JOIN usuarios u ON i.solicitante_id = u.id
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.id = ? AND i.org_id = ?
        """, (id, org_id())).rows

        if not incidencia_raw:
            cliente.close()
            return "<h1>Error 404: Incidencia no encontrada o no pertenece a tu empresa</h1>", 404

        incidencia = incidencia_raw[0]

        if session.get('rol') == 'Solicitante' and incidencia[13] != session.get('id_usuario'):
            cliente.close()
            return "<h1>403 Forbidden: No tienes permiso para ver este ticket.</h1>", 403

        query_mensajes = "SELECT m.mensaje, m.es_nota_interna, m.fecha, u.nombre, u.foto, u.rol, m.archivo FROM mensajes m JOIN usuarios u ON m.usuario_id = u.id WHERE m.incidencia_id = ? AND m.org_id = ?"
        if session.get('rol') == 'Solicitante':
            query_mensajes += " AND m.es_nota_interna = 0"
        query_mensajes += " ORDER BY m.fecha ASC"

        mensajes = cliente.execute(query_mensajes, (id, org_id())).rows

        historial = cliente.execute("""
            SELECT h.accion, h.detalle, h.fecha, u.nombre, u.rol
            FROM historial_incidencias h
            JOIN usuarios u ON h.usuario_id = u.id
            WHERE h.incidencia_id = ? AND h.org_id = ?
            ORDER BY h.fecha DESC, h.id DESC
        """, (id, org_id())).rows

        tecnicos_equipo = []
        if session.get('rol') != 'Solicitante':
            tecnicos_equipo = cliente.execute(
                "SELECT id, nombre, rol FROM usuarios WHERE org_id = ? AND rol IN ('Técnico', 'Administrador', 'Propietario') AND activo = 1 ORDER BY nombre ASC",
                (org_id(),)
            ).rows

        cliente.close()
        return render_template('detalle.html', incidencia=incidencia, mensajes=mensajes, tecnicos_equipo=tecnicos_equipo, historial=historial)
    except Exception as e:
        print(e)
        return "<h1>Error interno</h1>", 500

@app.route('/asignar/<int:id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def asignar_ticket(id):
    tecnico_id = request.form.get('asignado_a')
    try:
        cliente = get_db()
        ticket = cliente.execute("SELECT numero, titulo FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id())).rows
        if not ticket:
            cliente.close()
            return "<h1>Error 404: Incidencia no encontrada</h1>", 404

        if not tecnico_id:
            cliente.execute("UPDATE incidencias SET asignado_a = NULL WHERE id = ? AND org_id = ?", (id, org_id()))
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], 'Asignación removida', 'Ticket sin asignar')
            )
            flash('Asignación removida del ticket.', 'success')
        else:
            tec = cliente.execute(
                "SELECT id, nombre FROM usuarios WHERE id = ? AND org_id = ? AND rol IN ('Técnico', 'Administrador', 'Propietario')",
                (tecnico_id, org_id())
            ).rows
            if not tec:
                cliente.close()
                flash('El usuario seleccionado no es válido en tu organización.', 'danger')
                return redirect(url_for('ver_detalle', id=id))

            cliente.execute("UPDATE incidencias SET asignado_a = ? WHERE id = ? AND org_id = ?", (tec[0][0], id, org_id()))
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], 'Ticket Asignado', f"Asignado a {tec[0][1]}")
            )

            if tec[0][0] != session.get('id_usuario'):
                cliente.execute(
                    "INSERT INTO notificaciones (org_id, usuario_id, texto, enlace) VALUES (?, ?, ?, ?)",
                    (org_id(), tec[0][0], f"Te asignaron el ticket LD-{ticket[0][0]:04d}: {ticket[0][1]}", f"/incidencia/{id}")
                )
            flash(f'Ticket asignado a {tec[0][1]}.', 'success')

        cliente.close()
    except Exception as e:
        print(e)
        flash('Error al asignar el ticket.', 'danger')
    return redirect(url_for('ver_detalle', id=id))

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
    if es_nota and session.get('rol') == 'Solicitante':
        flash('No tienes permisos para crear notas internas.', 'danger')
        return redirect(url_for('ver_detalle', id=id))

    try:
        cliente = get_db()
        check = cliente.execute("SELECT id, solicitante_id FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id())).rows
        if check:
            if session.get('rol') == 'Solicitante' and check[0][1] != session.get('id_usuario'):
                cliente.close()
                return "<h1>403 Forbidden: No puedes comentar en este ticket.</h1>", 403

            cliente.execute(
                "INSERT INTO mensajes (org_id, incidencia_id, usuario_id, mensaje, es_nota_interna, archivo) VALUES (?, ?, ?, ?, ?, ?)",
                (org_id(), id, session.get('id_usuario'), request.form.get('mensaje'), es_nota, archivo_url)
            )
            accion_hist = 'Nota interna agregada' if es_nota else 'Respuesta enviada'
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion) VALUES (?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], accion_hist)
            )
        cliente.close()
    except Exception as e:
        print(e)
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
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], 'Cambio de estado', f"De {check[0][0]} a {nuevo_estado}")
            )
            flash(f'Estado actualizado a "{nuevo_estado}".', 'success')
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('ver_detalle', id=id))

@app.route('/resolver/<int:id>', methods=['POST'])
@login_required
@roles_required('Técnico', 'Administrador', 'Propietario')
def resolver_incidencia(id):
    try:
        cliente = get_db()
        ticket = cliente.execute("SELECT numero, solicitante_id FROM incidencias WHERE id = ? AND org_id = ?", (id, org_id())).rows
        if ticket:
            cliente.execute(
                "UPDATE incidencias SET solucion = ?, estado = 'Resuelta', fecha_solucion = CURRENT_TIMESTAMP, resuelto_por = ? WHERE id = ? AND org_id = ?",
                (f"{request.form['solucion']}\n\n✅ Atendido por: {session.get('nombre')} ({session.get('rol')})", session.get('id_usuario'), id, org_id())
            )
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], 'Ticket Resuelto', 'Solución documentada y ticket cerrado')
            )
            if ticket[0][1] != session.get('id_usuario'):
                cliente.execute(
                    "INSERT INTO notificaciones (org_id, usuario_id, texto, enlace) VALUES (?, ?, ?, ?)",
                    (org_id(), ticket[0][1], f"Tu ticket LD-{ticket[0][0]:04d} ha sido resuelto.", f"/incidencia/{id}")
                )
            flash('Incidencia marcada como resuelta.', 'success')
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('ver_detalle', id=id))

@app.route('/reabrir/<int:id>', methods=['POST'])
@login_required
def reabrir_incidencia(id):
    motivo = request.form.get('motivo', '').strip()
    if not motivo:
        flash('Debes indicar el motivo para reabrir el ticket.', 'danger')
        return redirect(url_for('ver_detalle', id=id))

    try:
        cliente = get_db()
        ticket = cliente.execute(
            "SELECT numero, solicitante_id, asignado_a, estado FROM incidencias WHERE id = ? AND org_id = ?",
            (id, org_id())
        ).rows
        if not ticket:
            cliente.close()
            return "<h1>Error 404: Incidencia no encontrada</h1>", 404

        if session.get('rol') == 'Solicitante' and ticket[0][1] != session.get('id_usuario'):
            cliente.close()
            return "<h1>403 Forbidden: No puedes reabrir este ticket.</h1>", 403

        if ticket[0][3] == 'Resuelta':
            cliente.execute(
                "UPDATE incidencias SET estado = 'En revisión', solucion = NULL, fecha_solucion = NULL, resuelto_por = NULL WHERE id = ? AND org_id = ?",
                (id, org_id())
            )
            cliente.execute(
                "INSERT INTO historial_incidencias (org_id, incidencia_id, usuario_id, accion, detalle) VALUES (?, ?, ?, ?, ?)",
                (org_id(), id, session['id_usuario'], 'Ticket Reabierto', f"Motivo: {motivo}")
            )
            cliente.execute(
                "INSERT INTO mensajes (org_id, incidencia_id, usuario_id, mensaje, es_nota_interna) VALUES (?, ?, ?, ?, 0)",
                (org_id(), id, session['id_usuario'], f"🔄 Ticket reabierto. Motivo: {motivo}")
            )

            destino_noti = ticket[0][2] if session.get('rol') == 'Solicitante' else ticket[0][1]
            if destino_noti and destino_noti != session.get('id_usuario'):
                cliente.execute(
                    "INSERT INTO notificaciones (org_id, usuario_id, texto, enlace) VALUES (?, ?, ?, ?)",
                    (org_id(), destino_noti, f"El ticket LD-{ticket[0][0]:04d} fue reabierto: {motivo}", f"/incidencia/{id}")
                )

            flash('El ticket ha sido reabierto y puesto en revisión.', 'success')
        cliente.close()
    except Exception as e:
        print(e)
        flash('Error al reabrir el ticket.', 'danger')
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
        flash('Ticket eliminado permanentemente.', 'success')
    except Exception as e:
        print(e)
    return redirect(url_for('inicio'))

# ==========================================
# GESTIÓN DE ÁREAS Y CATEGORÍAS (PASO 10)
# ==========================================
@app.route('/areas', methods=['GET', 'POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def vista_areas():
    cliente = get_db()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        nombre = request.form.get('nombre')
        try:
            if tipo == 'area':
                cliente.execute("INSERT INTO areas (org_id, nombre) VALUES (?, ?)", (org_id(), nombre))
                flash('Departamento agregado con éxito.', 'success')
            elif tipo == 'categoria':
                cliente.execute("INSERT INTO categorias (org_id, nombre) VALUES (?, ?)", (org_id(), nombre))
                flash('Categoría agregada con éxito.', 'success')
        except Exception:
            flash('Error al guardar. Es posible que el nombre ya exista.', 'danger')
        return redirect(url_for('vista_areas'))

    areas = cliente.execute("SELECT id, nombre FROM areas WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    categorias = cliente.execute("SELECT id, nombre FROM categorias WHERE org_id = ? ORDER BY nombre", (org_id(),)).rows
    cliente.close()
    return render_template('areas.html', areas=areas, categorias=categorias)

@app.route('/eliminar_area/<int:id>', methods=['POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def eliminar_area(id):
    try:
        cliente = get_db()
        check = cliente.execute("SELECT id FROM incidencias WHERE area_id = ? AND org_id = ?", (id, org_id())).rows
        if check:
            flash('No se puede eliminar este departamento porque tiene tickets asociados.', 'danger')
        else:
            cliente.execute("DELETE FROM areas WHERE id = ? AND org_id = ?", (id, org_id()))
            flash('Departamento eliminado.', 'success')
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('vista_areas'))

@app.route('/eliminar_categoria/<int:id>', methods=['POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def eliminar_categoria(id):
    try:
        cliente = get_db()
        check = cliente.execute("SELECT id FROM incidencias WHERE categoria_id = ? AND org_id = ?", (id, org_id())).rows
        if check:
            flash('No se puede eliminar esta categoría porque tiene tickets asociados.', 'danger')
        else:
            cliente.execute("DELETE FROM categorias WHERE id = ? AND org_id = ?", (id, org_id()))
            flash('Categoría eliminada.', 'success')
        cliente.close()
    except Exception as e:
        print(e)
    return redirect(url_for('vista_areas'))

# ==========================================
# GESTIÓN DE EQUIPO, ROLES Y PROPIEDAD (PASO 9)
# ==========================================
@app.route('/tecnicos')
@login_required
@roles_required('Administrador', 'Propietario')
def gestion_tecnicos():
    try:
        cliente = get_db()
        org_data = cliente.execute(
            "SELECT nombre, codigo_invitacion FROM organizaciones WHERE id = ?",
            (org_id(),)
        ).rows
        empresa = {'nombre': org_data[0][0], 'codigo': org_data[0][1]} if org_data else {'nombre': '', 'codigo': ''}

        miembros = cliente.execute(
            "SELECT id, nombre, usuario, email, rol, activo FROM usuarios WHERE org_id = ? ORDER BY CASE rol WHEN 'Propietario' THEN 1 WHEN 'Administrador' THEN 2 WHEN 'Técnico' THEN 3 ELSE 4 END, nombre ASC",
            (org_id(),)
        ).rows
        cliente.close()
    except Exception as e:
        print(e)
        empresa = {'nombre': '', 'codigo': ''}
        miembros = []
    return render_template('tecnicos.html', tecnicos=miembros, empresa=empresa)

@app.route('/cambiar_rol/<int:user_id>', methods=['POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def cambiar_rol(user_id):
    nuevo_rol = request.form.get('rol')
    if nuevo_rol not in ['Solicitante', 'Técnico', 'Administrador']:
        flash('Rol no válido.', 'danger')
        return redirect(url_for('gestion_tecnicos'))

    try:
        cliente = get_db()
        target = cliente.execute(
            "SELECT id, rol, nombre FROM usuarios WHERE id = ? AND org_id = ?",
            (user_id, org_id())
        ).rows
        if not target:
            cliente.close()
            flash('Usuario no encontrado en tu empresa.', 'danger')
            return redirect(url_for('gestion_tecnicos'))

        if target[0][1] == 'Propietario':
            cliente.close()
            flash('No se puede cambiar el rol del Propietario directamente. Usa la opción de transferir propiedad.', 'danger')
            return redirect(url_for('gestion_tecnicos'))

        cliente.execute(
            "UPDATE usuarios SET rol = ? WHERE id = ? AND org_id = ?",
            (nuevo_rol, user_id, org_id())
        )
        if user_id == session.get('id_usuario'):
            session['rol'] = nuevo_rol
        cliente.close()
        flash(f'Rol de {target[0][2]} actualizado a {nuevo_rol}.', 'success')
    except Exception as e:
        print(e)
        flash('Error al actualizar el rol.', 'danger')
    return redirect(url_for('gestion_tecnicos'))

@app.route('/regenerar_codigo', methods=['POST'])
@login_required
@roles_required('Administrador', 'Propietario')
def regenerar_codigo():
    try:
        nuevo_codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        cliente = get_db()
        cliente.execute(
            "UPDATE organizaciones SET codigo_invitacion = ? WHERE id = ?",
            (nuevo_codigo, org_id())
        )
        cliente.close()
        flash(f'Código de invitación regenerado: {nuevo_codigo}', 'success')
    except Exception as e:
        print(e)
        flash('Error al regenerar el código.', 'danger')
    return redirect(url_for('gestion_tecnicos'))

@app.route('/transferir_propiedad', methods=['POST'])
@login_required
@roles_required('Propietario')
def transferir_propiedad():
    nuevo_prop_id = request.form.get('nuevo_propietario_id')
    try:
        cliente = get_db()
        target = cliente.execute(
            "SELECT id, nombre FROM usuarios WHERE id = ? AND org_id = ? AND id != ?",
            (nuevo_prop_id, org_id(), session.get('id_usuario'))
        ).rows
        if not target:
            cliente.close()
            flash('Selecciona un miembro válido de tu empresa.', 'danger')
            return redirect(url_for('gestion_tecnicos'))

        cliente.execute("UPDATE usuarios SET rol = 'Propietario' WHERE id = ? AND org_id = ?", (target[0][0], org_id()))
        cliente.execute("UPDATE usuarios SET rol = 'Administrador' WHERE id = ? AND org_id = ?", (session.get('id_usuario'), org_id()))
        session['rol'] = 'Administrador'
        cliente.close()
        flash(f'Propiedad transferida a {target[0][1]}. Tu rol actual es Administrador.', 'success')
    except Exception as e:
        print(e)
        flash('Error al transferir la propiedad.', 'danger')
    return redirect(url_for('gestion_tecnicos'))

# ==========================================
# REPORTES Y EXPORTACIÓN AVANZADA (PASO 8 & 11)
# ==========================================
@app.route('/exportar')
@login_required
@roles_required('Administrador', 'Propietario')
def exportar_csv():
    estado_filtro = request.args.get('estado', '')
    try:
        cliente = get_db()
        query = """
            SELECT i.numero, i.titulo, i.activo_ubicacion, a.nombre, c.nombre, i.prioridad, i.estado, 
                   u.nombre, COALESCE(u2.nombre, 'Sin asignar'), i.fecha_reporte, COALESCE(i.fecha_solucion, '')
            FROM incidencias i 
            JOIN areas a ON i.area_id = a.id 
            JOIN categorias c ON i.categoria_id = c.id 
            JOIN usuarios u ON i.solicitante_id = u.id 
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.org_id = ?
        """
        params = [org_id()]
        if estado_filtro:
            query += " AND i.estado = ?"
            params.append(estado_filtro)
        query += " ORDER BY i.numero DESC"

        filas = cliente.execute(query, params).rows
        cliente.close()

        def generate():
            data = io.StringIO()
            writer = csv.writer(data)
            writer.writerow(['Ticket', 'Titulo', 'Activo / Ubicacion', 'Departamento', 'Categoria', 'Prioridad', 'Estado', 'Solicitante', 'Tecnico Asignado', 'Fecha Reporte', 'Fecha Solucion'])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)
            for fila in filas:
                writer.writerow([f"LD-{fila[0]:04d}", fila[1], fila[2], fila[3], fila[4], fila[5], fila[6], fila[7], fila[8], fila[9], fila[10]])
                yield data.getvalue()
                data.seek(0)
                data.truncate(0)

        response = Response(generate(), mimetype='text/csv')
        response.headers.set("Content-Disposition", "attachment", filename=f"reporte_tickets_{datetime.now().strftime('%Y%m%d')}.csv")
        return response
    except Exception as e:
        print(e)
        return redirect(url_for('inicio'))

@app.route('/exportar_pdf')
@login_required
@roles_required('Administrador', 'Propietario')
def exportar_pdf():
    estado_filtro = request.args.get('estado', '')
    try:
        cliente = get_db()
        empresa_row = cliente.execute("SELECT nombre FROM organizaciones WHERE id = ?", (org_id(),)).rows
        nombre_empresa = empresa_row[0][0] if empresa_row else "Empresa"

        query = """
            SELECT i.numero, i.titulo, i.activo_ubicacion, a.nombre, i.prioridad, i.estado, 
                   u.nombre, COALESCE(u2.nombre, 'Sin asignar')
            FROM incidencias i 
            JOIN areas a ON i.area_id = a.id 
            JOIN usuarios u ON i.solicitante_id = u.id 
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.org_id = ?
        """
        params = [org_id()]
        if estado_filtro:
            query += " AND i.estado = ?"
            params.append(estado_filtro)
        query += " ORDER BY i.numero DESC"

        filas = cliente.execute(query, params).rows
        cliente.close()

        total = len(filas)
        pendientes = sum(1 for f in filas if f[5] == 'Pendiente')
        revision = sum(1 for f in filas if f[5] == 'En revisión')
        resueltas = sum(1 for f in filas if f[5] == 'Resuelta')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph(f"Reporte Ejecutivo de Incidencias — {nombre_empresa}", styles['Title']))
        elements.append(Paragraph(f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')} | Emitido por: {session.get('nombre')}", styles['Normal']))
        elements.append(Spacer(1, 14))

        resumen_data = [
            ['Total Incidencias', 'Pendientes', 'En Revisión', 'Resueltas'],
            [str(total), str(pendientes), str(revision), str(resueltas)]
        ]
        t_resumen = Table(resumen_data, colWidths=[135, 135, 135, 135])
        t_resumen.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1D1D1F')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F5F5F7')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.white),
        ]))
        elements.append(t_resumen)
        elements.append(Spacer(1, 18))

        data = [['Ticket', 'Problema / Activo', 'Depto.', 'Prioridad', 'Estado', 'Asignado a']]
        for f in filas:
            detalle_col = f"{f[1]} ({f[2]})"
            if len(detalle_col) > 38:
                detalle_col = detalle_col[:35] + "..."
            data.append([f"LD-{f[0]:04d}", detalle_col, f[3], f[4], f[5], f[7]])

        t = Table(data, colWidths=[58, 192, 75, 62, 68, 85])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0071E3')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F7')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F5F5F7'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E5EA')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(t)
        doc.build(elements)

        pdf = buffer.getvalue()
        buffer.close()
        response = Response(pdf, mimetype='application/pdf')
        response.headers.set("Content-Disposition", "attachment", filename="reporte_corporativo.pdf")
        return response
    except Exception as e:
        print(e)
        return redirect(url_for('inicio'))

if __name__ == '__main__':
    app.run(debug=True)