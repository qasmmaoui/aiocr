# -*- coding: utf-8 -*-
"""Téléversement des PDF vers le volume réseau RunPod, SANS pod allumé.

RunPod expose les volumes réseau via une API compatible S3 : on écrit donc
directement dans le volume, et on n'allume un GPU qu'au moment de calculer.
Économie : ~4,50 $ de GPU inutile par téléversement complet.

Identifiants — JAMAIS dans ce fichier ni dans la conversation.
Créez %USERPROFILE%\\.runpod_s3 avec exactement deux lignes :

    access_key = <votre RunPod User ID>
    secret_key = <la clé S3 générée dans Settings > S3 API Keys>

Usage :
    python pod/upload_s3.py --etat        # ce qui manque, sans rien envoyer
    python pod/upload_s3.py               # envoie ce qui manque
    python pod/upload_s3.py --lot laws    # un seul lot

Reprise : le script liste d'abord ce qui est DÉJÀ sur le volume et ne renvoie
que la différence. Interrompre puis relancer ne recommence rien.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BUCKET = "gk2d8f88ko"
ENDPOINT = "https://s3api-eur-is-1.runpod.io"
REGION = "eur-is-1"
CREDS = os.path.join(os.path.expanduser("~"), ".runpod_s3")

# source locale -> préfixe sur le volume (= chemin sous /workspace)
LOTS = {
    "juris": [(r"Z:\jurisprudence", "rework/input/juris")],
    "juris6": [(r"Y:\adala-project\juris", "rework/input/juris_y")],
    "laws": [(r"Y:\adala-project\adala_pdfs", "rework/input/laws_all")],
}

_lock = threading.Lock()
_done = _bytes = 0


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# Erreurs transitoires de la passerelle RunPod : elle revalide chaque requête
# auprès de son API GraphQL interne, qui sature sous charge et renvoie alors
# AccessDenied ou 530 alors que les identifiants sont parfaitement valides.
_TRANSITOIRE = ("failed to fetch user keys", "context deadline exceeded",
                "(530)", "SlowDown", "ServiceUnavailable", "InternalError")


def creds() -> tuple[str, str]:
    if not os.path.exists(CREDS):
        sys.exit(f"Fichier d'identifiants absent : {CREDS}\n"
                 "Créez-le avec les deux lignes access_key = … / secret_key = …")
    kv = {}
    for line in open(CREDS, encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    try:
        return kv["access_key"], kv["secret_key"]
    except KeyError:
        sys.exit(f"{CREDS} doit contenir access_key et secret_key")


def client():
    import boto3
    from botocore.config import Config
    ak, sk = creds()
    return boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id=ak, aws_secret_access_key=sk,
        # beaucoup de petits fichiers : on veut des connexions, pas des retries lents
        # mode adaptatif : botocore ralentit tout seul quand le service peine
        config=Config(max_pool_connections=32, connect_timeout=20,
                      read_timeout=120,
                      retries={"max_attempts": 8, "mode": "adaptive"}))


def remote_keys(s3, prefix: str) -> set[str]:
    """Ce qui est déjà sur le volume — c'est ce qui rend la reprise gratuite.

    Le listage échoue aussi en 530 quand la passerelle est en refroidissement.
    Abandonner ici serait le pire moment : sans cette liste on ne sait plus ce
    qui reste à envoyer. On attend donc, longuement s'il le faut."""
    keys = set()
    tok = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix, "MaxKeys": 1000}
        if tok:
            kw["ContinuationToken"] = tok
        for n in range(8):
            try:
                r = s3.list_objects_v2(**kw)
                break
            except Exception as e:
                if not any(t in str(e) for t in _TRANSITOIRE) or n == 7:
                    raise
                attente = min(120, 5 * 2 ** n)
                log(f"   passerelle indisponible ({str(e)[-40:].strip()}) — "
                    f"nouvelle tentative dans {attente} s")
                time.sleep(attente)
        for o in r.get("Contents", []):
            keys.add(o["Key"])
        if not r.get("IsTruncated"):
            return keys
        tok = r.get("NextContinuationToken")


def cle_sure(prefix: str, rel: str) -> str:
    """S3 limite une clé à 255 OCTETS une fois encodée en URL. Un caractère
    arabe pèse 9 octets encodés (%D8%A7) : un nom de 60 lettres en fait 540.
    On raccourcit alors le nom de fichier en conservant un condensat du nom
    d'origine — la traçabilité passe par le catalogue, pas par la clé."""
    from urllib.parse import quote
    cle = f"{prefix}/{rel}"
    if len(quote(cle).encode()) <= 250:
        return cle
    tete, _, nom = cle.rpartition("/")
    h = hashlib.sha1(nom.encode("utf-8")).hexdigest()[:12]
    base = nom[:-4] if nom.lower().endswith(".pdf") else nom
    while base and len(quote(f"{tete}/{base}_{h}.pdf").encode()) > 250:
        base = base[:-1]
    return f"{tete}/{base}_{h}.pdf"


def local_files(root: str, prefix: str) -> list[tuple[str, str, int]]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if not f.lower().endswith(".pdf"):
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            out.append((p, cle_sure(prefix, rel), os.path.getsize(p)))
    return out


# botocore ne retente jamais un AccessDenied (403 = définitif pour lui), alors
# qu'ici il est transitoire. D'où cette boucle explicite par-dessus.
def send(s3, path: str, key: str, size: int, essais: int = 6) -> str | None:
    global _done, _bytes
    derniere = ""
    for n in range(essais):
        try:
            s3.upload_file(path, BUCKET, key)
            with _lock:
                _done += 1
                _bytes += size
            return None
        except Exception as e:
            derniere = f"{type(e).__name__} {e}"
            if not any(t in str(e) for t in _TRANSITOIRE):
                break                          # erreur réelle : inutile d'insister
            time.sleep(min(30, 2 ** n) + (hash(key) % 1000) / 1000.0)
    return f"{os.path.basename(path)} : {derniere}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--etat", action="store_true", help="n'envoie rien")
    ap.add_argument("--lot", choices=sorted(LOTS), help="un seul lot")
    # 16 fils saturaient la revalidation d'identifiants côté RunPod (16 557
    # refus sur 43 984). 6 tient sans déclencher le goulot.
    ap.add_argument("--fils", type=int, default=6)
    a = ap.parse_args()

    s3 = client()
    lots = {a.lot: LOTS[a.lot]} if a.lot else LOTS
    plan: list[tuple[str, str, int]] = []
    # Les fonds se recouvrent : Chambre_6 (Y:) est aussi الغرفة الجنائية (Z:).
    # On dédoublonne par nom de fichier — les lots sont traités dans l'ordre,
    # le premier gagne. Sans ça, 5 933 fichiers partiraient deux fois.
    vus: set[str] = set()

    for nom, sources in lots.items():
        for root, prefix in sources:
            if not os.path.isdir(root):
                log(f"{nom} : {root} absent — ignoré")
                continue
            loc = local_files(root, prefix)
            avant = len(loc)
            loc = [x for x in loc if os.path.basename(x[0]) not in vus]
            vus.update(os.path.basename(x[0]) for x in loc)
            dbl = avant - len(loc)
            log(f"{nom} : {avant:,} PDF locaux"
                + (f" · {dbl:,} doublons écartés" if dbl else "")
                + " — lecture du volume…")
            dist = remote_keys(s3, prefix)
            manque = [x for x in loc if x[1] not in dist]
            go = sum(s for _p, _k, s in manque) / 2**30
            log(f"   déjà sur le volume : {len(loc) - len(manque):,} · "
                f"à envoyer : {len(manque):,} ({go:.1f} Go)")
            plan += manque

    total_go = sum(s for _p, _k, s in plan) / 2**30
    log(f"TOTAL à envoyer : {len(plan):,} fichiers · {total_go:.1f} Go")
    if a.etat or not plan:
        return 0

    t0 = time.time()
    erreurs = []
    with ThreadPoolExecutor(max_workers=a.fils) as ex:
        futs = [ex.submit(send, s3, p, k, s) for p, k, s in plan]
        for i, f in enumerate(as_completed(futs), 1):
            err = f.result()
            if err:
                erreurs.append(err)
            if i % 250 == 0 or i == len(futs):
                dt = time.time() - t0
                mo = _bytes / 2**20
                reste = (len(plan) - i) * dt / max(1, i)
                log(f"   {i:,}/{len(plan):,} · {mo:.0f} Mo · "
                    f"{mo/max(1,dt):.1f} Mo/s · reste ~{reste/60:.0f} min")

    log(f"TERMINÉ : {_done:,} envoyés en {(time.time()-t0)/60:.0f} min")
    if erreurs:
        log(f"ÉCHECS : {len(erreurs)} — relancez, seuls ceux-ci repartiront")
        for e in erreurs[:10]:
            log(f"   {e}")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
