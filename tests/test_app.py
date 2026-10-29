import re
from datetime import date

import pytest

from app import create_app
from app.date_utils import pasqua, primo_giorno_lavorativo, prossima_scadenza


@pytest.fixture
def app(tmp_path):
    return create_app({"DATABASE": str(tmp_path / "test.sqlite"), "TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


def token(client, path="/accedi"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def registra(client, studio="Studio A", email="a@a.it"):
    t = token(client, "/registrati")
    return client.post("/registrati", data={"_csrf": t, "studio": studio, "nome": "Mario Rossi",
                                            "email": email, "password": "passwordlunga1"})


def post(client, path, **data):
    data["_csrf"] = token(client, "/")
    return client.post(path, data=data)


def db(app, sql, *p):
    import sqlite3
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    r = con.execute(sql, p).fetchall()
    con.close()
    return r


# --- Date ---

def test_pasqua():
    assert pasqua(2026) == date(2026, 4, 5)
    assert pasqua(2027) == date(2027, 3, 28)


def test_slittamento_weekend_e_festivi():
    assert primo_giorno_lavorativo(date(2026, 8, 15)) == date(2026, 8, 17)  # sab Ferragosto
    assert primo_giorno_lavorativo(date(2026, 11, 16)) == date(2026, 11, 16)  # lunedì
    assert primo_giorno_lavorativo(date(2026, 4, 6)) == date(2026, 4, 7)  # Pasquetta


def test_prossimo_f24():
    # F24 del 16: dicembre 2026 il 16 è mercoledì
    assert prossima_scadenza(date(2026, 11, 16), "mensile", 16) == date(2026, 12, 16)
    # 16 gennaio 2027 è sabato -> lunedì 18
    assert prossima_scadenza(date(2026, 12, 16), "mensile", 16) == date(2027, 1, 18)
    assert prossima_scadenza(date(2026, 1, 31), "mensile", None) == date(2026, 3, 2)  # 28/2 sab
    assert prossima_scadenza(date(2026, 1, 1), "nessuna", None) is None


# --- Accesso e sicurezza ---

def test_pagine_protette(client):
    for p in ["/", "/scadenze", "/clienti", "/tipi"]:
        r = client.get(p)
        assert r.status_code == 302 and "/accedi" in r.headers["Location"]


def test_post_senza_csrf_rifiutato(client):
    r = client.post("/registrati", data={"studio": "X", "nome": "X", "email": "x@x.it",
                                         "password": "passwordlunga1"})
    assert r.status_code == 400


def test_registrazione_crea_studio_e_tipi(app, client):
    r = registra(client)
    assert r.status_code == 302
    assert len(db(app, "SELECT * FROM tipi_scadenza")) == 8
    assert client.get("/").status_code == 200


def test_login_sbagliato(client):
    registra(client)
    post(client, "/esci")
    t = token(client)
    r = client.post("/accedi", data={"_csrf": t, "email": "a@a.it", "password": "sbagliata"})
    assert "non corretti" in r.get_data(as_text=True)


def test_redirect_esterno_bloccato(client):
    registra(client)
    post(client, "/esci")
    t = token(client)
    r = client.post("/accedi?next=//evil.com", data={"_csrf": t, "email": "a@a.it",
                                                       "password": "passwordlunga1"})
    assert r.headers["Location"] == "/"


# --- Funzioni ---

def test_flusso_scadenza_ricorrente(app, client):
    registra(client)
    post(client, "/clienti/nuovo", ragione_sociale="Alfa SRL", referente_id="1")
    f24 = db(app, "SELECT id FROM tipi_scadenza WHERE nome='F24'")[0]["id"]
    post(client, "/scadenze/in-blocco", tipo_id=str(f24), data="2026-11-16",
         clienti="1", lavorativo="1")
    s = db(app, "SELECT * FROM scadenze")
    assert len(s) == 1 and s[0]["referente_id"] == 1
    r = post(client, f"/scadenze/{s[0]['id']}/stato")
    assert r.status_code == 302
    righe = db(app, "SELECT data, stato FROM scadenze ORDER BY data")
    assert [tuple(x) for x in righe] == [("2026-11-16", "fatto"), ("2026-12-16", "da_fare")]
    # di nuovo in blocco: il doppione viene saltato
    post(client, "/scadenze/in-blocco", tipo_id=str(f24), data="2026-12-16", clienti="1")
    assert len(db(app, "SELECT * FROM scadenze")) == 2


def test_pagine_si_aprono(app, client):
    registra(client)
    post(client, "/clienti/nuovo", ragione_sociale="Alfa SRL")
    post(client, "/scadenze/nuova", cliente_id="1", tipo_id="1", data="2026-11-16",
         importo="1.250,50", note="prova")
    assert db(app, "SELECT importo FROM scadenze")[0]["importo"] == 1250.50
    for p in ["/", "/?mie=1", "/scadenze?mese=2026-11", "/scadenze?tutti_i_mesi=1",
              "/scadenze/nuova", "/scadenze/1/modifica", "/scadenze/in-blocco", "/clienti",
              "/clienti/1/modifica", "/tipi", "/collaboratori", "/password"]:
        assert client.get(p).status_code == 200, p
    csv = client.get("/scadenze/esporta.csv?mese=2026-11").get_data(as_text=True)
    assert "Alfa SRL" in csv and "1250,50" in csv


# --- Isolamento tra studi: la cosa più importante ---

def test_studi_isolati(app):
    a, b = app.test_client(), app.test_client()
    registra(a, "Studio A", "a@a.it")
    registra(b, "Studio B", "b@b.it")
    post(a, "/clienti/nuovo", ragione_sociale="Cliente segreto di A")
    post(a, "/scadenze/nuova", cliente_id="1", tipo_id="1", data="2026-11-16")
    # B non vede nulla di A
    assert "segreto" not in b.get("/clienti").get_data(as_text=True)
    assert "segreto" not in b.get("/scadenze?tutti_i_mesi=1").get_data(as_text=True)
    assert "segreto" not in b.get("/scadenze/esporta.csv?tutti_i_mesi=1").get_data(as_text=True)
    # B non può aprire, modificare o eliminare dati di A
    assert b.get("/clienti/1/modifica").status_code == 404
    assert b.get("/scadenze/1/modifica").status_code == 404
    assert post(b, "/scadenze/1/stato").status_code == 404
    assert post(b, "/scadenze/1/elimina").status_code == 404
    post(b, "/scadenze/azione-multipla", sel="1", azione="elimina")
    assert len(db(app, "SELECT * FROM scadenze WHERE studio_id=1")) == 1
    # B non può usare un cliente o un tipo di A nelle sue scadenze
    assert post(b, "/scadenze/nuova", cliente_id="1", tipo_id="9",
                data="2026-11-16").status_code == 404
    post(b, "/scadenze/in-blocco", tipo_id="9", data="2026-11-16", clienti="1")
    assert len(db(app, "SELECT * FROM scadenze WHERE studio_id=2")) == 0


def test_collaboratore_non_admin(app, client):
    registra(client)
    post(client, "/collaboratori", nome="Luca", email="l@a.it", password="passwordlunga2")
    post(client, "/esci")
    t = token(client)
    client.post("/accedi", data={"_csrf": t, "email": "l@a.it", "password": "passwordlunga2"})
    assert client.get("/collaboratori").status_code == 403
    assert client.get("/scadenze").status_code == 200
