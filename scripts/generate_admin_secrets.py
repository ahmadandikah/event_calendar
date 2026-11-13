"""Bootstrap Admin yang aman: membuat ADMIN_PIN_HASH, APP_SECRET, dan ADMIN_ACCESS_KEY.

Jalankan di komputer Anda (BUKAN di server):
    python scripts/generate_admin_secrets.py

PIN tidak pernah disimpan — yang Anda tempel ke Secrets hanyalah hash-nya.
"""
import getpass
import hashlib
import base64
import secrets
import sys

ITERATIONS = 390_000


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def main() -> None:
    print("=== Generator Rahasia Admin — Kalender Kegiatan Panitia ===\n")
    print("Syarat PIN: minimal 8 karakter (angka/huruf). Hindari tanggal lahir atau 12345678.\n")
    pin = getpass.getpass("Masukkan PIN admin baru : ").strip()
    if len(pin) < 8:
        sys.exit("PIN terlalu pendek (minimal 8 karakter).")
    if len(set(pin)) < 3:
        sys.exit("PIN terlalu mudah ditebak.")
    if getpass.getpass("Ulangi PIN              : ").strip() != pin:
        sys.exit("PIN tidak sama.")
    print("\nTempel baris berikut ke Streamlit Secrets / .streamlit/secrets.toml:\n")
    print(f'ADMIN_PIN_HASH = "{hash_pin(pin)}"')
    print(f'APP_SECRET = "{secrets.token_hex(32)}"')
    print(f'ADMIN_ACCESS_KEY = "{secrets.token_urlsafe(24)}"   # opsional, kosongkan "" bila tidak dipakai')
    print("\nSimpan PIN dan ADMIN_ACCESS_KEY di tempat aman (password manager). Jangan kirim lewat grup chat.")


if __name__ == "__main__":
    main()
