# ============================================================
#  CONFIGURATION TELEGRAM SCRAPER
# ============================================================

API_ID   = 36977122
API_HASH = "605773c1b40159ed7ee5750fd2e4fb4c"
PHONE    = "+33758972521"

# Canal à scraper pour récupérer les membres
TARGET   = "https://t.me/+IsdmT-iCYvQzNjNk"

# Canal à surveiller pour le tracking de conversion (liens d'invitation Mass DM)
TRACKING_CHANNEL = "https://t.me/+DX-TmAG5x-E4NzNk"

# Fichiers de sortie
OUTPUT_CSV   = "output/membres.csv"
OUTPUT_EXCEL = "output/membres.xlsx"

# Delai entre requetes (secondes)
DELAY = 1.5

# ── Filtre genre ───────────────────────────────────────────
# True  = garde uniquement les hommes (détection par prénom)
# False = garde tout le monde
FILTER_MALE_ONLY = True
