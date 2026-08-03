from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import quote as url_quote
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from sqlalchemy import or_
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from . import db
from .auth import login_required
from .models import Quote, QuoteItem, Product, Customer, SalesOrder, SaleItem

quotes_bp = Blueprint("quotes", __name__, url_prefix="/quotes")

VALID_STATUSES = ("Borrador", "Enviada", "Aceptada", "Rechazada", "Vencida", "Convertida")

def next_quote_number():
    last = Quote.query.order_by(Quote.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"COT-{next_id:06d}"

def parse_items(form):
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")
    prices = form.getlist("unit_price[]")
    discounts = form.getlist("discount_pct[]")

    items = []
    for product_id, quantity, price, discount in zip(product_ids, quantities, prices, discounts):
        if not product_id:
            continue

        product = Product.query.get(int(product_id))
        if not product or not product.active:
            raise ValueError("Uno de los productos ya no está disponible.")

        qty = int(quantity)
        unit_price = float(price)
        discount_pct = float(discount or 0)

        if qty <= 0 or unit_price < 0 or not 0 <= discount_pct <= 100:
            raise ValueError("Revisá cantidades, precios y descuentos.")

        items.append((product, qty, unit_price, discount_pct))

    if not items:
        raise ValueError("Agregá al menos un producto.")

    return items

def apply_items(quote, items):
    quote.items.clear()
    for product, qty, unit_price, discount_pct in items:
        quote.items.append(QuoteItem(
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            discount_pct=discount_pct,
            cost_snapshot=product.avg_cost,
        ))

def validate_stock_for_conversion(quote):
    requested = {}
    for item in quote.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    for product_id, qty in requested.items():
        product = Product.query.get(product_id)
        if qty > product.available_stock:
            raise ValueError(
                f"Stock insuficiente para {product.brand} {product.model}. "
                f"Disponible: {product.available_stock}."
            )

@quotes_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        try:
            date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            valid_until = datetime.strptime(request.form["valid_until"], "%Y-%m-%d").date()
            customer_id = int(request.form["customer_id"])
            items = parse_items(request.form)
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("quotes.index"))

        customer = Customer.query.get(customer_id)
        if not customer or not customer.active:
            flash("El cliente seleccionado no está disponible.", "error")
            return redirect(url_for("quotes.index"))

        quote = Quote(
            number=next_quote_number(),
            date=date_value,
            valid_until=valid_until,
            customer_id=customer.id,
            customer=customer.name,
            currency=request.form.get("currency") or "USD",
            status=request.form.get("status") or "Borrador",
            notes=request.form.get("notes", "").strip() or None,
        )
        apply_items(quote, items)
        db.session.add(quote)
        db.session.commit()

        flash("Cotización creada correctamente.", "success")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    customer_id = request.args.get("customer_id", "")

    query = Quote.query

    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Quote.number.ilike(term),
            Quote.customer.ilike(term),
        ))
    if status:
        query = query.filter_by(status=status)
    if customer_id:
        query = query.filter_by(customer_id=int(customer_id))

    rows = query.order_by(Quote.date.desc(), Quote.id.desc()).all()
    customers = Customer.query.filter_by(active=True).order_by(Customer.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()

    totals = {
        "count": len(rows),
        "amount": sum(q.total for q in rows if q.status not in ("Rechazada", "Vencida")),
        "accepted": sum(q.total for q in rows if q.status in ("Aceptada", "Convertida")),
        "converted": sum(1 for q in rows if q.status == "Convertida"),
    }

    return render_template(
        "quotes/index.html",
        rows=rows,
        customers=customers,
        products=products,
        totals=totals,
        q=q,
        selected_status=status,
        selected_customer=customer_id,
        default_date=datetime.now().date().isoformat(),
        default_valid_until=(datetime.now().date() + timedelta(days=15)).isoformat(),
    )

@quotes_bp.route("/<int:quote_id>")
@login_required
def detail(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    return render_template("quotes/detail.html", quote=quote)

@quotes_bp.route("/<int:quote_id>/edit", methods=["GET", "POST"])
@login_required
def edit(quote_id):
    quote = Quote.query.get_or_404(quote_id)

    if quote.status == "Convertida":
        flash("Una cotización convertida no puede editarse.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    if request.method == "POST":
        try:
            quote.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
            quote.valid_until = datetime.strptime(request.form["valid_until"], "%Y-%m-%d").date()
            customer_id = int(request.form["customer_id"])
            items = parse_items(request.form)
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("quotes.edit", quote_id=quote.id))

        customer = Customer.query.get(customer_id)
        if not customer or not customer.active:
            flash("El cliente seleccionado no está disponible.", "error")
            return redirect(url_for("quotes.edit", quote_id=quote.id))

        quote.customer_id = customer.id
        quote.customer = customer.name
        quote.currency = request.form.get("currency") or "USD"
        quote.status = request.form.get("status") or "Borrador"
        quote.notes = request.form.get("notes", "").strip() or None
        apply_items(quote, items)

        db.session.commit()
        flash("Cotización actualizada.", "success")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    customers = Customer.query.filter_by(active=True).order_by(Customer.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.brand, Product.model).all()
    return render_template(
        "quotes/edit.html",
        quote=quote,
        customers=customers,
        products=products,
    )

@quotes_bp.post("/<int:quote_id>/status/<status>")
@login_required
def change_status(quote_id, status):
    quote = Quote.query.get_or_404(quote_id)
    if status not in VALID_STATUSES or status == "Convertida":
        flash("Estado inválido.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))
    if quote.status == "Convertida":
        flash("La cotización ya fue convertida en venta.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    quote.status = status
    db.session.commit()
    flash("Estado actualizado.", "success")
    return redirect(url_for("quotes.detail", quote_id=quote.id))

@quotes_bp.post("/<int:quote_id>/duplicate")
@login_required
def duplicate(quote_id):
    source = Quote.query.get_or_404(quote_id)
    duplicate = Quote(
        number=next_quote_number(),
        date=datetime.now().date(),
        valid_until=datetime.now().date() + timedelta(days=15),
        customer_id=source.customer_id,
        customer=source.customer,
        currency=source.currency,
        status="Borrador",
        notes=source.notes,
    )
    for item in source.items:
        duplicate.items.append(QuoteItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_pct=item.discount_pct,
            cost_snapshot=item.product.avg_cost,
        ))

    db.session.add(duplicate)
    db.session.commit()
    flash("Cotización duplicada como nuevo borrador.", "success")
    return redirect(url_for("quotes.edit", quote_id=duplicate.id))

@quotes_bp.post("/<int:quote_id>/convert")
@login_required
def convert_to_sale(quote_id):
    quote = Quote.query.get_or_404(quote_id)

    if quote.status == "Convertida" or quote.converted_sale_id:
        flash("Esta cotización ya fue convertida.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    try:
        validate_stock_for_conversion(quote)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    sale = SalesOrder(
        date=datetime.now().date(),
        reference=quote.number,
        customer_id=quote.customer_id,
        customer=quote.customer,
        whatsapp=quote.customer_record.whatsapp,
        currency=quote.currency,
        payment_method="Transferencia",
        collected=0,
        status="Entregada",
        notes=f"Venta generada desde {quote.number}" + (f". {quote.notes}" if quote.notes else ""),
    )

    for item in quote.items:
        sale.items.append(SaleItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            discount_pct=item.discount_pct,
            cost_snapshot=item.product.avg_cost,
        ))

    db.session.add(sale)
    db.session.flush()
    quote.status = "Convertida"
    quote.converted_sale_id = sale.id
    db.session.commit()

    flash("Cotización convertida en venta correctamente.", "success")
    return redirect(url_for("sales.detail", sale_id=sale.id))


def money(value):
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def build_quote_pdf(quote):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=quote.number,
        author="ARVOX",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ArvoxTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=28,
        textColor=colors.HexColor("#111111"),
        spaceAfter=1 * mm,
    ))
    styles.add(ParagraphStyle(
        name="ArvoxOrange",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#F58220"),
        uppercase=True,
    ))
    styles.add(ParagraphStyle(
        name="SmallMuted",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#666666"),
    ))
    styles.add(ParagraphStyle(
        name="RightStrong",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        alignment=TA_RIGHT,
    ))

    story = []

    header = Table([
        [
            [
                Paragraph("ARVOX", styles["ArvoxTitle"]),
                Paragraph("DONDE JUEGA LA CALIDAD", styles["ArvoxOrange"]),
            ],
            [
                Paragraph("COTIZACIÓN", styles["RightStrong"]),
                Paragraph(f"<b>{quote.number}</b>", styles["RightStrong"]),
                Paragraph(f"Fecha: {quote.date.strftime('%d/%m/%Y')}", styles["SmallMuted"]),
                Paragraph(
                    f"Válida hasta: {quote.valid_until.strftime('%d/%m/%Y') if quote.valid_until else '-'}",
                    styles["SmallMuted"],
                ),
            ],
        ]
    ], colWidths=[105 * mm, 50 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor("#F58220")),
    ]))
    story.append(header)
    story.append(Spacer(1, 8 * mm))

    customer_data = [
        [Paragraph("<b>CLIENTE</b>", styles["ArvoxOrange"]), ""],
        ["Nombre", quote.customer],
        ["WhatsApp", quote.customer_record.whatsapp or "-"],
        ["Email", quote.customer_record.email or "-"],
        ["Moneda", quote.currency],
        ["Estado", quote.status],
    ]
    customer_table = Table(customer_data, colWidths=[35 * mm, 120 * mm])
    customer_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#F3F3F3")),
        ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#666666")),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
    ]))
    story.append(customer_table)
    story.append(Spacer(1, 8 * mm))

    product_rows = [["Producto", "Cant.", "Precio", "Desc.", "Subtotal"]]
    for item in quote.items:
        product_rows.append([
            Paragraph(
                f"<b>{item.product.brand}</b><br/>{item.product.model}",
                styles["Normal"],
            ),
            str(item.quantity),
            f"{quote.currency} {money(item.unit_price)}",
            f"{money(item.discount_pct or 0)}%",
            f"{quote.currency} {money(item.subtotal)}",
        ])

    products_table = Table(
        product_rows,
        colWidths=[76 * mm, 16 * mm, 28 * mm, 19 * mm, 31 * mm],
        repeatRows=1,
    )
    products_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D5D5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(products_table)
    story.append(Spacer(1, 7 * mm))

    total_table = Table([
        ["Subtotal", f"{quote.currency} {money(quote.subtotal)}"],
        ["Descuento", f"{quote.currency} {money(quote.discount_total)}"],
        ["TOTAL", f"{quote.currency} {money(quote.total)}"],
    ], colWidths=[120 * mm, 50 * mm])
    total_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, 2), 14),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor("#F58220")),
        ("LINEABOVE", (0, 2), (-1, 2), 1, colors.HexColor("#F58220")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(total_table)

    if quote.notes:
        story.append(Spacer(1, 8 * mm))
        story.append(KeepTogether([
            Paragraph("CONDICIONES Y OBSERVACIONES", styles["ArvoxOrange"]),
            Spacer(1, 2 * mm),
            Paragraph(quote.notes.replace("\n", "<br/>"), styles["Normal"]),
        ]))

    story.append(Spacer(1, 14 * mm))
    footer = Table([
        [
            Paragraph(
                "Gracias por elegir ARVOX.<br/>Esta cotización está sujeta a disponibilidad de stock.",
                styles["SmallMuted"],
            ),
            Paragraph("ARVOX · Donde juega la calidad.", styles["RightStrong"]),
        ]
    ], colWidths=[100 * mm, 70 * mm])
    footer.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(footer)

    doc.build(story)
    buffer.seek(0)
    return buffer

@quotes_bp.get("/<int:quote_id>/pdf")
@login_required
def pdf(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    buffer = build_quote_pdf(quote)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{quote.number}_{quote.customer.replace(' ', '_')}.pdf",
    )

@quotes_bp.get("/<int:quote_id>/whatsapp")
@login_required
def whatsapp(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    customer = quote.customer_record
    number = "".join(ch for ch in (customer.whatsapp or "") if ch.isdigit())

    if not number:
        flash("El cliente no tiene un WhatsApp cargado.", "error")
        return redirect(url_for("quotes.detail", quote_id=quote.id))

    pdf_url = url_for("quotes.pdf", quote_id=quote.id, _external=True)
    message = (
        f"Hola {customer.name}. Te envío la cotización {quote.number} de ARVOX "
        f"por un total de {quote.currency} {money(quote.total)}. "
        f"Podés descargarla desde: {pdf_url}"
    )
    return redirect(f"https://wa.me/{number}?text={url_quote(message)}")
