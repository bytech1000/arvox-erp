import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from . import db
from .auth import login_required
from .models import MasterCatalogItem

catalog_bp = Blueprint("catalog", __name__, url_prefix="/catalog")

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def clean_text(value):
    return " ".join((value or "").strip().split())


def normalized_key(brand, model):
    return clean_text(brand).casefold(), clean_text(model).casefold()


def parse_csv(raw):
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("El archivo no contiene encabezados.")

    names = {clean_text(name).casefold(): name for name in reader.fieldnames if name}
    brand_col = names.get("marca") or names.get("brand")
    model_col = names.get("modelo") or names.get("model")
    if not brand_col or not model_col:
        raise ValueError("El archivo debe tener las columnas Marca y Modelo.")

    rows = []
    for row in reader:
        brand = clean_text(row.get(brand_col))
        model = clean_text(row.get(model_col))
        if brand and model:
            rows.append((brand, model))
    return rows


def parse_xlsx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", XLSX_NS):
                texts = [
                    node.text or ""
                    for node in item.iter(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                    )
                ]
                shared.append("".join(texts))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels
        }
        sheet = workbook.find("a:sheets/a:sheet", XLSX_NS)
        if sheet is None:
            raise ValueError("El Excel no contiene hojas.")

        rel_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        target = rel_map.get(rel_id, "worksheets/sheet1.xml")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        worksheet = ET.fromstring(archive.read(target))

        matrix = []
        for row in worksheet.findall(".//a:sheetData/a:row", XLSX_NS):
            values = {}
            for cell in row.findall("a:c", XLSX_NS):
                ref = cell.attrib.get("r", "")
                match = re.match(r"[A-Z]+", ref)
                if not match:
                    continue
                col = match.group(0)
                cell_type = cell.attrib.get("t")
                value = ""
                if cell_type == "inlineStr":
                    inline = cell.find("a:is", XLSX_NS)
                    if inline is not None:
                        value = "".join(
                            node.text or ""
                            for node in inline.iter(
                                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                            )
                        )
                else:
                    value_node = cell.find("a:v", XLSX_NS)
                    if value_node is not None:
                        raw_value = value_node.text or ""
                        if cell_type == "s":
                            value = shared[int(raw_value)]
                        else:
                            value = raw_value
                values[col] = clean_text(str(value))
            matrix.append(values)

    if not matrix:
        raise ValueError("El Excel está vacío.")

    header = {value.casefold(): col for col, value in matrix[0].items() if value}
    brand_col = header.get("marca") or header.get("brand")
    model_col = header.get("modelo") or header.get("model")
    if not brand_col or not model_col:
        raise ValueError("El Excel debe tener las columnas Marca y Modelo.")

    rows = []
    for row in matrix[1:]:
        brand = clean_text(row.get(brand_col))
        model = clean_text(row.get(model_col))
        if brand and model:
            rows.append((brand, model))
    return rows


def import_rows(rows):
    existing = {
        normalized_key(item.brand, item.model)
        for item in MasterCatalogItem.query.all()
    }
    incoming_seen = set()
    created = 0
    duplicates = 0

    for brand, model in rows:
        key = normalized_key(brand, model)
        if key in incoming_seen or key in existing:
            duplicates += 1
            continue
        incoming_seen.add(key)
        existing.add(key)
        db.session.add(MasterCatalogItem(brand=clean_text(brand), model=clean_text(model)))
        created += 1

    db.session.commit()
    return created, duplicates


@catalog_bp.get("/")
@login_required
def index():
    q = clean_text(request.args.get("q"))
    brand = clean_text(request.args.get("brand"))
    active = request.args.get("active", "1")

    query = MasterCatalogItem.query
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            MasterCatalogItem.brand.ilike(term),
            MasterCatalogItem.model.ilike(term),
        ))
    if brand:
        query = query.filter(MasterCatalogItem.brand == brand)
    if active in ("0", "1"):
        query = query.filter(MasterCatalogItem.active == (active == "1"))

    rows = query.order_by(MasterCatalogItem.brand, MasterCatalogItem.model).all()
    brands = [
        row[0]
        for row in db.session.query(MasterCatalogItem.brand)
        .distinct()
        .order_by(MasterCatalogItem.brand)
        .all()
    ]
    total = MasterCatalogItem.query.count()
    active_count = MasterCatalogItem.query.filter_by(active=True).count()

    return render_template(
        "catalog/index.html",
        rows=rows,
        brands=brands,
        q=q,
        selected_brand=brand,
        selected_active=active,
        total=total,
        active_count=active_count,
    )


@catalog_bp.post("/add")
@login_required
def add():
    brand = clean_text(request.form.get("brand"))
    model = clean_text(request.form.get("model"))
    if not brand or not model:
        flash("Completá marca y modelo.", "error")
        return redirect(url_for("catalog.index"))

    exists = MasterCatalogItem.query.filter(
        func.lower(MasterCatalogItem.brand) == brand.casefold(),
        func.lower(MasterCatalogItem.model) == model.casefold(),
    ).first()
    if exists:
        flash("Ese modelo ya existe en el Catálogo Maestro.", "error")
        return redirect(url_for("catalog.index"))

    db.session.add(MasterCatalogItem(brand=brand, model=model))
    db.session.commit()
    flash("Modelo agregado al Catálogo Maestro.", "success")
    return redirect(url_for("catalog.index"))


@catalog_bp.post("/import")
@login_required
def import_file():
    uploaded = request.files.get("catalog_file")
    if not uploaded or not uploaded.filename:
        flash("Seleccioná un archivo Excel o CSV.", "error")
        return redirect(url_for("catalog.index"))

    raw = uploaded.read()
    if len(raw) > 10 * 1024 * 1024:
        flash("El archivo supera el límite de 10 MB.", "error")
        return redirect(url_for("catalog.index"))

    try:
        filename = uploaded.filename.lower()
        if filename.endswith(".xlsx"):
            rows = parse_xlsx(raw)
        elif filename.endswith(".csv"):
            rows = parse_csv(raw)
        else:
            raise ValueError("Formato no válido. Usá .xlsx o .csv.")

        created, duplicates = import_rows(rows)
        flash(
            f"Importación terminada: {created} modelos nuevos y "
            f"{duplicates} duplicados omitidos.",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"No se pudo importar el catálogo: {exc}", "error")

    return redirect(url_for("catalog.index"))


@catalog_bp.post("/<int:item_id>/toggle")
@login_required
def toggle(item_id):
    item = MasterCatalogItem.query.get_or_404(item_id)
    item.active = not item.active
    db.session.commit()
    flash("Estado del modelo actualizado.", "success")
    return redirect(url_for("catalog.index"))


@catalog_bp.post("/<int:item_id>/delete")
@login_required
def delete(item_id):
    item = MasterCatalogItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Modelo eliminado del Catálogo Maestro.", "success")
    return redirect(url_for("catalog.index"))
