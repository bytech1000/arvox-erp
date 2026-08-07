# ARVOX ERP v6.2.3 — Ajustes de inventario

- Ajuste manual de stock por conteo físico desde Stock > Ajustar stock.
- El usuario informa el stock físico real y ARVOX registra solamente la diferencia como movimiento de ajuste.
- Editar un producto ya no puede modificar `opening_stock` ni `opening_cost`.
- Desde Editar producto se muestra el stock actual y un acceso directo a Ajustar stock.
- Compras, ventas y ajustes siguen siendo las fuentes de movimientos de inventario.
- Compatible con PostgreSQL y conserva los datos existentes.
