# ============================================================
# KONFIGURASI AKUN - EDIT FILE INI
# ============================================================

# Chain ID (8453 = Base network)
CHAIN_ID = 8453

# ============================================================
# KONFIGURASI PESAN
# ============================================================

# Jeda antar pesan (detik)
DELAY_BETWEEN_MESSAGES = 15

# True  = semua pesan dalam 1 conversation
# False = tiap pesan buat conversation baru
USE_SINGLE_CONVERSATION = True

# ============================================================
# KONFIGURASI PROXY
# ============================================================
# Jika menggunakan proxy rotation, cukup tulis 1 kali di sini.
# Format: "http://user:pass@ip:port" atau biarkan kosong "" jika tidak pakai.
PROXY = "http://fc23aa5e82afc382d4fd:b47018a66dce3ba3@gw.dataimpulse.com:823"

# ============================================================
# KONFIGURASI FITUR BOT
# ============================================================
# Jeda antar loop / siklus (dalam detik, misal 3600 = 1 jam)
LOOP_INTERVAL = 1800

# Fitur Auto Claim Token Reward (True/False)
ENABLE_CLAIM_REWARD = True

# Fitur Auto Staking 50% Token Harian (True/False)
ENABLE_STAKE = True

# Fitur Auto Harvest Staking Reward (True/False)
ENABLE_HARVEST = True

# Fitur Auto Chat (True/False)
ENABLE_AUTO_CHAT = True

# Jumlah sesi chat per akun per siklus (digunakan jika ENABLE_AUTO_CHAT = True)
JUMLAH_SESI_CHAT = 1

# Selalu gunakan proxy secara default (True/False)
# Jika False, bot hanya akan menggunakan proxy (Smart Proxy) saat kena Limit 429
USE_PROXY = True