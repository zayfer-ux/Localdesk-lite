import os
import io
import csv
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import libsql_client
from dotenv import load_dotenv
from datetime import datetime
import json

# Importaciones para generar PDF profesional (Estilo Apple/ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Cargar credenciales de Turso
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

app = Flask(__name__)
# OBLIGATORIO para el login
app.secret_key = os.getenv("SECRET_KEY", "super_secreto_futurista_123")

# --- CANDADO DE SEGURIDAD ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logeado' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# RUTAS DE AUTENTICACIÓN
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        if usuario == 'admin' and password == 'admin123':
            session['logeado'] = True
            session['usuario'] = usuario
            return redirect(url_for('inicio'))
        else:
            flash('Credenciales incorrectas. Intenta de nuevo.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# RUTAS DE LA APLICACIÓN
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
            sql = """
                SELECT * FROM incidencias 
                WHERE CAST(id AS TEXT) LIKE ? 
                OR titulo LIKE ? 
                OR equipo LIKE ? 
                OR reportado_por LIKE ?
                ORDER BY id DESC
            """
            resultado = cliente.execute(sql, (param, param, param, param))
        else:
            resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
            
        lista_incidencias = resultado.rows
        cliente.close()
        
    except Exception as e:
        lista_incidencias = []
        stats = {'total': 0, 'pendientes': 0, 'revision': 0, 'resueltas': 0}
        categorias = {'Hardware': 0, 'Software': 0, 'Red': 0, 'Otro': 0}
        print(f"Error base de datos: {e}")

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
            sql = """
            INSERT INTO incidencias (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            cliente.execute(sql, (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte))
            cliente.close()
        except Exception as e:
            print(f"Error al guardar: {e}")

        return redirect(url_for('inicio'))

    return render_template('nuevo.html')


@app.route('/incidencia/<int:id>')
@login_required
def ver_detalle(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT * FROM incidencias WHERE id = ?", (id,))
        cliente.close()
        
        if resultado.rows:
            return render_template('detalle.html', incidencia=resultado.rows[0])
        else:
            return "<h1>Error: Incidencia no encontrada</h1>", 404
    except Exception as e:
        return f"<h1>Error al conectar con la base de datos: {e}</h1>"


@app.route('/actualizar_estado/<int:id>', methods=['POST'])
@login_required
def actualizar_estado(id):
    nuevo_estado = request.form['nuevo_estado']
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("UPDATE incidencias SET estado = ? WHERE id = ?", (nuevo_estado, id))
        cliente.close()
    except Exception as e:
        print(f"Error al actualizar estado: {e}")
    return redirect(url_for('ver_detalle', id=id))


@app.route('/resolver/<int:id>', methods=['POST'])
@login_required
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


@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_incidencia(id):
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        cliente.execute("DELETE FROM incidencias WHERE id = ?", (id,))
        cliente.close()
    except Exception as e:
        print(f"Error al eliminar incidencia: {e}")
    return redirect(url_for('inicio'))


# ==========================================
# EXPORTAR A EXCEL (CSV)
# ==========================================
@app.route('/exportar')
@login_required
def exportar_csv():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT * FROM incidencias ORDER BY id DESC")
        incidencias = resultado.rows
        cliente.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Problema', 'Equipo', 'Area', 'Categoria', 'Descripcion', 'Prioridad', 'Estado', 'Reportado Por', 'Solucion', 'Fecha Reporte', 'Fecha Solucion'])
        
        for item in incidencias:
            writer.writerow([item[0], item[1], item[2], item[3], item[4], item[5], item[6], item[7], item[8], item[9], item[10], item[11]])
        
        output.seek(0)
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=Reporte_LocalDesk_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    except Exception as e:
        print(f"Error al exportar CSV: {e}")
        return redirect(url_for('inicio'))


# ==========================================
# NUEVA RUTA: EXPORTAR A PDF ESTILO APPLE
# ==========================================
@app.route('/exportar_pdf')
@login_required
def exportar_pdf():
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        resultado = cliente.execute("SELECT id, titulo, equipo, categoria, estado, prioridad, reportado_por FROM incidencias ORDER BY id DESC")
        incidencias = resultado.rows
        cliente.close()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elementos = []

        # Estilos tipográficos limpios
        styles = getSampleStyleSheet()
        estilo_titulo = ParagraphStyle(
            'TituloReporte',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            textColor=colors.HexColor('#1D1D1F'),
            spaceAfter=4
        )
        estilo_subtitulo = ParagraphStyle(
            'SubTituloReporte',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.HexColor('#86868B'),
            spaceAfter=20
        )

        elementos.append(Paragraph("LocalDesk - Reporte de Incidencias", estilo_titulo))
        elementos.append(Paragraph(f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | Total de registros: {len(incidencias)}", estilo_subtitulo))

        # Tabla de datos
        data = [["ID", "Problema", "Equipo", "Categoría", "Estado", "Prioridad", "Reportado"]]
        for item in incidencias:
            data.append([str(item[0]), str(item[1]), str(item[2]), str(item[3]), str(item[4]), str(item[5]), str(item[6])])

        # Construcción de la tabla con estética limpia y bordes sutiles
        tabla = Table(data, colWidths=[30, 140, 75, 65, 65, 65, 100])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0071E3')), # Azul Apple
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F7')), # Fondo gris suave tipo iOS
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E5EA')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))

        elementos.append(tabla)
        doc.build(elementos)

        buffer.seek(0)
        return Response(
            buffer,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment;filename=Reporte_LocalDesk_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )
    except Exception as e:
        print(f"Error al generar PDF: {e}")
        return redirect(url_for('inicio'))


if __name__ == '__main__':
    app.run(debug=True)