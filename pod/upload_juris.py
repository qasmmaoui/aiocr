# -*- coding: utf-8 -*-
"""Téléversement de la jurisprudence vers le pod, chambre par chambre.

rsync n'existe pas côté Windows : on streame donc un tar par chambre à
travers ssh (aucune duplication sur le disque local), en tenant un journal
des chambres déjà transférées pour pouvoir reprendre après une coupure.

    python pod/upload_juris.py            # tout ce qui manque
    python pod/upload_juris.py --etat     # état seulement
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

JURIS = r"Z:\jurisprudence"
DEST = "/workspace/rework/input/juris"
SSH = ["ssh", "-o", "StrictHostKeyChecking=no", "-i",
       os.path.expanduser("~/.ssh/id_auto"), "-p", "48054",
       "root@157.157.221.29"]
STATE = r"Y:\adala-project\aiocr_data\upload_juris_state.json"
# le pénal est déjà sur le pod (paquet penal_*.tar)
SKIP = {"الغرفة الجنائية"}


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def chambers() -> list[tuple[str, int, float]]:
    out = []
    for name in sorted(os.listdir(JURIS)):
        d = os.path.join(JURIS, name)
        if not os.path.isdir(d):
            continue
        files = [f for f in os.listdir(d) if f.lower().endswith(".pdf")]
        size = sum(os.path.getsize(os.path.join(d, f)) for f in files) / 2**30
        out.append((name, len(files), size))
    return out


def done() -> set:
    try:
        return set(json.load(open(STATE, encoding="utf-8")))
    except Exception:
        return set()


def mark(name: str) -> None:
    d = done()
    d.add(name)
    json.dump(sorted(d), open(STATE, "w", encoding="utf-8"), ensure_ascii=False)


def send(name: str, nfiles: int, size: float) -> bool:
    """tar local -> ssh -> untar distant, sans fichier intermédiaire."""
    log(f"{name} : {nfiles} fichiers · {size:.2f} Go — envoi…")
    t0 = time.time()
    remote = f"mkdir -p '{DEST}' && tar --no-same-owner -xf - -C '{DEST}'"
    p1 = subprocess.Popen(
        ["tar", "-cf", "-", "-C", JURIS, name], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(SSH + [remote], stdin=p1.stdout)
    p1.stdout.close()
    rc = p2.wait()
    p1.wait()
    dt = time.time() - t0
    if rc == 0:
        mark(name)
        log(f"  ✓ {name} en {dt/60:.0f} min ({size*1024/max(1,dt):.1f} Mo/s)")
        return True
    log(f"  ✗ {name} a échoué (code {rc}) — sera repris au prochain lancement")
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etat", action="store_true")
    a = ap.parse_args()

    todo = [(n, c, s) for n, c, s in chambers()
            if n not in SKIP and n not in done()]
    total = sum(s for _n, _c, s in todo)
    log(f"chambres à envoyer : {len(todo)} · {total:.1f} Go")
    for n, c, s in todo:
        log(f"   {n} — {c} fichiers · {s:.2f} Go")
    if a.etat:
        return
    for n, c, s in todo:
        if not send(n, c, s):
            sys.exit(1)
    log("TERMINÉ : toute la jurisprudence est sur le pod")


if __name__ == "__main__":
    main()
