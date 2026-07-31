from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .models import User

auth_bp = Blueprint("auth", __name__)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and user.check_password(request.form["password"]):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard.index"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("auth/login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
