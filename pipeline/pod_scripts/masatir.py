# -*- coding: utf-8 -*-
"""Découpage du « دليل المساطر » en fiches de procédure.

Le guide n'est pas un texte de loi : chaque procédure est une SÉQUENCE, avec
son objet, ses prérequis, ses étapes numérotées, l'acteur de chaque étape, les
points de contrôle, les documents et les responsabilités. La découper au
kilomètre comme un code ferait perdre le fil — l'étape 3 remonterait sans
l'étape 2, le document sans l'autorité qui le détient.

On extrait donc une fiche par procédure, en champs.

Le filigrane « © Kurt Salmon - EMC » traverse les pages verticalement et
s'intercale au milieu des phrases : il est retiré avant tout découpage.
"""
import json
import re
import sys

PAGES = json.load(open(sys.argv[1], encoding="utf-8"))

# Le filigrane arrive en fragments isolés sur leur propre ligne.
FILIGRANE = re.compile(
    r"^\s*(?:©|Ku|rt|Sal|mo|n|EM|C|-)\s*$|©\s*Ku|rt\s*Sal|mo\s*n|EM\s*C",
    re.MULTILINE)
PIED = re.compile(r"^\s*\d{1,3}\s*ترجمة دليل المساطر\s*$", re.MULTILINE)


def nettoyer(t: str) -> str:
    t = FILIGRANE.sub("", t)
    t = PIED.sub("", t)
    return re.sub(r"[ \t]+", " ", t)


pages = [nettoyer(p) for p in PAGES]
full = "\n".join(f"\x0c{i + 1}\x0c{p}" for i, p in enumerate(pages))

# Début d'une procédure : « المسطرة. 12 <titre> » hors sommaire (le sommaire
# est suivi de points de conduite).
DEBUT = re.compile(r"المسطرة\.\s*(\d{1,3})\s+([^\n]{4,90})")
# Le guide emploie DEUX gabarits : les procédures de première instance
# (« إجراء N ») et celles d'appel et de cassation (« النشاط N »), plus riches —
# elles portent le cadre légal, les pièces à fournir et surtout les DÉLAIS.
SECTIONS = [
    ("objet", r"موضوع\s*(?:ونطاق|ومجال)\s*التطبيق"),
    ("cadre_legal", r"(?:الإطار\s*(?:التنظيمي|القانوني)|المرجع\s*القانوني)[^\n:]{0,40}"),
    ("delais", r"الآجال"),
    ("documents", r"(?:الوثائق\s*المكونة|(?:لائحة|قائمة)\s*الوثائق\s*المستعملة)[^\n:]{0,30}"),
    ("prerequis", r"(?:مقدمات\s*تطبيق\s*المسطرة|الإجراءات\s*القبلية)"),
    ("controles", r"(?:مفاتيح|مداخل)\s*المراقبة"),
    ("responsabilites", r"المسؤوليات"),
]
# Trois numérotations coexistent : « إجراء 3 », « النشاط 3 » et, quand la
# procédure se scinde en cas, « النشاط 3.1 » (étape 3 du cas 1).
ETAPE = re.compile(
    r"(?:[إا]جراء|النشاط)\s*(\d{1,2}(?:\.\d{1,2})?)\s*[:\-–]\s*([^\n]{0,80})")
# « الحالة 2: إرسال من طرف الوزارة » — un même intitulé d'étape se répète
# d'un cas à l'autre ; sans ce rattachement les séquences se mêlent.
CAS = re.compile(r"الحالة\s*(\d{1,2})\s*[:：]\s*([^\n]{0,90})")


def page_de(pos: int) -> int:
    m = None
    for m2 in re.finditer(r"\x0c(\d+)\x0c", full[:pos]):
        m = m2
    return int(m.group(1)) if m else 1


debuts = [m for m in DEBUT.finditer(full)
          if "...." not in full[m.start():m.start() + 160]]
print(f"{len(debuts)} procédures détectées hors sommaire", flush=True)

fiches = []
for i, m in enumerate(debuts):
    fin = debuts[i + 1].start() if i + 1 < len(debuts) else len(full)
    corps = re.sub(r"\x0c\d+\x0c", "\n", full[m.start():fin])
    fiche = {
        "numero": int(m.group(1)),
        "titre": re.sub(r"\s+", " ", m.group(2)).strip(),
        "page": page_de(m.start()),
        "etapes": [],
    }
    for nom, pat in SECTIONS:
        s = re.search(pat, corps)
        if not s:
            continue
        suite = corps[s.end():]
        # la section s'arrête au premier titre suivant, quel qu'il soit
        bornes = [len(suite)]
        for _, autre in SECTIONS:
            m2 = re.search(autre, suite)
            if m2:
                bornes.append(m2.start())
        m3 = ETAPE.search(suite)
        if m3:
            bornes.append(m3.start())
        stop = min(bornes)
        fiche[nom] = re.sub(r"\s+", " ", suite[:stop]).strip()[:900]
    cas = [(c.start(), re.sub(r"\s+", " ", c.group(2)).strip())
           for c in CAS.finditer(corps)]
    for e in ETAPE.finditer(corps):
        deb = e.end()
        nxt = ETAPE.search(corps, deb)
        bloc = corps[deb:nxt.start() if nxt else deb + 700]
        lignes = [re.sub(r"\s+", " ", l).strip(" -•\t")
                  for l in bloc.split("\n") if l.strip()]
        acteur = lignes[0] if lignes and not lignes[0].startswith("-") else None
        # le cas courant est le dernier en-tête « الحالة » avant l'étape
        courant = None
        for pos, libelle in cas:
            if pos < e.start():
                courant = libelle
        fiche["etapes"].append({
            "numero": e.group(1),
            "intitule": re.sub(r"\s+", " ", e.group(2)).strip(),
            "acteur": acteur,
            "cas": courant,
            "actions": [l for l in lignes[1:] if len(l) > 3][:8],
        })
    fiches.append(fiche)

avec = sum(1 for f in fiches if f["etapes"])
print(f"fiches avec étapes : {avec}/{len(fiches)}")
print(f"étapes au total    : {sum(len(f['etapes']) for f in fiches)}")
manquants = {k: sum(1 for f in fiches if not f.get(k))
             for k, _ in SECTIONS}
print("champs absents :", manquants)

json.dump(fiches, open(sys.argv[2], "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("fiches enregistrées :", sys.argv[2])
