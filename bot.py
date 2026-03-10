"""
Auto-chat, Claim, Stake & Harvest script untuk myntis.ai
Konfigurasi jeda/mode ada di file: config.py
Konfigurasi Akun/Wallet/Private Key di file: accounts.txt

Fitur:
- Multi-akun
- Auto claim token reward
- Auto chat (random sesi dari chat.txt)
- Auto staking 50% token harian (1x per hari)
- Auto harvest staking reward (1x per hari)
- Loop setiap 1 jam
"""

import os
import re
import sys
import json
import time
import uuid
import random
import datetime
import requests

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

try:
    from config import DELAY_BETWEEN_MESSAGES, USE_SINGLE_CONVERSATION, CHAIN_ID
    try:
        from config import PROXY as CONFIG_PROXY
    except ImportError:
        CONFIG_PROXY = ""
    try:
        from config import (
            LOOP_INTERVAL, 
            ENABLE_CLAIM_REWARD, 
            ENABLE_STAKE, 
            ENABLE_HARVEST, 
            ENABLE_AUTO_CHAT, 
            JUMLAH_SESI_CHAT,
            USE_PROXY
        )
    except ImportError:
        # Fallback default values jika menggunakan versi config lama
        LOOP_INTERVAL = 3600
        ENABLE_CLAIM_REWARD = True
        ENABLE_STAKE = True
        ENABLE_HARVEST = True
        ENABLE_AUTO_CHAT = True
        JUMLAH_SESI_CHAT = 1
        USE_PROXY = False
except ImportError:
    print("[✗] ERROR: File config.py tidak ditemukan!")
    sys.exit(1)

# ============================================================
# KONSTANTA
# ============================================================

BASE_URL         = "https://myntis.ai"
GRAPHQL_URL      = f"{BASE_URL}/api/graphql"
SSE_URL          = f"{BASE_URL}/api/sse/stream"
RPC_URL          = "https://mainnet.base.org"
ACCOUNTS_FILE    = "accounts.txt"
STATE_FILE       = "bot_state.json"
REPORT_DIR       = "reports"
LOW_ETH_THRESHOLD = 0.0005  # Peringatan jika ETH dibawah ini

# Contract Addresses (Base Mainnet)
DISTRIBUTOR_ADDR = "0xfF52fdA700CaF238F9fE3bea3091E863aA00EADc"
STAKING_ADDR     = "0x3CBA95f31B61d9FaAC54D3A8A7fbb926737BB57d"
MYNT_TOKEN_ADDR  = "0x7629FD045E1462C9DCD580d0aF31db6D46c5AB47"

# ============================================================
# ABI
# ============================================================

# ABI untuk claim reward dari distributor
DISTRIBUTOR_ABI = [
    {
        "inputs": [
            {"internalType": "address",   "name": "provider",    "type": "address"},
            {"internalType": "uint256",   "name": "rootIndex",   "type": "uint256"},
            {"internalType": "uint256",   "name": "amount",      "type": "uint256"},
            {"internalType": "bytes32[]", "name": "merkleProof", "type": "bytes32[]"}
        ],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ABI untuk staking (DualPoolStaking)
STAKING_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "stakeToProviderPool",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "name": "unstakeFromProviderPool",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "harvestProviderRewards",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "pendingProviderRewards",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "providerStaked",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "minProviderStake",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
]

# ABI untuk ERC-20 token (approve + balanceOf)
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
]

# Kata kunci status/metadata dari SSE yang harus difilter
STATUS_PREFIXES = (
    "Connecting to", "Backend stream", "Preparing request",
    "Validating conversation", "Checking rate", "Checking subscription",
    "Generating response", "agent_warmup",
)

def is_status_text(text: str) -> bool:
    return any(text.startswith(p) or p in text for p in STATUS_PREFIXES)

# ============================================================
# STATE MANAGEMENT (untuk tracking staking/harvest harian)
# ============================================================
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_today_str() -> str:
    return datetime.date.today().isoformat()


# ============================================================
# DAILY STATS TRACKER
# ============================================================
class DailyStats:
    """Melacak statistik harian per akun untuk laporan."""
    def __init__(self):
        self.accounts = {}  # wallet -> stats dict

    def init_account(self, wallet: str):
        if wallet not in self.accounts:
            self.accounts[wallet] = {
                "chat_success": 0,
                "chat_fail": 0,
                "tokens_claimed_wei": 0,
                "tokens_staked_wei": 0,
                "tokens_harvested_wei": 0,
                "eth_balance": 0.0,
                "mynt_balance": 0.0,
                "low_eth": False,
                "errors": [],
            }

    def add_chat_success(self, wallet: str, count: int = 1):
        self.init_account(wallet)
        self.accounts[wallet]["chat_success"] += count

    def add_chat_fail(self, wallet: str, count: int = 1):
        self.init_account(wallet)
        self.accounts[wallet]["chat_fail"] += count

    def add_claimed(self, wallet: str, amount_wei: int):
        self.init_account(wallet)
        self.accounts[wallet]["tokens_claimed_wei"] += amount_wei

    def add_staked(self, wallet: str, amount_wei: int):
        self.init_account(wallet)
        self.accounts[wallet]["tokens_staked_wei"] += amount_wei

    def add_harvested(self, wallet: str, amount_wei: int):
        self.init_account(wallet)
        self.accounts[wallet]["tokens_harvested_wei"] += amount_wei

    def set_balances(self, wallet: str, eth_bal: float, mynt_bal: float):
        self.init_account(wallet)
        self.accounts[wallet]["eth_balance"] = eth_bal
        self.accounts[wallet]["mynt_balance"] = mynt_bal
        self.accounts[wallet]["low_eth"] = eth_bal < LOW_ETH_THRESHOLD

    def add_error(self, wallet: str, msg: str):
        self.init_account(wallet)
        self.accounts[wallet]["errors"].append(msg)


def generate_daily_report(stats: DailyStats, state: dict):
    """Generate laporan harian ke file, hanya 1x per hari."""
    today = get_today_str()
    last_report = state.get("last_report_date", "")
    if last_report == today:
        return  # Sudah generate hari ini

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_file = os.path.join(REPORT_DIR, f"daily_report_{today}.txt")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("=" * 70)
    lines.append(f"  LAPORAN HARIAN MYNTIS AI BOT")
    lines.append(f"  Tanggal: {today}")
    lines.append(f"  Dibuat:  {now_str}")
    lines.append("=" * 70)
    lines.append("")

    total_claimed_all = 0
    total_staked_all = 0
    total_harvested_all = 0
    total_chat_ok = 0
    total_chat_fail = 0
    low_eth_accounts = []

    for i, (wallet, s) in enumerate(stats.accounts.items(), 1):
        short_w = f"{wallet[:8]}...{wallet[-6:]}"
        claimed_mynt = s["tokens_claimed_wei"] / 1e18
        staked_mynt = s["tokens_staked_wei"] / 1e18
        harvested_mynt = s["tokens_harvested_wei"] / 1e18

        total_claimed_all += s["tokens_claimed_wei"]
        total_staked_all += s["tokens_staked_wei"]
        total_harvested_all += s["tokens_harvested_wei"]
        total_chat_ok += s["chat_success"]
        total_chat_fail += s["chat_fail"]

        lines.append(f"─── Akun #{i}: {short_w} ───")
        lines.append(f"  ETH Balance     : {s['eth_balance']:.6f} ETH")
        lines.append(f"  MYNT Balance    : {s['mynt_balance']:.4f} MYNT")
        lines.append(f"  Chat Berhasil   : {s['chat_success']}")
        lines.append(f"  Chat Gagal      : {s['chat_fail']}")
        lines.append(f"  Token Diklaim   : {claimed_mynt:.4f} MYNT")
        lines.append(f"  Token Di-stake  : {staked_mynt:.4f} MYNT")
        lines.append(f"  Reward Harvest  : {harvested_mynt:.4f} MYNT")

        if s["low_eth"]:
            lines.append(f"  ⚠️  PERINGATAN: ETH RENDAH! Sisa {s['eth_balance']:.6f} ETH")
            low_eth_accounts.append(short_w)

        if s["errors"]:
            lines.append(f"  Errors ({len(s['errors'])}) :")
            for err in s["errors"][:5]:  # Max 5 error per akun
                lines.append(f"    - {err}")

        lines.append("")

    # Ringkasan total
    lines.append("=" * 70)
    lines.append("  RINGKASAN TOTAL")
    lines.append("=" * 70)
    lines.append(f"  Total Akun           : {len(stats.accounts)}")
    lines.append(f"  Total Chat Berhasil  : {total_chat_ok}")
    lines.append(f"  Total Chat Gagal     : {total_chat_fail}")
    lines.append(f"  Total Token Diklaim  : {total_claimed_all / 1e18:.4f} MYNT")
    lines.append(f"  Total Token Di-stake : {total_staked_all / 1e18:.4f} MYNT")
    lines.append(f"  Total Reward Harvest : {total_harvested_all / 1e18:.4f} MYNT")

    if low_eth_accounts:
        lines.append("")
        lines.append("  ⚠️  AKUN DENGAN ETH RENDAH (perlu top-up gas):")
        for w in low_eth_accounts:
            lines.append(f"    - {w}")

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"  Laporan ini otomatis dibuat oleh Myntis AI Bot")
    lines.append("=" * 70)

    report_content = "\n".join(lines)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    state["last_report_date"] = today
    save_state(state)

    print(f"\n[📊] Laporan harian disimpan ke: {report_file}")
    print(report_content)


# ============================================================
# KELAS BOT UTAMA
# ============================================================
class MyntisBot:
    def __init__(self, access_token, refresh_token, wallet, pk, proxy=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.wallet = wallet
        self.pk = pk
        self.proxy = proxy
        # Smart proxy: Secara default tidak aktif, hanya aktif jika ada error/429
        # Atau aktif jika USE_PROXY = True
        self.proxy_active = USE_PROXY

        self.headers = {
            "Accept":           "*/*",
            "Accept-Encoding":  "gzip, deflate, br, zstd",
            "Accept-Language":  "en-US,en;q=0.5",
            "Content-Type":     "application/json",
            "Origin":           BASE_URL,
            "Referer":          f"{BASE_URL}/chat",
            "Sec-Fetch-Dest":   "empty",
            "Sec-Fetch-Mode":   "cors",
            "Sec-Fetch-Site":   "same-origin",
            "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Priority":         "u=1, i",
        }
        self.cookies = {
            "access_token":  self.access_token,
            "refresh_token": self.refresh_token,
        }

    @property
    def active_proxies(self):
        return {"http": self.proxy, "https": self.proxy} if self.proxy and self.proxy_active else None

    def enable_proxy_if_needed(self):
        if self.proxy and not self.proxy_active:
            print("\n[!] 429 Too Many Requests terdeteksi! Mengaktifkan proxy pintar untuk akun ini...")
            self.proxy_active = True
            return True
        return False

    def _get_w3(self):
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

    def get_eth_balance(self) -> float:
        """Mengembalikan saldo ETH (dalam ETH, bukan wei)."""
        try:
            w3 = self._get_w3()
            bal = w3.eth.get_balance(Web3.to_checksum_address(self.wallet))
            return bal / 1e18
        except Exception:
            return 0.0

    # ==========================
    # BAGIAN: CLAIM TOKEN REWARD
    # ==========================
    def get_claimable_rewards(self) -> list:
        q = """
        query ClaimableRewards {
          claimableRewards {
            id batchId provider merkleRoot rootIndex rewardAmount
            expiry walletAddress messageIds merkleProof
            claimed claimedAt txHash distributorAddress isBugged
          }
        }
        """
        try:
            # Tidak menggunakan proxy/smart-proxy untuk operasi claim
            r = requests.post(GRAPHQL_URL, headers=self.headers, cookies=self.cookies, json={"query": q}, timeout=15)
            r.raise_for_status()
            data = r.json()
            rewards = data.get("data", {}).get("claimableRewards", [])
            return [r for r in rewards if not r.get("claimed") and not r.get("isBugged")]
        except Exception as e:
            print(f"[✗] get_claimable_rewards error: {e}")
            return []

    def submit_claim(self, batch_id: str, proof_data: dict) -> bool:
        q = """
        mutation ClaimRewards($batchId: ID!, $proof: ClaimProofInput!) {
          claimRewards(batchId: $batchId, proof: $proof) {
            success message txHash claimedAt
          }
        }
        """
        try:
            # Tidak menggunakan proxy/smart-proxy untuk operasi claim
            r = requests.post(GRAPHQL_URL, headers=self.headers, cookies=self.cookies,
                              json={"query": q, "variables": {"batchId": batch_id, "proof": proof_data}}, timeout=15)
            data = r.json()
            result = data.get("data", {}).get("claimRewards", {})
            if result.get("success"):
                print(f"[✓] Klaim berhasil dicatat ke server! txHash: {result.get('txHash')}")
                return True
            print(f"[✗] Klaim server ditolak: {result.get('message')}")
        except Exception as e:
            print(f"[✗] submit_claim error: {e}")
        return False

    def do_blockchain_claim(self, reward: dict) -> str:
        w3 = self._get_w3()
        if not w3.is_connected():
            print("[✗] Tidak bisa konek ke Base RPC")
            return None

        dist_addr = Web3.to_checksum_address(reward.get("distributorAddress") or DISTRIBUTOR_ADDR)
        contract = w3.eth.contract(address=dist_addr, abi=DISTRIBUTOR_ABI)

        provider = Web3.to_checksum_address(reward["provider"])
        root_index = int(reward["rootIndex"])
        reward_amount = int(reward["rewardAmount"])
        merkle_proof = [bytes.fromhex(p[2:]) if p.startswith("0x") else bytes.fromhex(p) for p in reward.get("merkleProof", [])]
        account = Web3.to_checksum_address(self.wallet)

        try:
            nonce = w3.eth.get_transaction_count(account, "pending")
            gas_price = w3.eth.gas_price

            tx = contract.functions.claim(
                provider, root_index, reward_amount, merkle_proof
            ).build_transaction({
                "chainId": CHAIN_ID, "from": account,
                "nonce": nonce, "gasPrice": gas_price, "gas": 300_000,
            })
            signed = w3.eth.account.sign_transaction(tx, self.pk)
            raw_tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = "0x" + raw_tx_hash.hex()
            print(f"[~] TX Token Claim: {tx_hash_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(raw_tx_hash, timeout=180)
            if receipt["status"] == 1:
                print(f"[✓] TX confirmed! Block #{receipt['blockNumber']}")
                return tx_hash_hex
            print("[✗] TX reverted!")
        except Exception as e:
            print(f"[-] Claim error: {e}")
        return None

    def check_and_claim_tokens(self) -> int:
        """Mengklaim semua reward token. Mengembalikan jumlah total amount yang diklaim (wei)."""
        print("\n[*] Mengecek token reward yang bisa diklaim...")
        rewards = self.get_claimable_rewards()
        if not rewards:
            print("[~] Tidak ada token yang bisa diklaim saat ini.")
            return 0

        total_claimed = 0
        print(f"[!] Ditemukan {len(rewards)} batch claimable reward!")
        for reward in rewards:
            bid = reward["batchId"]
            amount = int(reward["rewardAmount"])
            print(f"    - Claim batchId={bid} | amount={amount}")
            tx_hash = self.do_blockchain_claim(reward)
            if tx_hash:
                total_claimed += amount
                self.submit_claim(bid, {
                    "rootIndex":    reward["rootIndex"],
                    "rewardAmount": reward["rewardAmount"],
                    "merkleProof":  reward.get("merkleProof", []),
                    "messageIds":   reward.get("messageIds", []),
                    "txHash":       tx_hash,
                })
            time.sleep(5)
        return total_claimed

    # ==========================
    # BAGIAN: STAKING
    # ==========================
    def get_mynt_balance(self) -> int:
        w3 = self._get_w3()
        token = w3.eth.contract(address=Web3.to_checksum_address(MYNT_TOKEN_ADDR), abi=ERC20_ABI)
        return token.functions.balanceOf(Web3.to_checksum_address(self.wallet)).call()

    def approve_staking(self, amount: int) -> bool:
        w3 = self._get_w3()
        account = Web3.to_checksum_address(self.wallet)
        token = w3.eth.contract(address=Web3.to_checksum_address(MYNT_TOKEN_ADDR), abi=ERC20_ABI)
        staking_addr = Web3.to_checksum_address(STAKING_ADDR)

        # Cek allowance dulu
        current_allowance = token.functions.allowance(account, staking_addr).call()
        if current_allowance >= amount:
            print(f"[~] Allowance sudah cukup ({current_allowance / 1e18:.4f} MYNT)")
            return True

        try:
            nonce = w3.eth.get_transaction_count(account, "pending")
            tx = token.functions.approve(staking_addr, amount).build_transaction({
                "chainId": CHAIN_ID, "from": account,
                "nonce": nonce, "gasPrice": w3.eth.gas_price, "gas": 100_000,
            })
            signed = w3.eth.account.sign_transaction(tx, self.pk)
            raw_tx = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = "0x" + raw_tx.hex()
            print(f"[~] TX Approve: {tx_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(raw_tx, timeout=120)
            if receipt["status"] == 1:
                print("[✓] Approve berhasil!")
                return True
            print("[✗] Approve reverted!")
        except Exception as e:
            print(f"[-] Approve error: {e}")
        return False

    def stake_to_provider_pool(self, amount: int) -> bool:
        w3 = self._get_w3()
        account = Web3.to_checksum_address(self.wallet)
        staking = w3.eth.contract(address=Web3.to_checksum_address(STAKING_ADDR), abi=STAKING_ABI)

        try:
            nonce = w3.eth.get_transaction_count(account, "pending")
            tx = staking.functions.stakeToProviderPool(amount).build_transaction({
                "chainId": CHAIN_ID, "from": account,
                "nonce": nonce, "gasPrice": w3.eth.gas_price, "gas": 300_000,
            })
            signed = w3.eth.account.sign_transaction(tx, self.pk)
            raw_tx = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = "0x" + raw_tx.hex()
            print(f"[~] TX Stake: {tx_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(raw_tx, timeout=180)
            if receipt["status"] == 1:
                print(f"[✓] Staking berhasil! {amount / 1e18:.4f} MYNT di-stake ke Provider Pool")
                return True
            print("[✗] Staking reverted!")
        except Exception as e:
            print(f"[-] Staking error: {e}")
        return False

    def do_daily_stake(self, state: dict):
        """Stake 50% dari saldo MYNT yang dimiliki (1x per hari)."""
        wallet_key = self.wallet.lower()
        today = get_today_str()

        last_stake_date = state.get(f"last_stake_{wallet_key}", "")
        if last_stake_date == today:
            print("[~] Staking sudah dilakukan hari ini, skip.")
            return

        balance = self.get_mynt_balance()
        balance_mynt = balance / 1e18
        print(f"[i] Saldo MYNT saat ini: {balance_mynt:.4f} MYNT")

        # Minimum stake biasanya 100 MYNT
        stake_amount = balance // 2  # 50%
        min_stake = 100 * (10 ** 18)  # 100 MYNT

        if stake_amount < min_stake:
            print(f"[~] 50% saldo ({stake_amount / 1e18:.4f} MYNT) di bawah minimum stake (100 MYNT). Skip staking.")
            return

        print(f"[*] Akan men-stake 50% saldo = {stake_amount / 1e18:.4f} MYNT")

        # Step 1: Approve
        if not self.approve_staking(stake_amount):
            return

        time.sleep(3)

        # Step 2: Stake
        if self.stake_to_provider_pool(stake_amount):
            state[f"last_stake_{wallet_key}"] = today
            save_state(state)
            print("[✓] Staking harian selesai!")

    # ==========================
    # BAGIAN: HARVEST REWARD
    # ==========================
    def check_pending_rewards(self) -> int:
        w3 = self._get_w3()
        staking = w3.eth.contract(address=Web3.to_checksum_address(STAKING_ADDR), abi=STAKING_ABI)
        account = Web3.to_checksum_address(self.wallet)
        try:
            pending = staking.functions.pendingProviderRewards(account).call()
            return pending
        except Exception as e:
            print(f"[-] Gagal cek pending rewards: {e}")
            return 0

    def harvest_rewards(self) -> bool:
        w3 = self._get_w3()
        account = Web3.to_checksum_address(self.wallet)
        staking = w3.eth.contract(address=Web3.to_checksum_address(STAKING_ADDR), abi=STAKING_ABI)

        try:
            nonce = w3.eth.get_transaction_count(account, "pending")
            tx = staking.functions.harvestProviderRewards().build_transaction({
                "chainId": CHAIN_ID, "from": account,
                "nonce": nonce, "gasPrice": w3.eth.gas_price, "gas": 300_000,
            })
            signed = w3.eth.account.sign_transaction(tx, self.pk)
            raw_tx = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = "0x" + raw_tx.hex()
            print(f"[~] TX Harvest: {tx_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(raw_tx, timeout=180)
            if receipt["status"] == 1:
                print("[✓] Harvest berhasil! Reward staking diterima.")
                return True
            print("[✗] Harvest reverted!")
        except Exception as e:
            print(f"[-] Harvest error: {e}")
        return False

    def do_daily_harvest(self, state: dict):
        """Harvest staking reward (1x per hari)."""
        wallet_key = self.wallet.lower()
        today = get_today_str()

        last_harvest_date = state.get(f"last_harvest_{wallet_key}", "")
        if last_harvest_date == today:
            print("[~] Harvest sudah dilakukan hari ini, skip.")
            return

        pending = self.check_pending_rewards()
        pending_mynt = pending / 1e18
        print(f"[i] Pending staking reward: {pending_mynt:.6f} MYNT")

        if pending == 0:
            print("[~] Tidak ada reward staking untuk di-harvest. Skip, coba lagi besok.")
            return

        print(f"[*] Melakukan harvest {pending_mynt:.6f} MYNT...")
        if self.harvest_rewards():
            state[f"last_harvest_{wallet_key}"] = today
            save_state(state)
            print("[✓] Harvest harian selesai!")

    # ==========================
    # BAGIAN: CHAT AUTOMATION
    # ==========================
    def create_conversation(self) -> str:
        mutations = [
            ('createConversation', 'mutation { createConversation { id } }'),
            ('createChat',        'mutation { createChat { id } }'),
            ('newConversation',   'mutation { newConversation { id } }'),
            ('startConversation', 'mutation { startConversation { id } }'),
        ]
        for name, query in mutations:
            try:
                resp = requests.post(GRAPHQL_URL, headers=self.headers, cookies=self.cookies, json={"query": query}, timeout=15, proxies=self.active_proxies)
                if resp.status_code == 429 and self.enable_proxy_if_needed():
                    resp = requests.post(GRAPHQL_URL, headers=self.headers, cookies=self.cookies, json={"query": query}, timeout=15, proxies=self.active_proxies)
                if resp.status_code != 200: continue
                data = resp.json()
                conv_id = (data.get("data", {}).get(name, {}) or {}).get("id")
                if conv_id:
                    print(f"[✓] Conversation dibuat via GraphQL ({name}): {conv_id}")
                    return conv_id
            except Exception:
                continue

        conv_id = uuid.uuid4().hex
        print(f"[~] GraphQL gagal, pakai UUID lokal: {conv_id}")
        return conv_id

    def send_message(self, conversation_id: str, message: str) -> str:
        client_request_id = str(uuid.uuid4())
        params  = {"conversationId": conversation_id}
        payload = {
            "clientRequestId": client_request_id,
            "message":         message,
            "chainId":         CHAIN_ID,
            "connectedWallet": self.wallet,
        }

        print(f"\n{'='*60}")
        print(f"[→] Mengirim: {message}")
        print(f"{'='*60}")

        full_response  = ""
        response_started = False

        try:
            resp = requests.post(
                SSE_URL,
                headers={**self.headers, "Accept": "text/event-stream"},
                cookies=self.cookies,
                params=params, json=payload,
                stream=True, timeout=90,
                proxies=self.active_proxies
            )
            if resp.status_code == 429 and self.enable_proxy_if_needed():
                resp.close()
                resp = requests.post(
                    SSE_URL,
                    headers={**self.headers, "Accept": "text/event-stream"},
                    cookies=self.cookies,
                    params=params, json=payload,
                    stream=True, timeout=90,
                    proxies=self.active_proxies
                )
            
            with resp:
                resp.raise_for_status()
                print("[←] Respons AI:")
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        text = None
                        for key in ("text", "content", "message", "output", "response"):
                            val = chunk.get(key)
                            if isinstance(val, str) and val:
                                text = val; break
                            elif isinstance(val, dict):
                                inner = val.get("text") or val.get("content", "")
                                if isinstance(inner, str) and inner:
                                    text = inner; break
                        if not text:
                            delta = chunk.get("delta", {})
                            if isinstance(delta, dict):
                                text = delta.get("text") or delta.get("content", "")
                        if text and isinstance(text, str) and not is_status_text(text):
                            response_started = True
                            print(text, end="", flush=True)
                            full_response += text
                    except json.JSONDecodeError:
                        if not is_status_text(raw):
                            response_started = True
                            print(raw, end="", flush=True)
                            full_response += raw

                if response_started:
                    print()
                else:
                    print("(tidak ada respons)")

        except requests.exceptions.HTTPError as e:
            print(f"\n[✗] HTTP Error: {e}")
            if e.response is not None:
                print(f"    Status: {e.response.status_code}")
                print(f"    Body:   {e.response.text[:300]}")
        except Exception as e:
            print(f"\n[✗] Error saat streaming: {e}")

        return full_response


# ============================================================
# FUNGSI PEMBANTU
# ============================================================
def load_accounts():
    accounts = []
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"[✗] File '{ACCOUNTS_FILE}' tidak ditemukan!")
        sys.exit(1)

    current_account = {}
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line == "---":
                if current_account and "access_token" in current_account and "wallet" in current_account:
                    current_account["id"] = len(accounts) + 1
                    accounts.append(current_account)
                    current_account = {}
                continue
            if line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "access_token":
                    current_account["access_token"] = val
                elif key == "refresh_token":
                    current_account["refresh_token"] = val
                elif key == "wallet_address":
                    current_account["wallet"] = val
                elif key == "private_key":
                    current_account["pk"] = val
                elif key == "proxy":
                    current_account["proxy"] = val

    if current_account and "access_token" in current_account and "wallet" in current_account:
        current_account["id"] = len(accounts) + 1
        accounts.append(current_account)

    return accounts

def load_sessions(filepath="chat.txt"):
    if not os.path.exists(filepath):
        print(f"[✗] File {filepath} tidak ditemukan di folder ini!")
        sys.exit(1)

    sessions = []
    current_session = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith("###"):
                if current_session:
                    sessions.append(current_session)
                    current_session = []
            elif re.match(r'^\d+\.\s+', line):
                msg = re.sub(r'^\d+\.\s+', '', line)
                current_session.append(msg)
    if current_session:
        sessions.append(current_session)
    return sessions


# ============================================================
# FUNGSI UTAMA (SATU SIKLUS)
# ============================================================
def run_one_cycle(accounts, sessions, jumlah_sesi, state, daily_stats: DailyStats):
    """Menjalankan SATU siklus lengkap untuk semua akun."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 60)
    print(f"  SIKLUS DIMULAI: {now}")
    print("=" * 60)

    for account_data in accounts:
        w_addr = account_data['wallet']
        print(f"\n" + "#" * 60)
        print(f"### Memproses AKUN: {w_addr[:8]}...{w_addr[-6:]} ###")
        print("#" * 60)

        daily_stats.init_account(w_addr)

        pk = account_data.get('pk', '')
        if not pk or pk == "MASUKKAN_PRIVATE_KEY_DISINI" or not pk.startswith("0x"):
            print("[!] Private Key tidak valid. Claim/Stake/Harvest dinonaktifkan.")
            pk = None

        # Gunakan proxy dari akun jika ada, jika tidak gunakan proxy dari config
        proxy_val = account_data.get('proxy')
        if not proxy_val and CONFIG_PROXY:
            proxy_val = CONFIG_PROXY

        bot = MyntisBot(
            access_token=account_data['access_token'],
            refresh_token=account_data['refresh_token'],
            wallet=w_addr,
            pk=pk,
            proxy=proxy_val
        )

        # ── STEP 1: Claim Token Reward (pra-chat) ──
        if pk and ENABLE_CLAIM_REWARD:
            claimed_pre = bot.check_and_claim_tokens()
            if claimed_pre > 0:
                daily_stats.add_claimed(w_addr, claimed_pre)
        else:
            print("[~] Skip klaim token (PK kosong).")

        # ── STEP 2: Harvest Staking Reward (1x/hari) ──
        if pk and ENABLE_HARVEST:
            print("\n[*] Mengecek harvest staking reward...")
            pending_before = bot.check_pending_rewards()
            bot.do_daily_harvest(state)
            if pending_before > 0:
                # Cek apakah harvest berhasil
                wallet_key = w_addr.lower()
                if state.get(f"last_harvest_{wallet_key}") == get_today_str():
                    daily_stats.add_harvested(w_addr, pending_before)

        # ── STEP 3: Chat Random Sesi ──
        if ENABLE_AUTO_CHAT:
            all_indices = list(range(len(sessions)))
            # Jika sample yang diminta melebihi total sesi, kurangi
            sample_size = min(jumlah_sesi, len(sessions))
            selected_indices = random.sample(all_indices, sample_size)
    
            for idx, sesi_idx in enumerate(selected_indices):
                pesan_sesi = sessions[sesi_idx]
                print(f"\n[>>>] AKUN {w_addr[:6]} - Sesi {sesi_idx + 1} ({idx + 1}/{sample_size}) - {len(pesan_sesi)} pesan [<<<]")
    
                conversation_id = None
                if USE_SINGLE_CONVERSATION:
                    conversation_id = bot.create_conversation()
    
                for i, msg in enumerate(pesan_sesi):
                    if not USE_SINGLE_CONVERSATION:
                        conversation_id = bot.create_conversation()
    
                    result = bot.send_message(conversation_id, msg)
                    if result:
                        daily_stats.add_chat_success(w_addr)
                    else:
                        daily_stats.add_chat_fail(w_addr)
    
                    if i < len(pesan_sesi) - 1:
                        print(f"\n[~] Menunggu jeda {DELAY_BETWEEN_MESSAGES} detik...\n")
                        time.sleep(DELAY_BETWEEN_MESSAGES)
    
                print(f"\n[✓] Sesi {sesi_idx + 1} selesai.")
    
                if idx < len(selected_indices) - 1:
                    print(f"\n[~] Jeda antarsesi {DELAY_BETWEEN_MESSAGES} detik...\n")
                    time.sleep(DELAY_BETWEEN_MESSAGES)
        else:
            print("\n[~] Skip auto chat (ENABLE_AUTO_CHAT=False).")

        # ── STEP 4: Claim Token Reward (pasca-chat) ──
        if pk and ENABLE_CLAIM_REWARD:
            print("\n[*] Pengecekan reward pasca-chat...")
            claimed_post = bot.check_and_claim_tokens()
            if claimed_post > 0:
                daily_stats.add_claimed(w_addr, claimed_post)

        # ── STEP 5: Daily Stake 50% (1x/hari) ──
        if pk and ENABLE_STAKE:
            print("\n[*] Mengecek staking harian...")
            balance_before = bot.get_mynt_balance()
            bot.do_daily_stake(state)
            balance_after = bot.get_mynt_balance()
            staked_amount = balance_before - balance_after
            if staked_amount > 0:
                daily_stats.add_staked(w_addr, staked_amount)

        # ── Catat saldo akhir untuk laporan ──
        if pk:
            eth_bal = bot.get_eth_balance()
            mynt_bal = bot.get_mynt_balance() / 1e18
            daily_stats.set_balances(w_addr, eth_bal, mynt_bal)
            if eth_bal < LOW_ETH_THRESHOLD:
                daily_stats.add_error(w_addr, f"ETH sangat rendah: {eth_bal:.6f} ETH. Perlu top-up untuk gas fee!")
        else:
            daily_stats.set_balances(w_addr, 0.0, 0.0)
            daily_stats.add_error(w_addr, "Private Key tidak valid, fitur on-chain dinonaktifkan.")

    print(f"\n[✓] Semua akun ({len(accounts)}) telah selesai memproses siklus ini!")


# ============================================================
# ENTRY POINT
# ============================================================
import os

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 60)
    print("  MYNTIS AI AUTO-CHAT, CLAIM, STAKE & HARVEST BOT")
    print("=" * 60)
    print("  > Built by Noya-xen (Github)")
    print("  > Follow me on X  : @xinomixo")
    print("=" * 60)

    accounts = load_accounts()
    if not accounts:
        print("[✗] Tidak ada akun valid di accounts.txt!")
        sys.exit(1)

    print(f"[i] Berhasil memuat {len(accounts)} akun dari {ACCOUNTS_FILE}.")

    sessions = load_sessions("chat.txt")
    if not sessions:
        print("[✗] Tidak ada sesi/pesan yang valid di dalam chat.txt.")
        sys.exit(1)

    print(f"[i] Ditemukan {len(sessions)} sesi di dalam chat.txt")

    print("-" * 60)
    jumlah_sesi = JUMLAH_SESI_CHAT
    if jumlah_sesi > len(sessions):
        print(f"[!] Target sesi chat disesuaikan dari {jumlah_sesi} ke {len(sessions)} (jumlah maksimum sesi yang ada)")
        jumlah_sesi = len(sessions)

    state = load_state()
    daily_stats = DailyStats()
    last_report_day = ""

    cycle = 1
    while True:
        print(f"\n{'*' * 60}")
        print(f"  LOOP ke-{cycle}")
        print(f"{'*' * 60}")

        # Reset stats jika hari berganti
        today = get_today_str()
        if today != last_report_day and last_report_day != "":
            daily_stats = DailyStats()  # Reset untuk hari baru
        last_report_day = today

        try:
            run_one_cycle(accounts, sessions, jumlah_sesi, state, daily_stats)
        except KeyboardInterrupt:
            print("\n[!] Dihentikan oleh user (Ctrl+C).")
            break
        except Exception as e:
            print(f"\n[✗] Error tidak terduga di siklus {cycle}: {e}")

        # Generate laporan harian (1x per hari)
        try:
            generate_daily_report(daily_stats, state)
        except Exception as e:
            print(f"[✗] Gagal generate laporan: {e}")

        # Tunggu 1 jam sebelum siklus berikutnya
        next_time = datetime.datetime.now() + datetime.timedelta(seconds=LOOP_INTERVAL)
        print(f"\n[⏰] Siklus {cycle} selesai. Menunggu 1 jam...")
        print(f"[⏰] Siklus berikutnya dimulai pada: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\n[!] Dihentikan oleh user (Ctrl+C) saat menunggu.")
            break

        cycle += 1

    # Generate laporan terakhir sebelum keluar
    try:
        generate_daily_report(daily_stats, state)
    except Exception:
        pass

    print("\n[✓] Bot selesai. Sampai jumpa!")


if __name__ == "__main__":
    main()