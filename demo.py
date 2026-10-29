"""Crea uno studio dimostrativo con dati INVENTATI, utile per presentare l'app.

Uso:  python demo.py      →  accesso: demo@scadenzo.it / demo-scadenzo
"""
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.db import crea_tipi_predefiniti, get_db
from app.date_utils import primo_giorno_lavorativo

CLIENTI = ["Bottega Lumière SRL", "Ferramenta Colli Albani SNC", "Studio Dentistico Aurora",
           "Pasticceria Dolce Vita SRL", "Officina Moretti & Figli", "Trattoria Il Glicine SAS",
           "Green Bike Roma SRL", "Agenzia Viaggi Orizzonte", "Tipografia Nuova Stampa SRL",
           "Elettrica Tevere SNC", "Panificio San Lorenzo", "Bio Market Prati SRL"]
STAFF = [("Giulia Bianchi", "giulia@demo.it"), ("Marco Verdi", "marco@demo.it")]


def main():
    app = create_app()
    with app.app_context():
        db = get_db()
        if db.execute("SELECT 1 FROM utenti WHERE email='demo@scadenzo.it'").fetchone():
            print("Studio demo già presente.")
            return
        random.seed(7)
        sid = db.execute("INSERT INTO studi (nome) VALUES ('Studio Esempio')").lastrowid
        crea_tipi_predefiniti(db, sid)
        pw = generate_password_hash("demo-scadenzo")
        ids = [db.execute("INSERT INTO utenti (studio_id, nome, email, password_hash, ruolo) "
                          "VALUES (?, 'Anna Demo', 'demo@scadenzo.it', ?, 'admin')",
                          (sid, pw)).lastrowid]
        for nome, email in STAFF:
            ids.append(db.execute("INSERT INTO utenti (studio_id, nome, email, password_hash) "
                                  "VALUES (?,?,?,?)", (sid, nome, email, pw)).lastrowid)
        tipi = {r["nome"]: r["id"] for r in db.execute(
            "SELECT id, nome FROM tipi_scadenza WHERE studio_id=?", (sid,))}
        oggi = date.today()
        for i, nome in enumerate(CLIENTI):
            ref = ids[i % len(ids)]
            cid = db.execute("INSERT INTO clienti (studio_id, ragione_sociale, referente_id) "
                             "VALUES (?,?,?)", (sid, nome, ref)).lastrowid
            for delta in (-1, 0, 1):
                m = (oggi.replace(day=1) + timedelta(days=32 * delta)).replace(day=16)
                d = primo_giorno_lavorativo(m)
                stato = "fatto" if delta < 0 or (delta == 0 and random.random() < .4) else "da_fare"
                db.execute("INSERT INTO scadenze (studio_id, cliente_id, tipo_id, data, "
                           "referente_id, importo, stato, ricevuta) VALUES (?,?,?,?,?,?,?,?)",
                           (sid, cid, tipi["F24"], d.isoformat(), ref,
                            round(random.uniform(150, 4800), 2), stato,
                            1 if stato == "fatto" and random.random() < .7 else 0))
            if i % 3 == 0:
                d = oggi + timedelta(days=random.randint(-4, 6))
                db.execute("INSERT INTO scadenze (studio_id, cliente_id, tipo_id, data, "
                           "referente_id, note) VALUES (?,?,?,?,?,?)",
                           (sid, cid, random.choice([tipi["770"], tipi["IRAP"], tipi["LIPE"]]),
                            d.isoformat(), ref, "Attendere i dati dal cliente" if i == 3 else None))
        db.commit()
        print("Studio demo creato: demo@scadenzo.it / demo-scadenzo")


if __name__ == "__main__":
    main()
