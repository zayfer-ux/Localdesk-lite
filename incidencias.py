import os
import libsql_client
from datetime import datetime
from dotenv import load_dotenv

# Cargar credenciales
load_dotenv()
url = os.getenv("TURSO_DATABASE_URL")
token = os.getenv("TURSO_AUTH_TOKEN")

def registrar_incidencia():
    print("\n" + "-" * 40)
    print(" REGISTRAR NUEVA INCIDENCIA")
    print("-" * 40)
    
    # Solicitar datos
    titulo = input("Título del problema: ").strip()
    equipo = input("Código o nombre del equipo: ").strip()
    area = input("Área o ubicación: ").strip()
    categoria = input("Categoría (Hardware/Software/Red/Impresora/Cuenta/Otro): ").strip()
    descripcion = input("Descripción detallada: ").strip()
    reportado_por = input("Reportado por: ").strip()
    prioridad = input("Prioridad (Baja/Media/Alta) [Por defecto: Media]: ").strip().capitalize()
    
    # Reglas de negocio
    if not prioridad:
        prioridad = "Media"
        
    if not titulo or not equipo or not descripcion or not reportado_por:
        print("\n[Error] El título, equipo, descripción y la persona que reporta son obligatorios.")
        return

    estado = "Pendiente"
    fecha_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Guardar en Turso
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        
        sql = """
        INSERT INTO incidencias (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        parametros = (titulo, equipo, area, categoria, descripcion, prioridad, estado, reportado_por, fecha_reporte)
        
        cliente.execute(sql, parametros)
        print("\n[Éxito] Incidencia registrada correctamente en la base de datos.")
        
        cliente.close()
    except Exception as e:
        print(f"\n[Error] No se pudo guardar el registro: {e}")

def mostrar_incidencias():
    print("\n" + "-" * 40)
    print(" LISTADO DE INCIDENCIAS")
    print("-" * 40)
    
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        
        # Consultar los campos más importantes
        sql = "SELECT id, titulo, equipo, prioridad, estado FROM incidencias"
        resultado = cliente.execute(sql)
        
        if not resultado.rows:
            print("\n[Info] No hay incidencias registradas en este momento.")
        else:
            for fila in resultado.rows:
                # fila[0] es id, fila[1] es titulo, fila[2] es equipo, fila[3] es prioridad, fila[4] es estado
                print(f"ID: {fila[0]} | Estado: {fila[4]} | Prioridad: {fila[3]}")
                print(f"Equipo: {fila[2]} | Problema: {fila[1]}")
                print("-" * 40)
                
        cliente.close()
    except Exception as e:
        print(f"\n[Error] No se pudieron consultar los registros: {e}")