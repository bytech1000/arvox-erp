# Arquitectura de ARVOX ERP

Esta versión reorganiza el proyecto sin cambiar la experiencia del usuario.

## Estructura principal

- `app/factory.py`: crea y configura la aplicación Flask.
- `app/extensions.py`: contiene extensiones compartidas, actualmente SQLAlchemy.
- `app/registry.py`: registra los módulos funcionales.
- `app/bootstrap.py`: prepara la base de datos, migraciones y datos iniciales.
- `app/health.py`: expone `/health` para controlar el servicio en Render.
- `app/models.py`: mantiene temporalmente los modelos juntos para no arriesgar los datos existentes.
- `app/*.py`: cada módulo funcional conserva su blueprint y sus rutas.

## Motivo de esta reorganización

La separación reduce dependencias circulares y permite agregar Finanzas, Gastos y Reportes sin seguir agrandando `app/__init__.py`.

## Compatibilidad

- El punto de inicio continúa siendo `gunicorn run:app`.
- Las rutas y pantallas actuales no cambian.
- No se elimina ni renombra ninguna tabla existente.
- La estructura sigue siendo compatible con Render.
