# PUBLICAR ESTA CORRECCIÓN EN RENDER

Esta versión corrige el primer error de despliegue.

## Cambios aplicados

- Python fijado en 3.11.11 mediante `.python-version`.
- Eliminada la dependencia PostgreSQL que bloqueaba la instalación.
- Comando de inicio correcto: `gunicorn run:app`.
- Se conserva la base SQLite para esta prueba gratuita.

## En Render

Build Command:

    pip install -r requirements.txt

Start Command:

    gunicorn run:app

Después de subir estos archivos a GitHub:

1. Entrar al servicio `arvox-erp`.
2. Abrir `Settings`.
3. Cambiar Start Command a `gunicorn run:app`.
4. Elegir `Manual Deploy` → `Deploy latest commit`.

## Importante

SQLite sirve para probar la aplicación, pero Render puede borrar sus datos cuando
reinicia o vuelve a desplegar el servicio gratuito. No cargar información irremplazable
hasta conectar una base persistente.


## v5.2.1

Después del deploy, ingresá en Configuración > Mantenimiento. Antes de reiniciar los datos, descargá un respaldo. El reinicio conserva el usuario administrador.
