"""Accesso al database (SQLite).

Ogni tabella con dati di uno studio ha la colonna studio_id: TUTTE le query
che leggono o modificano dati devono filtrare per lo studio dell'utente
collegato. È la regola che tiene separati i dati dei diversi clienti paganti.
"""
import sqlite3

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS studi (
    id          INTEGER PRIMARY KEY,
    nome        TEXT NOT NULL,
    creato_il   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS utenti (
    id            INTEGER PRIMARY KEY,
    studio_id     INTEGER NOT NULL REFERENCES studi(id) ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    ruolo         TEXT NOT NULL DEFAULT 'collaboratore'
                  CHECK (ruolo IN ('admin', 'collaboratore')),
    attivo        INTEGER NOT NULL DEFAULT 1,
    creato_il     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clienti (
    id              INTEGER PRIMARY KEY,
    studio_id       INTEGER NOT NULL REFERENCES studi(id) ON DELETE CASCADE,
    ragione_sociale TEXT NOT NULL,
    codice_fiscale  TEXT,
    partita_iva     TEXT,
    referente_id    INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
    note            TEXT,
    attivo          INTEGER NOT NULL DEFAULT 1,
    creato_il       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tipi_scadenza (
    id         INTEGER PRIMARY KEY,
    studio_id  INTEGER NOT NULL REFERENCES studi(id) ON DELETE CASCADE,
    nome       TEXT NOT NULL,
    colore     TEXT NOT NULL DEFAULT '#4f6bed',
    ricorrenza TEXT NOT NULL DEFAULT 'nessuna'
               CHECK (ricorrenza IN ('nessuna', 'mensile', 'trimestrale', 'annuale')),
    giorno     INTEGER CHECK (giorno IS NULL OR giorno BETWEEN 1 AND 31)
);

CREATE TABLE IF NOT EXISTS scadenze (
    id            INTEGER PRIMARY KEY,
    studio_id     INTEGER NOT NULL REFERENCES studi(id) ON DELETE CASCADE,
    cliente_id    INTEGER NOT NULL REFERENCES clienti(id) ON DELETE CASCADE,
    tipo_id       INTEGER NOT NULL REFERENCES tipi_scadenza(id) ON DELETE RESTRICT,
    data          TEXT NOT NULL,
    referente_id  INTEGER REFERENCES utenti(id) ON DELETE SET NULL,
    importo       REAL,
    stato         TEXT NOT NULL DEFAULT 'da_fare' CHECK (stato IN ('da_fare', 'fatto')),
    ricevuta      INTEGER NOT NULL DEFAULT 0,
    note          TEXT,
    completata_il TEXT,
    creato_il     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_scadenze_studio_data ON scadenze(studio_id, data);
CREATE INDEX IF NOT EXISTS ix_clienti_studio ON clienti(studio_id);
"""

# Tipi creati in automatico per ogni nuovo studio (modificabili dopo).
TIPI_PREDEFINITI = [
    ("F24", "#d9480f", "mensile", 16),
    ("Liquidazione IVA", "#1971c2", "mensile", 16),
    ("LIPE", "#0c8599", "trimestrale", None),
    ("770", "#7048e8", "annuale", None),
    ("Redditi", "#2f9e44", "annuale", None),
    ("IRAP", "#e67700", "annuale", None),
    ("730", "#c2255c", "annuale", None),
    ("CU", "#5c7cfa", "annuale", None),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def crea_tipi_predefiniti(db, studio_id):
    db.executemany(
        "INSERT INTO tipi_scadenza (studio_id, nome, colore, ricorrenza, giorno) "
        "VALUES (?, ?, ?, ?, ?)",
        [(studio_id, *t) for t in TIPI_PREDEFINITI],
    )
