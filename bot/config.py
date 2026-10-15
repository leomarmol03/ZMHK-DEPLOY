"""Configuración sin secretos en código ni valores predeterminados sensibles."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    owner_id: int
    authorized_users: frozenset[int]
    download_dir: Path
    max_bytes: int
    timeout: int
    rclone_destination: str = ""

    @classmethod
    def from_env(cls):
        load_dotenv("config.env", override=False)
        token = os.getenv("BOT_TOKEN", "").strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
            raise ValueError("Configura BOT_TOKEN con el token de BotFather.")
        try:
            owner = int(os.environ.get("OWNER_ID", "0"))
            users = {int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",") if x.strip()}
            size = int(os.getenv("MAX_DOWNLOAD_MB", "45"))
            timeout = int(os.getenv("TASK_TIMEOUT", "1800"))
        except ValueError:
            raise ValueError("OWNER_ID, AUTHORIZED_USERS, MAX_DOWNLOAD_MB y TASK_TIMEOUT deben ser enteros.") from None
        if owner <= 0 or any(x <= 0 for x in users):
            raise ValueError("OWNER_ID y los usuarios autorizados deben ser IDs positivos.")
        if not 1 <= size <= 2048 or not 10 <= timeout <= 86400:
            raise ValueError("MAX_DOWNLOAD_MB: 1–2048; TASK_TIMEOUT: 10–86400 segundos.")
        destination = os.getenv("RCLONE_DESTINATION", "").strip()
        if destination and (destination.startswith(('-', '/')) or ':' not in destination):
            raise ValueError("RCLONE_DESTINATION debe tener formato remoto:carpeta.")
        return cls(token, owner, frozenset(users | {owner}),
                   Path(os.getenv("DOWNLOAD_DIR", "downloads")).expanduser().resolve(),
                   size * 1024 * 1024, timeout, destination)
