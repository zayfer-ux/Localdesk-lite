import incidencias

def mostrar_menu():
    print("\n" + "=" * 40)
    print("          LOCALDESK LITE")
    print("=" * 40)
    print("1. Registrar incidencia")
    print("2. Mostrar incidencias")
    print("3. Buscar incidencia")
    print("4. Actualizar estado")
    print("5. Registrar solución")
    print("6. Eliminar incidencia")
    print("7. Mostrar estadísticas")
    print("8. Salir")
    print("=" * 40)

def ejecutar_programa():
    while True:
        mostrar_menu()
        opcion = input("Seleccione una opción: ").strip()

        if opcion == "1":
            incidencias.registrar_incidencia()

        elif opcion == "2":
            incidencias.mostrar_incidencias()

        elif opcion == "3":
            incidencias.buscar_incidencia()

        elif opcion == "4":
            incidencias.actualizar_estado()

        elif opcion == "5":
            incidencias.registrar_solucion()

        elif opcion == "6":
            incidencias.eliminar_incidencia()

        elif opcion == "7":
            print("\nLas estadísticas estarán disponibles próximamente.")

        elif opcion == "8":
            print("\nGracias por utilizar LocalDesk Lite.")
            break

        else:
            print("\n[Error] Opción incorrecta. Seleccione una opción del 1 al 8.")


if __name__ == "__main__":
    ejecutar_programa()