# 🤖 Myntis.ai Auto-Chat, Claim, Stake & Harvest Bot
link projek : https://myntis.ai/

![Myntis Bot Banner](https://img.shields.io/badge/Status-Active-brightgreen) ![Base](https://img.shields.io/badge/Network-Base_Mainnet-blue) ![Python](https://img.shields.io/badge/Language-Python-blue)

Auto-Bot Script untuk platform **Myntis.ai** (berjalan pada jaringan Base). Script ini dibuat untuk melakukan otomatisasi interaksi lengkap seperti Claim Token Reward, Chatting, Staking harian, hingga Memanen (Harvesting) reward staking menggunakan Multi-Account secara otomatis dan terjadwal.

> **Built by:** Noya-xen ([GitHub](https://github.com/Noya-xen))  
> **Follow me on X:** [@xinomixo](https://twitter.com/xinomixo)

---

## ✨ Fitur Utama
- **Multi-Account Support:** Mampu menjalankan putaran / rotasi fungsi untuk banyak akun sekaligus melalui `accounts.txt`.
- **Auto Claim Token Reward:** Memeriksa dan mengeksekusi pengklaiman Token Reward jika tersedia sebelum maupun sesudah chat.
- **Auto Chat & Interaction:** Melakukan interaksi obrolan dengan AI secara acak berdasarkan template `chat.txt`.
- **Auto Daily Stake & Harvest:** Secara mandiri men-staking 50% dari total saldo MYNT Anda ke Provider Pool (1x sehari) dan melakukan penarikan / Harvest untuk Token Reward yang *pending*.
- **Smart Proxy Fallback:** Jika Limit / Error `429 Too Many Requests` terdeteksi, Script ini akan secara cerdas mengaktifkan proxy secara mandiri tanpa campur tangan pengguna.
- **Daily Reporting:** Menghasilkan statistik berupa file laporan yang berisi informasi status akun, error yang dialami, serta status jumlah aset ETH & MYNT yang sedang berjalan.

---

## 🚀 Prasyarat Instalasi
1. Pastikan Anda telah menginstal [Python 3.8+](https://www.python.org/downloads/)
2. Memiliki saldo gas fee minimal di jaringan Base untuk menanggung *tx cost* Claiming, Staking & Harvesting.

## 🛠️ Cara Setup & Menjalankan

### 1. Kloning Repositori
```bash
git clone https://github.com/Noya-xen/Myntis-ai.git
cd Myntis-ai
```

### 2. Install Dependensi
Karena script ini menggunakan modul Python, jalankan instruksi PIP:
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi Wallet (Sangat Penting!)
Script membutuhkan kredensial Private Key dari Wallet Crypto Anda untuk menandatangani (Sign) transaksi claim/stake. Salin `accounts.txt` atau edit isinya:

Format `accounts.txt`:
```ini
access_token=...
refresh_token=...
wallet_address=0x...
private_key=0x...

---
access_token=...
refresh_token=...
wallet_address=0x...
private_key=0x...
```

### 4. Setup Konfigurasi Tambahan
Buka `config.py` dan sesuaikan nilainya sesuai preferensi Anda. (Anda bisa menghidup-matikan fitur yang tidak ingin dipakai seperti Stake atau Harvest).

### 5. Mulai Jalankan!
```bash
python bot.py
```

---

## 📡 Menjalankan 24/7 di VPS (Opsional)
Untuk memastikan bot berlari berhari-hari:
1. Pastikan menggunakan `screen` atau `tmux`.
2. `screen -S myntis`
3. `python bot.py`
4. Tekan `CTRL+A+D` untuk menutup window.

---

## ⚠️ Disclaimer
Script otomasi (bot) ini disediakan "Sebagaimana Adanya" (*As Is*) secara Open Source untuk keperluan edukasi. Seluruh kerugian, kegagalan transaksi, atau masalah banned akun menjadi tanggung jawab Anda sepenuhnya. Kami tidak pernah membagikan/mengirim kredensial Anda ke server kami.

**Happy Farming! 🤖**
