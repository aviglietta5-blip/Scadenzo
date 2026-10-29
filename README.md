# Scadenzo

Scadenziario fiscale online per studi commercialisti e professionisti.
Ogni studio ha il suo spazio separato, con utenti, clienti e scadenze.

Nome provvisorio.

## Cosa fa (versione 0.1)

- Registrazione dello studio, login, collaboratori con ruolo (amministratore / collaboratore)
- Clienti con referente interno
- Tipi di scadenza (F24, IVA, LIPE, 770, Redditi, IRAP, 730, CU già pronti) con ricorrenza
- Scadenze: filtri per mese, cliente, tipo, referente, stato; fatto / da fare; ricevuta scaricata
- Scadenze in blocco per più clienti, senza doppioni
- Ricorrenza automatica: segnando "Fatto" un F24 si crea quello del mese dopo,
  spostato al primo giorno lavorativo se cade di sabato, domenica o festivo
- Cruscotto: scadute, prossimi 7 giorni, vista "solo le mie"
- Esportazione CSV (si apre in Excel)

## Sicurezza

- Password salvate solo come hash; minimo 10 caratteri
- Protezione CSRF su tutti i form, cookie di sessione protetti, intestazioni di sicurezza
- **Isolamento tra studi**: ogni query filtra per studio. Ci sono test automatici apposta (`tests/`)

## Avvio in locale

```bash
pip install -r requirements.txt
python demo.py          # facoltativo: studio di esempio con dati inventati
flask --app app run     # → http://127.0.0.1:5000
```

Accesso demo: `demo@scadenzo.it` / `demo-scadenzo`

## Test

```bash
pip install pytest
python -m pytest
```

## In produzione

```bash
export SCADENZO_ENV=production
export SECRET_KEY="una-stringa-lunga-e-casuale"
export DATABASE_PATH=/var/data/scadenzo.sqlite
gunicorn "app:create_app()" --bind 0.0.0.0:8000 --workers 2
```

Serve HTTPS (dietro un reverse proxy o un hosting che lo fornisce) e un server in UE.

## Da fare prima di vendere

- [ ] Recupero password via email e invito collaboratori via email
- [ ] Promemoria email delle scadenze in arrivo
- [ ] Limite ai tentativi di login
- [ ] Backup automatici giornalieri del database
- [ ] Passaggio a PostgreSQL quando gli studi crescono
- [ ] Pagamenti in abbonamento (es. Stripe)
- [ ] Privacy policy, termini di servizio, accordo di trattamento dati (DPA, art. 28 GDPR)
- [ ] Import clienti da Excel/CSV
