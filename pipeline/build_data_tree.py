# -*- coding: utf-8 -*-
"""Réorganise le corpus en Y:\\DATA\\<matière>\\{lois,jurisprudence}.

Pourquoi : les fichiers sont aujourd'hui rangés par ORIGINE (quel scraper, quel
disque) et non par MATIÈRE. Un avocat pénaliste doit pouvoir prendre un dossier
et y trouver le code, les décrets et la jurisprudence de sa matière ensemble.
C'est aussi ce découpage qui permettra d'OCRiser et d'indexer matière par
matière, donc de livrer un produit utilisable avant d'avoir tout traité.

Économie d'espace : les lois vivent déjà sur Y:, on les LIE (lien dur, zéro
octet supplémentaire). La jurisprudence vient de Z:, une autre partition —
le lien dur y est impossible, il faut copier.

    python pipeline/build_data_tree.py --plan     # ce qui serait fait
    python pipeline/build_data_tree.py            # exécute
    python pipeline/build_data_tree.py --matiere penal
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter

CAT = r"Y:\adala-project\aiocr_data\catalogue_unifie.jsonl"
RACINE = r"Y:\DATA"

# Les 6 premières matières correspondent aux chambres de la Cour de cassation :
# jurisprudence ET lois y cohabitent. Les suivantes n'ont pas de chambre
# dédiée — elles ne contiendront que des textes.
THEME_MATIERE = {
    # --- pénal
    "المادة الجنائية": "penal",
    "المادة الأمنية": "penal",
    "الهيئة الوطنية للنزاهة والوقاية من الرشوة ومحاربتها": "penal",
    # --- civil
    "المادة المدنية": "civil",
    "المادة العقارية": "civil",
    "المادة الكرائية": "civil",
    # --- commercial
    "المادة التجارية": "commercial",
    "matiere commercial": "commercial",
    "مادة الصناعة والاقتصاد والاستثمار": "commercial",
    "مجلس المنافسة": "commercial",
    "مادة التأمين و التقاعد": "commercial",
    "مادة المعاملات الالكترونية": "commercial",
    # --- famille
    "المادة الأسرية": "famille",
    # --- social
    "المادة الاجتماعية": "social",
    "مادة المنظومة الصحية والحماية الاجتماعية": "social",
    "مؤسسات الأعمال الإجتماعية للقطاعات الحكومية": "social",
    # --- administratif
    "المادة الإدارية": "administratif",
    "مادة الوظيفة العمومية": "administratif",
    "مادة الجماعات الترابية": "administratif",
    "مادة اختصاصات وتنظيم القطاعات الحكومية والمؤسساتية": "administratif",
    "التنظيم الهيكلي للوزارة": "administratif",
    "السلطة التنفيذية": "administratif",
    "المجلس الأعلى للحسابات": "administratif",
    "مؤسسة الوسيط": "administratif",
    "المادة الإنتخابية": "administratif",
    # --- fiscal
    "المادة المالية": "fiscal",
    "المادة الجبائية": "fiscal",
    # --- constitutionnel & organisation judiciaire
    "الدستور": "constitutionnel",
    "المحكمة الدستورية": "constitutionnel",
    "السلطة التشريعية": "constitutionnel",
    "السلطة القضائية": "constitutionnel",
    "مادة التنظيم القضائي": "constitutionnel",
    "مادة الحقوق والحريات": "constitutionnel",
    "خطة العدالة": "constitutionnel",
    "المجلس الاقتصادي والاجتماعي والبيئي": "constitutionnel",
    "مؤسسات وهيئات حماية حقوق الإنسان والنهوض بها": "constitutionnel",
    "مؤسسات وهيئات النهوض بالتنمية البشرية والمستدامة والديمقراطية التشاركية":
        "constitutionnel",
    # --- conventions internationales
    "اتفاقيات دولية": "international",
    "اتفاقيات إقليمية": "international",
    "اتفاقيات حقوق الإنسان": "international",
    "اتفاقيات جنيف": "international",
    # --- professions judiciaires
    "مهنة المحاماة": "professions",
    "مهنة التوثيق": "professions",
    "مهنة المفوضون القضائيون": "professions",
    "مهنة التراجمة": "professions",
    "مهنة النساخة": "professions",
    "الخبراء القضائيين": "professions",
    "مادة المهن": "professions",
    # --- doctrine (une revue, pas un texte de loi)
    "مجلة القضاء والقانون": "doctrine",
    # --- réglementations sectorielles
    "مادة التربية والتعليم": "sectoriel",
    "مادة الفلاحة": "sectoriel",
    "مادة الثقافة والسياحة والتراث": "sectoriel",
    "المادة البيئية": "sectoriel",
    "مادة الصيد البحري": "sectoriel",
    "مادة السلامة الصحية والغدائية": "sectoriel",
    "النقل عبر الطرق": "sectoriel",
    "مادة الطاقة": "sectoriel",
    "المادة السمعية البصرية": "sectoriel",
    "مادة الشؤون الدينية والإسلامية": "sectoriel",
    "مادة النقل الجوي و البحري": "sectoriel",
    "مادة الصحافة": "sectoriel",
    "مادة الصناعة التقليدية": "sectoriel",
    "حالة الطوارئ الصحية": "sectoriel",
}


def log(m: str) -> None:
    print(m, flush=True)


def matiere_de(d: dict) -> str:
    if d["type"] == "jurisprudence":
        return d.get("matiere") or "inconnu"
    return THEME_MATIERE.get(d.get("theme", ""), "sectoriel")


def poser(src: str, dst: str, meme_volume: bool) -> str:
    """Lien dur si possible (gratuit), copie sinon. Renvoie 'lien'|'copie'|'saut'."""
    if os.path.exists(dst):
        return "saut"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if meme_volume:
        try:
            os.link(src, dst)
            return "lien"
        except OSError:
            pass                      # repli silencieux : mieux vaut copier que échouer
    shutil.copy2(src, dst)
    return "copie"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="n'écrit rien")
    ap.add_argument("--matiere", help="une seule matière")
    a = ap.parse_args()

    docs = [json.loads(l) for l in open(CAT, encoding="utf-8")]
    par_mat: dict[str, dict[str, list]] = {}
    absents = 0
    for d in docs:
        if not d.get("present_local") or not d.get("chemin_local"):
            absents += 1
            continue
        m = matiere_de(d)
        if a.matiere and m != a.matiere:
            continue
        genre = "lois" if d["type"] == "loi" else "jurisprudence"
        par_mat.setdefault(m, {}).setdefault(genre, []).append(d)

    log(f"{'MATIÈRE':<18}{'lois':>8}{'jurisprudence':>16}{'Go':>9}")
    log("-" * 51)
    total_go = 0.0
    for m in sorted(par_mat, key=lambda k: -sum(
            len(v) for v in par_mat[k].values())):
        nl = len(par_mat[m].get("lois", []))
        nj = len(par_mat[m].get("jurisprudence", []))
        go = sum(d.get("taille", 0) for g in par_mat[m].values()
                 for d in g) / 2**30
        total_go += go
        log(f"{m:<18}{nl:>8,}{nj:>16,}{go:>9.1f}")
    log("-" * 51)
    log(f"{'TOTAL':<18}{'':>8}{'':>16}{total_go:>9.1f}")
    if absents:
        log(f"({absents} documents du catalogue absents du disque — ignorés)")

    if a.plan:
        log("\n--plan : rien n'a été écrit.")
        return 0

    # espace : seules les copies (jurisprudence, autre partition) consomment
    besoin = sum(d.get("taille", 0) for m in par_mat
                 for d in par_mat[m].get("jurisprudence", [])) / 2**30
    libre = shutil.disk_usage(os.path.splitdrive(RACINE)[0] + "\\").free / 2**30
    log(f"\nespace requis (copies) : {besoin:.1f} Go · libre sur "
        f"{os.path.splitdrive(RACINE)[0]} : {libre:.1f} Go")
    if besoin > libre - 5:
        sys.exit("ESPACE INSUFFISANT — abandon avant d'avoir rien cassé.")

    vol_racine = os.path.splitdrive(RACINE)[0].upper()
    stats = Counter()
    for m, genres in par_mat.items():
        for genre, liste in genres.items():
            for d in liste:
                src = d["chemin_local"]
                meme = os.path.splitdrive(src)[0].upper() == vol_racine
                dst = os.path.join(RACINE, m, genre, d["fichier"])
                try:
                    stats[poser(src, dst, meme)] += 1
                except Exception as e:
                    stats["echec"] += 1
                    if stats["echec"] <= 5:
                        log(f"  échec {d['fichier'][:50]} : {type(e).__name__}")
            if stats["lien"] + stats["copie"] + stats["saut"] > 0:
                log(f"  {m}/{genre} : {len(liste):,} documents")
        # métadonnées de la matière, à côté des fichiers
        meta = os.path.join(RACINE, m, "_metadata")
        os.makedirs(meta, exist_ok=True)
        with open(os.path.join(meta, "catalogue.jsonl"), "w",
                  encoding="utf-8") as f:
            for genre, liste in genres.items():
                for d in liste:
                    e = dict(d)
                    e["chemin_data"] = os.path.join(RACINE, m, genre,
                                                    d["fichier"])
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")

    log(f"\nliens durs : {stats['lien']:,} · copies : {stats['copie']:,} · "
        f"déjà là : {stats['saut']:,} · échecs : {stats['echec']:,}")
    log(f"ARBORESCENCE PRÊTE : {RACINE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
