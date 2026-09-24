"""Téléchargements HTTP avec mise en cache sur disque."""
import time
from pathlib import Path

import requests

from .config import SEC_USER_AGENT


def telecharger(url: str, chemin: Path, sec: bool = False, forcer: bool = False) -> Path:
    """Télécharge `url` vers `chemin` sauf si le fichier est déjà en cache."""
    if chemin.exists() and chemin.stat().st_size > 0 and not forcer:
        return chemin
    chemin.parent.mkdir(parents=True, exist_ok=True)
    entetes = {"User-Agent": SEC_USER_AGENT} if sec else {"User-Agent": "Mozilla/5.0 sp500-per"}
    if sec:
        entetes["Accept-Encoding"] = "gzip, deflate"
    print(f"  téléchargement {url}")
    tmp = chemin.with_suffix(chemin.suffix + ".part")
    for essai in range(4):
        try:
            with requests.get(url, headers=entetes, stream=True, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                recu = 0
                with open(tmp, "wb") as f:
                    for bloc in r.iter_content(chunk_size=1 << 20):
                        f.write(bloc)
                        recu += len(bloc)
                        if total > 50 << 20:
                            print(f"\r    {recu >> 20} / {total >> 20} Mo", end="", flush=True)
                if total > 50 << 20:
                    print()
            tmp.replace(chemin)
            return chemin
        except requests.RequestException as e:
            attente = 2 ** (essai + 1)
            print(f"    échec ({e}), nouvel essai dans {attente}s")
            time.sleep(attente)
    raise RuntimeError(f"Impossible de télécharger {url}")
