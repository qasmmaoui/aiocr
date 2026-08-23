# -*- coding: utf-8 -*-
"""Passe 3 — qualité du texte arabe, par document.

Quatre signatures de corruption, chacune mesurée séparément :

  espaces parasites  — « تف تح » au lieu de « تفتح » : l'extraction insère des
                       blancs à l'intérieur des mots. Signature : lettres
                       isolées entre deux espaces, hors mots-outils légitimes.
  ligatures inversées— « حمكمة » pour « محكمة » : couches texte à CMap cassée.
  bruit latin        — proportion de caractères non arabes dans un texte arabe.
  mojibake           — séquences d'un UTF-8 doublement encodé.
"""
import collections, json, re, unicodedata

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl"
ARABE = re.compile(r"[\u0621-\u064A]")
# mots arabes d'une seule lettre réellement existants
MONO = {"و", "ب", "ل", "ك", "ف", "أ", "ا"}
ISOLEE = re.compile(r"(?:^|\s)([\u0621-\u064A])(?=\s|$)")
MOJIBAKE = re.compile(r"[ÃÂØÙÛ][\u0080-\u00BF]")
# bigrammes typiques d'une inversion de ligature (lam-alef, etc.)
INVERSES = ("حمكمة", "اجلنحي", "مبقتضى", "اإلدارية", "اجلريدة", "املادة",
            "اململكة", "اإلسالمية", "اتلنفيذ", "اذلي")

docs = collections.defaultdict(lambda: {"n": 0, "car": 0, "isolees": 0,
                                        "mots": 0, "inv": 0, "latin": 0,
                                        "moji": 0})
for line in open(C, encoding="utf-8"):
    r = json.loads(line)
    t = r.get("text") or ""
    f = (r.get("file") or "")[:60]
    d = docs[f]
    d["n"] += 1
    d["car"] += len(t)
    mots = t.split()
    d["mots"] += len(mots)
    d["isolees"] += sum(1 for m in ISOLEE.findall(t) if m not in MONO)
    d["inv"] += sum(t.count(x) for x in INVERSES)
    d["latin"] += sum(1 for c in t if "A" <= c <= "z" and c.isalpha())
    d["moji"] += len(MOJIBAKE.findall(t))

print(f"documents analysés : {len(docs):,}\n")
res = []
for f, d in docs.items():
    if d["mots"] < 200:          # trop court pour conclure
        continue
    res.append({
        "f": f, "frag": d["n"], "mots": d["mots"],
        "tx_isolees": d["isolees"] / d["mots"],
        "inv": d["inv"],
        "tx_latin": d["latin"] / max(d["car"], 1),
        "moji": d["moji"],
    })

def top(cle, seuil, titre, fmt="{:.1%}"):
    mauvais = [x for x in res if x[cle] > seuil]
    print(f"=== {titre} : {len(mauvais):,} documents sur {len(res):,} ===")
    for x in sorted(mauvais, key=lambda y: -y[cle])[:8]:
        print(f"  {fmt.format(x[cle]):>8}  {x['frag']:>5} frag.  {x['f'][:52]}")
    print()

top("tx_isolees", 0.04, "espaces parasites (>4 % de lettres isolées)")
top("tx_latin", 0.15, "bruit latin (>15 % de caractères latins)")
inv = [x for x in res if x["inv"] > 5]
print(f"=== ligatures inversées : {len(inv):,} documents ===")
for x in sorted(inv, key=lambda y: -y["inv"])[:8]:
    print(f"  {x['inv']:>6} occurrences  {x['f'][:52]}")
print()
moji = [x for x in res if x["moji"] > 0]
print(f"=== mojibake : {len(moji):,} documents ===")
for x in sorted(moji, key=lambda y: -y["moji"])[:5]:
    print(f"  {x['moji']:>6} séquences  {x['f'][:52]}")
