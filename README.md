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


## Interfaz ARVOX

- Identidad visual negra, blanca y naranja
- Menú lateral
- Barra superior con búsqueda y acciones rápidas
- Dashboard ejecutivo
- Vista de productos en tarjetas y tabla
- Diseño responsive para celular
- Login renovado


## v1.2 — Módulo 2: Proveedores

- Alta de proveedores
- Búsqueda y filtros
- Edición
- Activación/desactivación
- Ficha comercial
- Acceso directo a WhatsApp
- Condiciones de pago y moneda
- Total comprado
- Total pagado
- Saldo pendiente
- Historial de compras
- Integración preparada para el Módulo Compras


## Corrección de despliegue Render

- Python 3.11.11 fijado en `.python-version`
- Dependencias compatibles con la prueba gratuita
- Build: `pip install -r requirements.txt`
- Start: `gunicorn run:app`
- Persistencia temporal con SQLite durante la prueba


## v1.3 — Módulo 1 Productos finalizado

- Stock inicial
- Costo unitario inicial
- Moneda por producto
- Último costo calculado
- Costo promedio ponderado
- Precio de venta y margen
- Preparado para actualización automática desde Compras
- Migración segura de bases SQLite existentes


## v2.1 — Módulo Compras 2.1

- Alta de compras de un producto
- Proveedor y producto
- Estados Recibida, Pendiente y Cancelada
- Stock automático
- Último costo
- Costo promedio ponderado
- Saldo pendiente
- Historial, edición y cancelación


## v2.2 — Compra completa multiproducto

- Una compra por proveedor y factura
- Varias líneas de productos
- Total y saldo general
- Stock y costos actualizados por cada línea
- Historial consolidado por compra


## v3.0 — Módulo Ventas

- Venta multiproducto
- Precio automático del producto
- Descuentos por línea
- Estados Entregada, Reservada y Cancelada
- Control de stock
- Reserva de stock
- Cobros y saldos
- Costo congelado al momento de vender
- Ganancia por producto y por venta
- Historial y detalle
