"""Pagine dell'app: cruscotto, scadenze, clienti, tipi, collaboratori."""
import csv
import io
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, redirect,
                   render_template, request, url_for)
from werkzeug.security import generate_password_hash

from .auth import login_richiesto, solo_admin, valida_password
from .date_utils import MESI_IT, primo_giorno_lavorativo, prossima_scadenza
from .db import get_db

bp = Blueprint("main", __name__)


# --- Helper: leggere solo righe dello studio collegato ---------------------

def sid():
    return g.utente["studio_id"]


def riga_dello_studio(tabella, id_):
    assert tabella in {"clienti", "tipi_scadenza", "scadenze", "utenti"}
    row = get_db().execute(
        f"SELECT * FROM {tabella} WHERE id = ? AND studio_id = ?", (id_, sid())
    ).fetchone()
    if row is None:
        abort(404)
    return dict(row)


def id_opzionale(tabella, valore):
    """Converte un id dal form verificando che appartenga allo studio."""
    if not valore:
        return None
    try:
        return riga_dello_studio(tabella, int(valore))["id"]
    except ValueError:
        abort(400)


def leggi_data(valore):
    try:
        return datetime.strptime(valore, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def leggi_importo(valore):
    valore = (valore or "").strip().replace(".", "").replace(",", ".")
    if not valore:
        return None
    try:
        return round(float(valore), 2)
    except ValueError:
        return None


def collaboratori():
    return get_db().execute(
        "SELECT id, nome FROM utenti WHERE studio_id = ? AND attivo = 1 ORDER BY nome",
        (sid(),)).fetchall()


def clienti_attivi():
    return get_db().execute(
        "SELECT id, ragione_sociale, referente_id FROM clienti "
        "WHERE studio_id = ? AND attivo = 1 ORDER BY ragione_sociale",
        (sid(),)).fetchall()


def tipi():
    return get_db().execute(
        "SELECT * FROM tipi_scadenza WHERE studio_id = ? ORDER BY nome",
        (sid(),)).fetchall()


SELECT_SCADENZE = """
    SELECT s.*, c.ragione_sociale, t.nome AS tipo_nome, t.colore,
           u.nome AS referente_nome
    FROM scadenze s
    JOIN clienti c ON c.id = s.cliente_id
    JOIN tipi_scadenza t ON t.id = s.tipo_id
    LEFT JOIN utenti u ON u.id = s.referente_id
    WHERE s.studio_id = ?
"""


@bp.app_template_filter("data_it")
def data_it(valore):
    d = leggi_data(valore) if isinstance(valore, str) else valore
    return d.strftime("%d/%m/%Y") if d else ""


@bp.app_template_filter("euro")
def euro(valore):
    if valore is None:
        return ""
    s = f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {s}"


# --- Cruscotto -------------------------------------------------------------

@bp.route("/")
@login_richiesto
def cruscotto():
    db = get_db()
    oggi = date.today()
    tra7 = oggi + timedelta(days=7)
    mie = request.args.get("mie") == "1"
    filtro, params = "", [sid()]
    if mie:
        filtro, params = " AND s.referente_id = ?", [sid(), g.utente["id"]]

    def elenco(cond, extra):
        return db.execute(SELECT_SCADENZE + filtro + cond + " ORDER BY s.data, c.ragione_sociale",
                          params + extra).fetchall()

    scadute = elenco(" AND s.stato = 'da_fare' AND s.data < ?", [oggi.isoformat()])
    prossime = elenco(" AND s.stato = 'da_fare' AND s.data BETWEEN ? AND ?",
                      [oggi.isoformat(), tra7.isoformat()])
    inizio_mese = oggi.replace(day=1).isoformat()
    fatte_mese = db.execute(
        "SELECT COUNT(*) FROM scadenze s WHERE s.studio_id = ? " + filtro +
        " AND s.stato = 'fatto' AND s.data >= ? AND s.data < date(?, '+1 month')",
        params + [inizio_mese, inizio_mese]).fetchone()[0]
    n_clienti = db.execute("SELECT COUNT(*) FROM clienti WHERE studio_id = ? AND attivo = 1",
                           (sid(),)).fetchone()[0]
    return render_template("cruscotto.html", scadute=scadute, prossime=prossime,
                           fatte_mese=fatte_mese, n_clienti=n_clienti, mie=mie, oggi=oggi)


# --- Scadenze --------------------------------------------------------------

def filtri_scadenze():
    oggi = date.today()
    mese = request.args.get("mese") or oggi.strftime("%Y-%m")
    try:
        anno, m = (int(x) for x in mese.split("-"))
        primo = date(anno, m, 1)
    except ValueError:
        primo = oggi.replace(day=1)
    sql, params = SELECT_SCADENZE, [sid()]
    if request.args.get("tutti_i_mesi") != "1":
        sql += " AND s.data >= ? AND s.data < date(?, '+1 month')"
        params += [primo.isoformat(), primo.isoformat()]
    for campo, col in (("cliente", "s.cliente_id"), ("referente", "s.referente_id"),
                       ("tipo", "s.tipo_id")):
        v = request.args.get(campo)
        if v and v.isdigit():
            sql += f" AND {col} = ?"
            params.append(int(v))
    stato = request.args.get("stato")
    if stato in ("da_fare", "fatto"):
        sql += " AND s.stato = ?"
        params.append(stato)
    sql += " ORDER BY s.data, c.ragione_sociale"
    return sql, params, primo


@bp.route("/scadenze")
@login_richiesto
def scadenze():
    sql, params, primo = filtri_scadenze()
    righe = get_db().execute(sql, params).fetchall()
    prec = (primo - timedelta(days=1)).replace(day=1)
    succ = (primo + timedelta(days=32)).replace(day=1)
    return render_template(
        "scadenze.html", righe=righe, primo=primo, prec=prec, succ=succ,
        nome_mese=f"{MESI_IT[primo.month]} {primo.year}",
        clienti=clienti_attivi(), tipi=tipi(), collaboratori=collaboratori(),
        args=request.args)


@bp.route("/scadenze/esporta.csv")
@login_richiesto
def esporta_csv():
    sql, params, _ = filtri_scadenze()
    righe = get_db().execute(sql, params).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data", "Cliente", "Tipo", "Referente", "Importo", "Stato", "Ricevuta", "Note"])
    for r in righe:
        w.writerow([data_it(r["data"]), r["ragione_sociale"], r["tipo_nome"],
                    r["referente_nome"] or "",
                    "" if r["importo"] is None else f"{r['importo']:.2f}".replace(".", ","),
                    "Fatto" if r["stato"] == "fatto" else "Da fare",
                    "Sì" if r["ricevuta"] else "No", r["note"] or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=scadenze.csv"})


def _salva_scadenza_da_form(scadenza=None):
    f = request.form
    cliente_id = id_opzionale("clienti", f.get("cliente_id"))
    tipo_id = id_opzionale("tipi_scadenza", f.get("tipo_id"))
    d = leggi_data(f.get("data"))
    if not cliente_id or not tipo_id or not d:
        flash("Cliente, tipo e data sono obbligatori.", "errore")
        return False
    valori = (cliente_id, tipo_id, d.isoformat(),
              id_opzionale("utenti", f.get("referente_id")),
              leggi_importo(f.get("importo")), f.get("note", "").strip() or None)
    db = get_db()
    if scadenza:
        db.execute("UPDATE scadenze SET cliente_id=?, tipo_id=?, data=?, referente_id=?, "
                   "importo=?, note=? WHERE id=? AND studio_id=?",
                   valori + (scadenza["id"], sid()))
    else:
        db.execute("INSERT INTO scadenze (cliente_id, tipo_id, data, referente_id, importo, "
                   "note, studio_id) VALUES (?,?,?,?,?,?,?)", valori + (sid(),))
    db.commit()
    return True


@bp.route("/scadenze/nuova", methods=["GET", "POST"])
@login_richiesto
def nuova_scadenza():
    if request.method == "POST" and _salva_scadenza_da_form():
        flash("Scadenza aggiunta.", "ok")
        return redirect(url_for("main.scadenze", mese=request.form["data"][:7]))
    return render_template("scadenza_form.html", s=None, clienti=clienti_attivi(),
                           tipi=tipi(), collaboratori=collaboratori())


@bp.route("/scadenze/<int:id_>/modifica", methods=["GET", "POST"])
@login_richiesto
def modifica_scadenza(id_):
    s = riga_dello_studio("scadenze", id_)
    if request.method == "POST" and _salva_scadenza_da_form(s):
        flash("Scadenza aggiornata.", "ok")
        return redirect(url_for("main.scadenze", mese=request.form["data"][:7]))
    return render_template("scadenza_form.html", s=s, clienti=clienti_attivi(),
                           tipi=tipi(), collaboratori=collaboratori())


def _segna_fatta(db, s):
    """Segna fatta e, se il tipo è ricorrente, crea la scadenza successiva."""
    db.execute("UPDATE scadenze SET stato='fatto', completata_il=datetime('now') "
               "WHERE id=? AND studio_id=?", (s["id"], sid()))
    tipo = riga_dello_studio("tipi_scadenza", s["tipo_id"])
    nuova = prossima_scadenza(leggi_data(s["data"]), tipo["ricorrenza"], tipo["giorno"])
    if nuova is None:
        return None
    esiste = db.execute("SELECT 1 FROM scadenze WHERE studio_id=? AND cliente_id=? "
                        "AND tipo_id=? AND data=?",
                        (sid(), s["cliente_id"], s["tipo_id"], nuova.isoformat())).fetchone()
    if not esiste:
        db.execute("INSERT INTO scadenze (studio_id, cliente_id, tipo_id, data, referente_id) "
                   "VALUES (?,?,?,?,?)",
                   (sid(), s["cliente_id"], s["tipo_id"], nuova.isoformat(), s["referente_id"]))
        return nuova
    return None


@bp.route("/scadenze/<int:id_>/stato", methods=["POST"])
@login_richiesto
def cambia_stato(id_):
    s = riga_dello_studio("scadenze", id_)
    db = get_db()
    if s["stato"] == "fatto":
        db.execute("UPDATE scadenze SET stato='da_fare', completata_il=NULL "
                   "WHERE id=? AND studio_id=?", (id_, sid()))
    else:
        nuova = _segna_fatta(db, s)
        if nuova:
            flash(f"Fatto. Creata la prossima scadenza: {data_it(nuova)}.", "ok")
    db.commit()
    return redirect(request.form.get("torna") or url_for("main.scadenze"))


@bp.route("/scadenze/<int:id_>/ricevuta", methods=["POST"])
@login_richiesto
def cambia_ricevuta(id_):
    s = riga_dello_studio("scadenze", id_)
    db = get_db()
    db.execute("UPDATE scadenze SET ricevuta=? WHERE id=? AND studio_id=?",
               (0 if s["ricevuta"] else 1, id_, sid()))
    db.commit()
    return redirect(request.form.get("torna") or url_for("main.scadenze"))


@bp.route("/scadenze/<int:id_>/elimina", methods=["POST"])
@login_richiesto
def elimina_scadenza(id_):
    riga_dello_studio("scadenze", id_)
    db = get_db()
    db.execute("DELETE FROM scadenze WHERE id=? AND studio_id=?", (id_, sid()))
    db.commit()
    flash("Scadenza eliminata.", "ok")
    return redirect(request.form.get("torna") or url_for("main.scadenze"))


@bp.route("/scadenze/azione-multipla", methods=["POST"])
@login_richiesto
def azione_multipla():
    ids = [int(x) for x in request.form.getlist("sel") if x.isdigit()]
    azione = request.form.get("azione")
    db = get_db()
    n = 0
    for id_ in ids:
        s = db.execute("SELECT * FROM scadenze WHERE id=? AND studio_id=?",
                       (id_, sid())).fetchone()
        if s is None:
            continue
        if azione == "fatto" and s["stato"] != "fatto":
            _segna_fatta(db, s)
            n += 1
        elif azione == "elimina":
            db.execute("DELETE FROM scadenze WHERE id=? AND studio_id=?", (id_, sid()))
            n += 1
    db.commit()
    if n:
        flash(f"{n} scadenze aggiornate.", "ok")
    return redirect(request.form.get("torna") or url_for("main.scadenze"))


@bp.route("/scadenze/in-blocco", methods=["GET", "POST"])
@login_richiesto
def scadenze_in_blocco():
    if request.method == "POST":
        tipo_id = id_opzionale("tipi_scadenza", request.form.get("tipo_id"))
        d = leggi_data(request.form.get("data"))
        sel = [int(x) for x in request.form.getlist("clienti") if x.isdigit()]
        if not tipo_id or not d or not sel:
            flash("Scegli tipo, data e almeno un cliente.", "errore")
        else:
            if request.form.get("lavorativo") == "1":
                d = primo_giorno_lavorativo(d)
            db = get_db()
            creati = 0
            for cid in sel:
                c = db.execute("SELECT id, referente_id FROM clienti WHERE id=? AND studio_id=?",
                               (cid, sid())).fetchone()
                if c is None:
                    continue
                if db.execute("SELECT 1 FROM scadenze WHERE studio_id=? AND cliente_id=? "
                              "AND tipo_id=? AND data=?",
                              (sid(), cid, tipo_id, d.isoformat())).fetchone():
                    continue
                db.execute("INSERT INTO scadenze (studio_id, cliente_id, tipo_id, data, "
                           "referente_id) VALUES (?,?,?,?,?)",
                           (sid(), cid, tipo_id, d.isoformat(), c["referente_id"]))
                creati += 1
            db.commit()
            flash(f"Create {creati} scadenze per il {data_it(d)}.", "ok")
            return redirect(url_for("main.scadenze", mese=d.strftime("%Y-%m")))
    return render_template("scadenze_blocco.html", clienti=clienti_attivi(), tipi=tipi(),
                           collaboratori=collaboratori())


# --- Clienti ---------------------------------------------------------------

@bp.route("/clienti")
@login_richiesto
def clienti():
    righe = get_db().execute(
        "SELECT c.*, u.nome AS referente_nome, "
        "(SELECT COUNT(*) FROM scadenze s WHERE s.cliente_id = c.id AND s.stato='da_fare') "
        "AS aperte FROM clienti c LEFT JOIN utenti u ON u.id = c.referente_id "
        "WHERE c.studio_id = ? ORDER BY c.attivo DESC, c.ragione_sociale", (sid(),)).fetchall()
    return render_template("clienti.html", righe=righe)


@bp.route("/clienti/nuovo", methods=["GET", "POST"])
@bp.route("/clienti/<int:id_>/modifica", methods=["GET", "POST"])
@login_richiesto
def cliente_form(id_=None):
    c = riga_dello_studio("clienti", id_) if id_ else None
    if request.method == "POST":
        f = request.form
        nome = f.get("ragione_sociale", "").strip()
        if not nome:
            flash("La ragione sociale è obbligatoria.", "errore")
        else:
            valori = (nome, f.get("codice_fiscale", "").strip().upper() or None,
                      f.get("partita_iva", "").strip() or None,
                      id_opzionale("utenti", f.get("referente_id")),
                      f.get("note", "").strip() or None,
                      1 if f.get("attivo", "1") == "1" else 0)
            db = get_db()
            if c:
                db.execute("UPDATE clienti SET ragione_sociale=?, codice_fiscale=?, "
                           "partita_iva=?, referente_id=?, note=?, attivo=? "
                           "WHERE id=? AND studio_id=?", valori + (c["id"], sid()))
            else:
                db.execute("INSERT INTO clienti (ragione_sociale, codice_fiscale, partita_iva, "
                           "referente_id, note, attivo, studio_id) VALUES (?,?,?,?,?,?,?)",
                           valori + (sid(),))
            db.commit()
            flash("Cliente salvato.", "ok")
            return redirect(url_for("main.clienti"))
    return render_template("cliente_form.html", c=c, collaboratori=collaboratori())


@bp.route("/clienti/<int:id_>/elimina", methods=["POST"])
@solo_admin
def elimina_cliente(id_):
    riga_dello_studio("clienti", id_)
    db = get_db()
    db.execute("DELETE FROM clienti WHERE id=? AND studio_id=?", (id_, sid()))
    db.commit()
    flash("Cliente eliminato insieme alle sue scadenze.", "ok")
    return redirect(url_for("main.clienti"))


# --- Tipi di scadenza ------------------------------------------------------

@bp.route("/tipi", methods=["GET", "POST"])
@login_richiesto
def tipi_pagina():
    if request.method == "POST":
        if g.utente["ruolo"] != "admin":
            abort(403)
        f = request.form
        nome = f.get("nome", "").strip()
        ric = f.get("ricorrenza", "nessuna")
        giorno = f.get("giorno", "").strip()
        colore = f.get("colore", "#4f6bed")
        if not nome or ric not in ("nessuna", "mensile", "trimestrale", "annuale") \
                or (giorno and not (giorno.isdigit() and 1 <= int(giorno) <= 31)) \
                or not (len(colore) == 7 and colore.startswith("#")):
            flash("Dati del tipo non validi.", "errore")
        else:
            db = get_db()
            valori = (nome, colore, ric, int(giorno) if giorno else None)
            if f.get("id"):
                t = riga_dello_studio("tipi_scadenza", int(f["id"]))
                db.execute("UPDATE tipi_scadenza SET nome=?, colore=?, ricorrenza=?, giorno=? "
                           "WHERE id=? AND studio_id=?", valori + (t["id"], sid()))
            else:
                db.execute("INSERT INTO tipi_scadenza (nome, colore, ricorrenza, giorno, "
                           "studio_id) VALUES (?,?,?,?,?)", valori + (sid(),))
            db.commit()
            flash("Tipo salvato.", "ok")
        return redirect(url_for("main.tipi_pagina"))
    return render_template("tipi.html", tipi=tipi())


@bp.route("/tipi/<int:id_>/elimina", methods=["POST"])
@solo_admin
def elimina_tipo(id_):
    riga_dello_studio("tipi_scadenza", id_)
    db = get_db()
    if db.execute("SELECT 1 FROM scadenze WHERE tipo_id=? LIMIT 1", (id_,)).fetchone():
        flash("Non puoi eliminare un tipo usato da alcune scadenze.", "errore")
    else:
        db.execute("DELETE FROM tipi_scadenza WHERE id=? AND studio_id=?", (id_, sid()))
        db.commit()
        flash("Tipo eliminato.", "ok")
    return redirect(url_for("main.tipi_pagina"))


# --- Collaboratori e studio ------------------------------------------------

@bp.route("/collaboratori", methods=["GET", "POST"])
@solo_admin
def collaboratori_pagina():
    db = get_db()
    if request.method == "POST":
        f = request.form
        nome, email = f.get("nome", "").strip(), f.get("email", "").strip().lower()
        pw = f.get("password", "")
        ruolo = "admin" if f.get("ruolo") == "admin" else "collaboratore"
        errore = None
        if not nome or "@" not in email:
            errore = "Inserisci nome ed email validi."
        elif (err := valida_password(pw)):
            errore = err
        elif db.execute("SELECT 1 FROM utenti WHERE email=?", (email,)).fetchone():
            errore = "Esiste già un account con questa email."
        if errore:
            flash(errore, "errore")
        else:
            db.execute("INSERT INTO utenti (studio_id, nome, email, password_hash, ruolo) "
                       "VALUES (?,?,?,?,?)",
                       (sid(), nome, email, generate_password_hash(pw), ruolo))
            db.commit()
            flash(f"{nome} aggiunto. Comunicagli la password temporanea.", "ok")
        return redirect(url_for("main.collaboratori_pagina"))
    righe = db.execute("SELECT * FROM utenti WHERE studio_id=? ORDER BY attivo DESC, nome",
                       (sid(),)).fetchall()
    studio = db.execute("SELECT * FROM studi WHERE id=?", (sid(),)).fetchone()
    return render_template("collaboratori.html", righe=righe, studio=studio)


@bp.route("/collaboratori/<int:id_>/attivo", methods=["POST"])
@solo_admin
def cambia_attivo(id_):
    u = riga_dello_studio("utenti", id_)
    if u["id"] == g.utente["id"]:
        flash("Non puoi disattivare te stesso.", "errore")
    else:
        db = get_db()
        db.execute("UPDATE utenti SET attivo=? WHERE id=? AND studio_id=?",
                   (0 if u["attivo"] else 1, id_, sid()))
        db.commit()
    return redirect(url_for("main.collaboratori_pagina"))


@bp.route("/studio", methods=["POST"])
@solo_admin
def rinomina_studio():
    nome = request.form.get("nome", "").strip()
    if nome:
        db = get_db()
        db.execute("UPDATE studi SET nome=? WHERE id=?", (nome, sid()))
        db.commit()
        flash("Nome dello studio aggiornato.", "ok")
    return redirect(url_for("main.collaboratori_pagina"))
