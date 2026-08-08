# ARVOX ERP v6.2.3 — Ajustes de inventario

- Ajuste manual de stock por conteo físico desde Stock > Ajustar stock.
- El usuario informa el stock físico real y ARVOX registra solamente la diferencia como movimiento de ajuste.
- Editar un producto ya no puede modificar `opening_stock` ni `opening_cost`.
- Desde Editar producto se muestra el stock actual y un acceso directo a Ajustar stock.
- Compras, ventas y ajustes siguen siendo las fuentes de movimientos de inventario.
- Compatible con PostgreSQL y conserva los datos existentes.


## v6.2.3.1
- Corrige el botón Ajustar stock desde Productos.
- Abre automáticamente el formulario con el producto seleccionado.
- Agrega Ajustar directamente en cada fila del módulo Stock.


## v6.2.4 — Conversión de unidades de compra
- Cada línea de compra distingue unidad de compra y unidad de stock.
- Permite indicar factor de conversión (ej.: 1 caja = 18 tubos).
- El total de la factura sigue usando cantidad comprada x costo de compra.
- Stock e inventario usan las unidades convertidas.
- Costo promedio y último costo se expresan por unidad de stock.
- Las compras históricas pueden corregirse desde su detalle.
- Al corregir una compra histórica se preserva el stock físico actual mediante un ajuste compensatorio trazable.


## v6.2.4.1 — Corrección de stock en conversiones históricas
- Al convertir una compra histórica, el stock aportado por esa compra se convierte también.
- Ejemplo: 1 caja x24 pasa a 24 tubos en stock.
- El costo total de la compra no cambia.
- El costo por tubo se calcula dividiendo el costo de la caja por el factor.
- Se elimina el ajuste compensatorio que preservaba incorrectamente el stock anterior.


## v6.2.4.2 — Limpieza de ajuste legado de conversión
- Elimina al guardar la conversión únicamente el ajuste compensatorio automático creado por v6.2.4.
- Corrige casos como ODPRO: 1 caja x24 debe mostrar 24 tubos, no 1.
- No elimina ajustes manuales de inventario.
- No modifica otras compras o productos.


## v6.2.5 — Costos visibles al editar producto
- Muestra último costo por unidad de stock.
- Muestra costo promedio por unidad de stock.
- Los costos son solo lectura y siguen viniendo de Compras.
- Al ingresar precio de venta muestra ganancia y margen estimado.
