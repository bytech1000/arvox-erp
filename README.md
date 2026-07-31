# ARVOX ERP

**Donde juega la calidad.**

Base profesional del sistema privado de gestión ARVOX.

## Versión actual

### v1.0 — Módulo 1: Productos

Incluye:

- Inicio de sesión privado
- Catálogo de productos
- Alta, edición y activación/desactivación
- Búsqueda y filtros
- Stock actual y stock mínimo
- Costo promedio
- Precio de venta y margen
- Ficha completa
- Historial de compras y ventas
- Información técnica opcional
- Diseño responsive con identidad ARVOX
- Configuración preparada para Render y PostgreSQL

## Acceso local inicial

- Usuario: `admin`
- Contraseña: `admin123`

En producción se debe definir una contraseña distinta mediante la variable `ADMIN_PASSWORD`.

## Ejecutar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Abrir `http://localhost:5000`.
