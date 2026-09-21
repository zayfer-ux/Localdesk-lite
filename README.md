# 🖥️ LocalDesk Lite

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Turso](https://img.shields.io/badge/Turso_DB-000000?style=flat-square&logo=sqlite&logoColor=white)
![Estado](https://img.shields.io/badge/Estado-En_Desarrollo-FF8C00?style=flat-square)

> **LocalDesk Lite** es un sistema de consola ágil y directo, desarrollado en Python, diseñado para registrar, gestionar y dar seguimiento a incidencias de equipos de cómputo en pequeños negocios e instituciones educativas.

---

## 🚨 El Problema vs. 💡 La Solución

**El Problema:**  
Los reportes técnicos suelen comunicarse de manera informal (en pasillos, notas de papel o mensajes directos). Esto provoca que los reportes se olviden, los usuarios ignoren el estado de su equipo, y no exista un historial de fallas o soluciones.

**La Solución:**  
Centralizar el caos. LocalDesk Lite permite documentar qué problema ocurrió, en qué equipo, quién lo reportó y, lo más importante, conservar un registro histórico de cómo se resolvió para agilizar futuros mantenimientos.

---

## ✨ Funciones y Progreso (Roadmap)

El desarrollo se encuentra en su primera fase. A continuación el estado actual de las funcionalidades:

- [x] 📝 **Registrar:** Crear nuevas incidencias tecnológicas.
- [x] 📋 **Mostrar:** Visualizar el listado general de reportes activos.
- [x] 🔍 **Buscar:** Consultar los detalles completos de una incidencia por ID.
- [x] 🔄 **Actualizar:** Cambiar el estado del reporte (Pendiente / En revisión).
- [ ] ✅ **Resolver:** Registrar la solución aplicada y marcar como finalizada.
- [ ] 🗑️ **Eliminar:** Borrar registros duplicados o incorrectos.
- [ ] 📊 **Estadísticas:** Mostrar un panel básico con el conteo de incidencias.

---

## 🛠️ Stack Tecnológico

* **Lenguaje:** Python
* **Base de Datos:** Turso (Edge SQL)
* **IDE:** Antigravity IDE
* **Control de Versiones:** Git & GitHub

---

## 🚀 Instalación y Ejecución

Para iniciar el programa en tu entorno local, clona el repositorio, asegúrate de tener tu archivo `.env` configurado con tus credenciales de Turso, y ejecuta el siguiente comando en tu terminal:

```bash
python main.py
