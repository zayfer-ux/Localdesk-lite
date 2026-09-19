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

def buscar_incidencia():
    print("\n" + "-" * 40)
    print(" BUSCAR INCIDENCIA")
    print("-" * 40)
    
    id_buscar = input("Ingrese el ID de la incidencia: ").strip()
    
    if not id_buscar.isdigit():
        print("\n[Error] El ID debe ser un número entero.")
        return
        
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        
        sql = "SELECT * FROM incidencias WHERE id = ?"
        resultado = cliente.execute(sql, (id_buscar,))
        
        if not resultado.rows:
            print(f"\n[Info] No se encontró ninguna incidencia con el ID {id_buscar}.")
        else:
            fila = resultado.rows[0]
            # La base de datos devuelve una tupla con los campos en el orden en que se crearon
            print("\n--- DETALLES DE LA INCIDENCIA ---")
            print(f"ID:            {fila[0]}")
            print(f"Estado:        {fila[7]}")
            print(f"Prioridad:     {fila[6]}")
            print(f"Título:        {fila[1]}")
            print(f"Categoría:     {fila[4]}")
            print(f"Equipo:        {fila[2]}")
            print(f"Área:          {fila[3]}")
            print(f"Descripción:   {fila[5]}")
            print(f"Reportado por: {fila[8]}")
            print(f"Fecha reporte: {fila[10]}")
            
            # Si ya tiene una solución y fecha de solución, las mostramos
            if fila[9]:
                print(f"Solución:      {fila[9]}")
                print(f"Fecha sol.:    {fila[11]}")
                
        cliente.close()
    except Exception as e:
        print(f"\n[Error] No se pudo realizar la búsqueda: {e}")

def actualizar_estado():
    print("\n" + "-" * 40)
    print(" ACTUALIZAR ESTADO DE INCIDENCIA")
    print("-" * 40)
    
    id_buscar = input("Ingrese el ID de la incidencia a actualizar: ").strip()
    
    if not id_buscar.isdigit():
        print("\n[Error] El ID debe ser un número entero.")
        return
        
    try:
        cliente = libsql_client.create_client_sync(url=url, auth_token=token)
        
        # Verificar que el registro existe antes de actualizar
        sql_verificar = "SELECT id, estado FROM incidencias WHERE id = ?"
        resultado = cliente.execute(sql_verificar, (id_buscar,))
        
        if not resultado.rows:
            print(f"\n[Info] No se encontró ninguna incidencia con el ID {id_buscar}.")
            cliente.close()
            return
            
        estado_actual = resultado.rows[0][1]
        print(f"\nEstado actual: {estado_actual}")
        print("Opciones: 1. Pendiente | 2. En revisión")
        print("(Nota: Para marcar como 'Resuelta', utilice la opción 5 del menú principal).")
        
        opcion_estado = input("Seleccione el nuevo estado (1 o 2): ").strip()
        
        if opcion_estado == "1":
            nuevo_estado = "Pendiente"
        elif opcion_estado == "2":
            nuevo_estado = "En revisión"
        else:
            print("\n[Error] Opción no válida. Se canceló la actualización.")
            cliente.close()
            return
            
        if nuevo_estado == estado_actual:
            print(f"\n[Info] La incidencia ya tiene el estado '{nuevo_estado}'.")
            cliente.close()
            return
            
        # Ejecutar la actualización en la base de datos
        sql_actualizar = "UPDATE incidencias SET estado = ? WHERE id = ?"
        cliente.execute(sql_actualizar, (nuevo_estado, id_buscar))
        
        print(f"\n[Éxito] El estado se actualizó correctamente a '{nuevo_estado}'.")
            
        cliente.close()
    except Exception as e:
        print(f"\n[Error] No se pudo actualizar el estado: {e}")