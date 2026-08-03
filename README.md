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


## v3.1 — Clientes y cuenta corriente

- Alta, edición y activación de clientes
- WhatsApp, email, ciudad y notas
- Selección obligatoria de cliente en Ventas
- Historial de ventas
- Total vendido
- Total cobrado
- Saldo pendiente
- Productos comprados
- Acceso directo a WhatsApp
- Nueva venta desde la ficha


## v3.2 — Dashboard comercial

- Filtros Hoy, Semana, Mes, Año y rango personalizado
- Selector de moneda
- Ventas, ganancias, compras y stock valorizado
- Por cobrar y por pagar
- Gráfico diario de ventas
- Productos más vendidos y rentables
- Clientes principales y con deuda
- Proveedores con saldo
- Stock crítico
- Alertas comerciales
- Últimos movimientos


## v4.0 — Motor de Cotizaciones

- Cotizaciones multiproducto
- Numeración automática COT-000001
- Clientes, fecha, validez, moneda y observaciones
- Precio automático y descuento por línea
- Margen esperado
- Estados Borrador, Enviada, Aceptada, Rechazada, Vencida y Convertida
- Edición
- Duplicado
- Historial y filtros
- Conversión directa a venta
- Control de stock al convertir
- Vínculo entre cotización y venta


## v4.1 — PDF profesional y WhatsApp

- Generación de PDF por cotización
- Diseño ARVOX negro, blanco y naranja
- Datos del cliente
- Productos, cantidades, precios y descuentos
- Subtotal, descuento y total
- Observaciones y condiciones comerciales
- Botón de descarga
- Mensaje de WhatsApp prearmado
- Enlace al PDF dentro del mensaje


## v4.2 — Cotización online y aceptación

- Enlace público firmado para cada cotización
- Vista responsive para el cliente
- Acceso sin iniciar sesión
- Descarga pública del PDF
- Aceptación online
- Estado actualizado automáticamente a Aceptada
- Detección de cotizaciones vencidas
- WhatsApp con enlace público correcto
- Embudo comercial tipo Kanban
- Indicadores de aceptación y conversión
