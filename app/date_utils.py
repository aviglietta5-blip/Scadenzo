"""Calcolo delle date di scadenza.

Regola usata: se una scadenza cade di sabato, domenica o in un festivo
nazionale, slitta al primo giorno lavorativo successivo.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

MESI_PER_RICORRENZA = {"mensile": 1, "trimestrale": 3, "annuale": 12}

MESI_IT = [
    "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


def pasqua(anno: int) -> date:
    """Domenica di Pasqua (algoritmo di Meeus/Jones/Butcher)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def festivi(anno: int) -> set:
    fissi = [(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
             (11, 1), (12, 8), (12, 25), (12, 26)]
    giorni = {date(anno, m, g) for m, g in fissi}
    giorni.add(pasqua(anno) + timedelta(days=1))  # Pasquetta
    return giorni


def primo_giorno_lavorativo(d: date) -> date:
    while d.weekday() >= 5 or d in festivi(d.year):
        d += timedelta(days=1)
    return d


def aggiungi_mesi(d: date, mesi: int, giorno: int | None = None) -> date:
    mese_tot = d.month - 1 + mesi
    anno, mese = d.year + mese_tot // 12, mese_tot % 12 + 1
    g = giorno or d.day
    return date(anno, mese, min(g, calendar.monthrange(anno, mese)[1]))


def prossima_scadenza(d: date, ricorrenza: str, giorno: int | None) -> date | None:
    mesi = MESI_PER_RICORRENZA.get(ricorrenza)
    if not mesi:
        return None
    return primo_giorno_lavorativo(aggiungi_mesi(d, mesi, giorno))
