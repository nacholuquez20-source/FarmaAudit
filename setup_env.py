#!/usr/bin/env python3
"""Helper script to setup environment variables correctly."""

import json
import base64
import os
from pathlib import Path


def encode_service_account():
    """Encode service account JSON to base64."""
    sa_path = Path("service-account.json")

    if not sa_path.exists():
        print("[ERROR] service-account.json no encontrado")
        print("\nPasos:")
        print("1. Descargá service-account.json desde Google Cloud Console")
        print("2. Colocalo en esta carpeta (auditbot/)")
        print("3. Ejecutá este script nuevamente")
        return None

    try:
        with open(sa_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        json_str = json.dumps(json_data, ensure_ascii=False)
        json_bytes = json_str.encode("utf-8")
        b64_encoded = base64.b64encode(json_bytes).decode("ascii")

        return b64_encoded
    except Exception as e:
        print(f"[ERROR] Error codificando service account: {e}")
        return None


def update_env(b64_encoded):
    """Update .env with encoded service account."""
    env_path = Path(".env")

    if not env_path.exists():
        print("[ERROR] .env no encontrado")
        return False

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Find and replace GOOGLE_SERVICE_ACCOUNT_JSON
        lines = content.split("\n")
        updated_lines = []

        for line in lines:
            if line.startswith("GOOGLE_SERVICE_ACCOUNT_JSON="):
                updated_lines.append(f"GOOGLE_SERVICE_ACCOUNT_JSON={b64_encoded}")
            else:
                updated_lines.append(line)

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines))

        print(f"[OK] .env actualizado correctamente")
        print(f"   GOOGLE_SERVICE_ACCOUNT_JSON: {b64_encoded[:50]}...")
        return True
    except Exception as e:
        print(f"[ERROR] Error actualizando .env: {e}")
        return False


if __name__ == "__main__":
    print("[*] Setup AuditBot Environment\n")

    b64 = encode_service_account()
    if b64:
        update_env(b64)
        print("\n[OK] Environment configurado correctamente")
    else:
        print("\n[!] Por favor completá los pasos anteriores")
