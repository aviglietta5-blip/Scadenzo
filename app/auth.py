"""Registrazione dello studio, login, logout e protezioni di sicurezza."""
import functools
import hmac
import secrets

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import crea_tipi_predefiniti, get_db

bp = Blueprint("auth", __name__)

PASSWORD_MIN = 10


# --- Protezione CSRF: ogni form POST deve rimandare il token di sessione ---

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def verifica_csrf():
    if request.method != "POST":
        return
    atteso = session.get("_csrf")
    ricevuto = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not atteso or not ricevuto or not hmac.compare_digest(atteso, ricevuto):
        abort(400, "Sessione scaduta o richiesta non valida. Ricarica la pagina.")


# --- Utente collegato ---

def carica_utente():
    g.utente = None
    uid = session.get("uid")
    if uid is None:
        return
    row = get_db().execute(
        "SELECT u.*, s.nome AS studio_nome FROM utenti u "
        "JOIN studi s ON s.id = u.studio_id WHERE u.id = ? AND u.attivo = 1",
        (uid,),
    ).fetchone()
    if row is None:
        session.clear()
    g.utente = row


def login_richiesto(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.utente is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def solo_admin(view):
    @functools.wraps(view)
    @login_richiesto
    def wrapped(*args, **kwargs):
        if g.utente["ruolo"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def valida_password(pw):
    if len(pw) < PASSWORD_MIN:
        return f"La password deve avere almeno {PASSWORD_MIN} caratteri."
    return None


def _accedi(user_id):
    session.clear()  # nuova sessione dopo il login
    session["uid"] = user_id
    session.permanent = True


@bp.route("/registrati", methods=["GET", "POST"])
def registrati():
    if request.method == "POST":
        studio = request.form.get("studio", "").strip()
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        errore = None
        if not studio or not nome or not email:
            errore = "Compila tutti i campi."
        elif "@" not in email:
            errore = "Indirizzo email non valido."
        else:
            errore = valida_password(pw)
        db = get_db()
        if not errore and db.execute(
                "SELECT 1 FROM utenti WHERE email = ?", (email,)).fetchone():
            errore = "Esiste già un account con questa email."
        if errore:
            flash(errore, "errore")
        else:
            cur = db.execute("INSERT INTO studi (nome) VALUES (?)", (studio,))
            studio_id = cur.lastrowid
            cur = db.execute(
                "INSERT INTO utenti (studio_id, nome, email, password_hash, ruolo) "
                "VALUES (?, ?, ?, ?, 'admin')",
                (studio_id, nome, email, generate_password_hash(pw)),
            )
            crea_tipi_predefiniti(db, studio_id)
            db.commit()
            _accedi(cur.lastrowid)
            flash("Benvenuto! Il tuo studio è pronto.", "ok")
            return redirect(url_for("main.cruscotto"))
    return render_template("auth/registrati.html")


@bp.route("/accedi", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        row = get_db().execute(
            "SELECT id, password_hash, attivo FROM utenti WHERE email = ?", (email,)
        ).fetchone()
        if row and row["attivo"] and check_password_hash(row["password_hash"], pw):
            _accedi(row["id"])
            dest = request.args.get("next", "")
            # solo percorsi interni, per evitare redirect verso siti esterni
            if not dest.startswith("/") or dest.startswith("//"):
                dest = url_for("main.cruscotto")
            return redirect(dest)
        flash("Email o password non corretti.", "errore")
    return render_template("auth/accedi.html")


@bp.route("/esci", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_richiesto
def cambia_password():
    if request.method == "POST":
        attuale = request.form.get("attuale", "")
        nuova = request.form.get("nuova", "")
        if not check_password_hash(g.utente["password_hash"], attuale):
            flash("La password attuale non è corretta.", "errore")
        elif (err := valida_password(nuova)):
            flash(err, "errore")
        else:
            db = get_db()
            db.execute("UPDATE utenti SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(nuova), g.utente["id"]))
            db.commit()
            flash("Password aggiornata.", "ok")
            return redirect(url_for("main.cruscotto"))
    return render_template("auth/password.html")
