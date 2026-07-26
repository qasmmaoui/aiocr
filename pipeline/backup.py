# -*- coding: utf-8 -*-
"""Sauvegarde RimLex — trois niveaux :

1. Snapshot versionné des données critiques -> Z:\\rimlex_backups\\<horodatage>
   (bases, registre, index, Excel, catalogue — tout ce qui est coûteux à
   reconstruire ; rotation sur 14 snapshots)
2. Copie hors-machine : push des mêmes fichiers (SANS les secrets) vers le
   dépôt GitHub privé rimlex-data-backup
3. Miroir des PDF Y:->Z: (protège des suppressions accidentelles ;
   un disque externe reste nécessaire contre la panne du disque physique)

Usage : python pipeline/backup.py [--no-mirror] [--no-git]
"""
import argparse
import datetime as dt
import glob
import os
import shutil
import sqlite3
import subprocess
import sys

DATA = r"Y:\adala-project\aiocr_data"
SNAP_ROOT = r"Z:\rimlex_backups"
GIT_REPO = r"Y:\adala-project\backup-repo"
GIT_REMOTE = "https://github.com/qasmmaoui/rimlex-data-backup.git"
KEEP = 14

# fichiers/dossiers critiques (petits, coûteux à reconstruire)
CRITICAL = [
    "app.db", "registry.json", "laws_corpus.jsonl", "laws_corpus_paged.jsonl",
    "laws_corpus_v2.jsonl", "version_graph.json", "dedup_report.json",
    "ingest_report.json", "juris_index.json", "relations.json",
    "ocr_quality.json", "ocr_review_worst.csv", "adala_alias_index.json",
    "juris_ocr_backlog.txt", "juris_texts.jsonl",
]
CRITICAL_DIRS = [r"Y:\adala-project\adala_pdfs\_catalog"]
CRITICAL_GLOBS = [r"Z:\jurisprudence\*\resultats_*.xlsx",
                  r"Y:\adala-project\adala_pdfs\_adala_index.json"]
# secrets : snapshot local OUI, GitHub NON
SECRETS = ["secret_key.txt", "admin_credentials.txt"]

MIRRORS = [  # (source, cible) — protège des suppressions, pas de la panne disque
    (r"Y:\adala-project\laws", r"Z:\rimlex_mirror\laws"),
    (r"Y:\adala-project\adala_pdfs", r"Z:\rimlex_mirror\adala_pdfs"),
]


def log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def sqlite_backup(src, dst):
    """Copie cohérente même si l'API écrit en même temps."""
    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    with d:
        s.backup(d)
    s.close()
    d.close()


def collect(dest, with_secrets: bool):
    os.makedirs(dest, exist_ok=True)
    n = 0
    for name in CRITICAL + (SECRETS if with_secrets else []):
        src = os.path.join(DATA, name)
        if not os.path.exists(src):
            continue
        if name.endswith(".db"):
            sqlite_backup(src, os.path.join(dest, name))
        else:
            shutil.copy2(src, os.path.join(dest, name))
        n += 1
    for d in CRITICAL_DIRS:
        if os.path.isdir(d):
            shutil.copytree(d, os.path.join(dest, os.path.basename(d)),
                            dirs_exist_ok=True)
            n += 1
    for pat in CRITICAL_GLOBS:
        for src in glob.glob(pat):
            sub = os.path.join(dest, "excels")
            os.makedirs(sub, exist_ok=True)
            tag = os.path.basename(os.path.dirname(src))
            shutil.copy2(src, os.path.join(sub, f"{tag}__{os.path.basename(src)}"))
            n += 1
    return n


def snapshot():
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(SNAP_ROOT, stamp)
    n = collect(dest, with_secrets=True)
    log(f"snapshot {stamp}: {n} éléments -> {dest}")
    snaps = sorted(glob.glob(os.path.join(SNAP_ROOT, "20*")))
    for old in snaps[:-KEEP]:
        shutil.rmtree(old, ignore_errors=True)
        log(f"rotation: {os.path.basename(old)} supprimé")


def git_push():
    if not os.path.isdir(os.path.join(GIT_REPO, ".git")):
        os.makedirs(GIT_REPO, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=GIT_REPO, check=True)
        subprocess.run(["git", "remote", "add", "origin", GIT_REMOTE], cwd=GIT_REPO)
        subprocess.run(["git", "config", "user.name", "RimLex Backup"], cwd=GIT_REPO)
        subprocess.run(["git", "config", "user.email", "qasmaoui@gmail.com"], cwd=GIT_REPO)
        open(os.path.join(GIT_REPO, ".gitignore"), "w").write(
            "secret_key.txt\nadmin_credentials.txt\n")
    collect(GIT_REPO, with_secrets=False)
    r = subprocess.run(["git", "status", "--porcelain"], cwd=GIT_REPO,
                       capture_output=True, text=True)
    if not r.stdout.strip():
        log("github: rien de nouveau")
        return
    subprocess.run(["git", "add", "-A"], cwd=GIT_REPO, check=True)
    subprocess.run(["git", "commit", "-m",
                    f"backup {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"],
                   cwd=GIT_REPO, check=True)
    p = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=GIT_REPO,
                       capture_output=True, text=True)
    log("github: push ok" if p.returncode == 0 else
        f"github: ECHEC push — {p.stderr.strip()[:200]}")


def mirror():
    for src, dst in MIRRORS:
        if not os.path.isdir(src):
            continue
        log(f"miroir {src} -> {dst}")
        # copie incrémentale par taille (rapide, suffisant pour des PDF figés)
        n = 0
        for dp, _dn, fn in os.walk(src):
            rel = os.path.relpath(dp, src)
            od = os.path.join(dst, rel) if rel != "." else dst
            os.makedirs(od, exist_ok=True)
            for f in fn:
                s, d = os.path.join(dp, f), os.path.join(od, f)
                try:
                    if (not os.path.exists(d)
                            or os.path.getsize(d) != os.path.getsize(s)):
                        shutil.copy2(s, d)
                        n += 1
                except OSError as e:
                    log(f"  ! {f[:50]}: {e}")
        log(f"  {n} fichier(s) copiés")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mirror", action="store_true")
    ap.add_argument("--no-git", action="store_true")
    a = ap.parse_args()
    snapshot()
    if not a.no_git:
        git_push()
    if not a.no_mirror:
        mirror()
    log("sauvegarde terminée")


if __name__ == "__main__":
    main()
