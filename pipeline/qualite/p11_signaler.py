# -*- coding: utf-8 -*-
"""Signale les fragments douteux — sans jamais réécrire le texte de la loi.

Réparer un NUMÉRO d'article, c'est corriger une étiquette : le texte reste
celui du Bulletin officiel, et l'ancienne valeur est conservée. Réparer une
DATE dans le corps du texte serait tout autre chose : le corpus cesserait de
citer la source officielle, et un avocat reprendrait une formule que le
Bulletin n'a jamais imprimée. Le risque n'est pas symétrique.

On marque donc, et le moteur pourra rétrograder ou avertir :
  date_douteuse    — année d'édiction hors plage, calendrier jumeau disponible
  texte_degrade    — mots brisés par des espaces parasites
"""
import collections, json, re

C = r"Y:\adala-project\pod_backup_20260819\data\laws_corpus_v2.jsonl.repare"
SORTIE = C + ".signale"
MOIS_G = r"(?:يناير|فبراير|مارس|أبريل|ماي|مايو|يونيو|يونيه|يوليو|يوليوز|غشت|أغسطس|شتنبر|سبتمبر|أكتوبر|نونبر|نوفمبر|دجنبر|ديسمبر)"
MOIS_H = r"(?:محرم|صفر|ربيع|جمادى|رجب|شعبان|رمضان|شوال|ذي القعدة|ذو القعدة|ذي الحجة|ذو الحجة)"
COUPLE = re.compile(r"(\d{1,2})\s*(?:من\s+)?" + MOIS_H + r"[^\d\n]{0,12}(\d{3,4})\s*\(\s*(\d{1,2})\s*"
                    + MOIS_G + r"\s*(\d{1,4})\s*\)")
MONO = {"و", "ب", "ل", "ك", "ف", "أ", "ا"}
ISOLEE = re.compile(r"(?:^|\s)([\u0621-\u064A])(?=\s|$)")
EXCLUS = ("مجلة", "قائمة", "التقرير السنوي", "دليل", "نشرة")

stats = collections.Counter()
with open(C, encoding="utf-8") as src, open(SORTIE, "w", encoding="utf-8") as dst:
    for line in src:
        r = json.loads(line)
        t = r.get("text") or ""
        f = r.get("file") or ""
        marques = []
        if not any(x in f for x in EXCLUS):
            for m in COUPLE.finditer(t):
                ah, ag = int(m.group(2)), int(m.group(4))
                if 1300 <= ah <= 1460 and not (1900 <= ag <= 2030):
                    marques.append("date_douteuse")
                    stats["date_douteuse"] += 1
                    break
        mots = t.split()
        if len(mots) > 40:
            iso = sum(1 for x in ISOLEE.findall(t) if x not in MONO)
            if iso / len(mots) > 0.06:
                marques.append("texte_degrade")
                stats["texte_degrade"] += 1
        if marques:
            r["qualite"] = marques
            line = json.dumps(r, ensure_ascii=False) + "\n"
        dst.write(line)

print(f"fragments signalés « date douteuse » : {stats['date_douteuse']:,}")
print(f"fragments signalés « texte dégradé » : {stats['texte_degrade']:,}")
print(f"\nsortie : {SORTIE}")
