# ARVOX v6.0 — PostgreSQL en Render

Esta versión evita que ARVOX use SQLite en Render. En producción, `DATABASE_URL` es obligatoria.

## Orden correcto de instalación

1. En Render, crear una base **Postgres** en la misma región que `arvox-erp`.
2. Copiar la **Internal Database URL**.
3. Abrir el Web Service `arvox-erp` > **Environment**.
4. Crear la variable `DATABASE_URL` y pegar la URL interna.
5. Guardar los cambios.
6. Subir esta versión a GitHub.
7. Esperar el despliegue.
8. Abrir ARVOX > Configuración > Mantenimiento.
9. Confirmar que el tipo de base diga `POSTGRESQL`.

## Importante

- La base SQLite anterior era temporal y sus datos ya se perdieron; esta instalación comienza con la nueva base PostgreSQL.
- El Catálogo Maestro se carga automáticamente una sola vez.
- El usuario administrador se crea automáticamente si la base está vacía.
- No elimines `DATABASE_URL` después de la instalación.
