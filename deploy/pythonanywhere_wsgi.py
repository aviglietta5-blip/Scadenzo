# File WSGI per PythonAnywhere: copiarlo nel file WSGI della scheda "Web".
# Funziona con qualsiasi nome utente, non va modificato.
import os
import secrets
import sys

progetto = os.path.expanduser("~/scadenzo")
dati = os.path.expanduser("~/scadenzo_dati")      # fuori dal progetto: git pull non lo tocca
os.makedirs(dati, exist_ok=True)
sys.path.insert(0, progetto)

# Chiave segreta creata una volta sola e salvata in un file privato
file_chiave = os.path.join(dati, "chiave_segreta.txt")
if not os.path.exists(file_chiave):
    with open(file_chiave, "w") as f:
        f.write(secrets.token_hex(32))
with open(file_chiave) as f:
    os.environ["SECRET_KEY"] = f.read().strip()

os.environ["SCADENZO_ENV"] = "production"
os.environ["DATABASE_PATH"] = os.path.join(dati, "scadenzo.sqlite")
os.environ["CREA_DEMO"] = "1"   # studio dimostrativo con dati inventati

from app import create_app  # noqa: E402

application = create_app()
