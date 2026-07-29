# -*- coding: utf-8 -*-
"""Index de la jurisprudence (passe 1, déterministe).

Lit les Excel des chambres (Z:\\jurisprudence\\<nom arabe>), nettoie la colonne
«المفاتيح أو القاعدة» (fragments de recherche → phrase-thème), extrait l'année
(nom de fichier, fiable) et applique une taxonomie de thèmes par mots-clés
(multi-étiquettes). Sortie : juris_index.json + stats.

Les thèmes vivent dans l'INDEX, pas dans des dossiers : un arrêt peut porter
plusieurs thèmes ; les fichiers restent plats (identifiants canoniques).
La passe 2 (clustering d'embeddings, pod GPU) affinera.
"""
import glob
import json
import os
import re
from collections import Counter

import openpyxl

JURIS = r"Z:\jurisprudence"
OUT = r"Y:\adala-project\aiocr_data\juris_index.json"

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

BOILER = re.compile(r"كاتب(?:ة)? الضبط|وبمساعدة|أجل الستين|الستين يوما|"
                    r"بكتابة ضبط|القرار المطعون|المقرر المطعون|المطعون فيه")

THEMES = {
    "غرفة الأحوال الشخصية والميراث": {
        "الزواج": ["زواج", "ثبوت الزوجية", "الخطبة"],
        "الطلاق والتطليق": ["طلاق", "تطليق", "شقاق", "خلع"],
        "النفقة": ["نفقة", "واجبات"],
        "الحضانة": ["حضانة", "زيارة المحضون"],
        "الإرث والتركات": ["إرث", "ميراث", "تركة", "وصية", "تنزيل"],
        "النسب": ["نسب", "بنوة", "خبرة جينية"],
        "الأموال الزوجية": ["أموال مكتسبة", "كد وسعاية", "تدبير الأموال"],
    },
    "الغرفة التجارية": {
        "الكراء التجاري": ["كراء تجاري", "الأصل التجاري", "إفراغ"],
        "صعوبات المقاولة": ["صعوبات المقاولة", "تسوية قضائية", "تصفية قضائية", "سنديك"],
        "الأوراق التجارية": ["شيك", "كمبيالة", "سند لأمر"],
        "الشركات": ["شركة", "شركات", "مساهم", "حصص"],
        "البنوك والقروض": ["بنك", "قرض", "فوائد", "حساب بنكي"],
        "التحكيم": ["تحكيم", "مقرر تحكيمي"],
        "الملكية الصناعية": ["علامة تجارية", "براءة", "ملكية صناعية", "منافسة غير مشروعة"],
    },
    "الغرفة الاجتماعية": {
        "عقد الشغل والفصل": ["مدونة الشغل", "عقد الشغل", "فصل تعسفي", "طرد", "استقالة"],
        "التعويضات": ["تعويض عن الضرر", "تعويض عن الفصل", "أجر", "عطلة"],
        "حوادث الشغل": ["حادثة شغل", "مرض مهني", "إيراد"],
        "الضمان الاجتماعي": ["الضمان الاجتماعي", "التقاعد", "معاش"],
        "النقابات والإضراب": ["نقاب", "إضراب", "مندوب"],
    },
    "الغرفة الجنائية": {
        "المخدرات": ["مخدرات", "اتجار في المخدرات", "شيرا"],
        "جرائم الأموال": ["سرقة", "نصب", "احتيال", "خيانة الأمانة", "اختلاس"],
        "الرشوة والفساد": ["رشوة", "استغلال النفوذ", "تبديد أموال"],
        "العنف والاعتداء": ["قتل", "ضرب وجرح", "عنف", "إيذاء"],
        "الجرائم الجنسية": ["اغتصاب", "هتك عرض", "فساد", "تحرش"],
        "التزوير": ["تزوير", "انتحال", "شهادة زور"],
        "شيك بدون مؤونة": ["شيك بدون مؤونة", "شيك بدون رصيد", "مؤونة الشيك"],
        "المسطرة الجنائية": ["مسطرة جنائية", "اعتقال احتياطي", "سراح مؤقت", "تقادم الدعوى"],
    },
    "الغرفة الإدارية": {
        "نزع الملكية": ["نزع الملكية", "الاعتداء المادي"],
        "الضرائب": ["ضريبة", "جبائ", "رسم"],
        "الصفقات العمومية": ["صفقة عمومية", "صفقات"],
        "الوظيفة العمومية": ["موظف", "وظيفة عمومية", "تأديب"],
        "إلغاء القرارات": ["إلغاء قرار", "تجاوز السلطة", "الشطط"],
        "المسؤولية الإدارية": ["مسؤولية", "تعويض عن الأضرار"],
        "التعمير": ["تعمير", "رخصة بناء", "تجزئة"],
    },
}


def clean_qaida(cell: str) -> str:
    """Fragments de recherche superposés -> phrase-thème (queue exploitable)."""
    if not cell:
        return ""
    frags = [f.strip() for f in str(cell).split("...") if f.strip()]
    if not frags:
        return ""
    t = re.sub(r"^[\d\s/.-]+", "", frags[-1])
    t = re.sub(r"\s+", " ", t).strip()
    return "" if (len(t) < 10 or BOILER.search(t)) else t


def year_of(fname: str, excel_date: str) -> str:
    m = re.match(r"(\d{4})-", fname)
    if m and 1950 <= int(m.group(1)) <= 2030:
        return m.group(1)
    m = re.match(r"(\d{4})", str(excel_date or "").translate(AR_DIGITS))
    return m.group(1) if m and 1950 <= int(m.group(1)) <= 2030 else ""


def themes_of(chamber: str, full_cell: str) -> list[str]:
    found = []
    txt = str(full_cell or "")
    for theme, kws in THEMES.get(chamber, {}).items():
        if any(k in txt for k in kws):
            found.append(theme)
    return found


def main() -> None:
    index, stats = [], {}
    for xl in sorted(glob.glob(os.path.join(JURIS, "*", "*.xlsx"))):
        chamber = os.path.basename(os.path.dirname(xl))
        wb = openpyxl.load_workbook(xl, read_only=True)
        ws = wb.active
        n = themed = 0
        theme_counts = Counter()
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r or not (r[5] or r[4]):
                continue
            n += 1
            fname = str(r[5] or "")
            ths = themes_of(chamber, r[3])
            if ths:
                themed += 1
                theme_counts.update(ths)
            index.append({
                "chamber": chamber,
                "file": fname,
                "file_no": str(r[0] or ""), "dec_no": str(r[1] or ""),
                "date": str(r[2] or ""), "year": year_of(fname, r[2]),
                "qaida_clean": clean_qaida(r[3]),
                "themes": ths,
                "data_id": str(r[4] or ""),
                "status": str(r[7] or ""),
            })
        wb.close()
        stats[chamber] = {"decisions": n, "themed": themed,
                          "top": theme_counts.most_common(5)}
    json.dump(index, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(index)} décisions indexées -> {OUT}")
    for ch, s in stats.items():
        pct = round(100 * s["themed"] / s["decisions"]) if s["decisions"] else 0
        print(f"  {ch}: {s['decisions']} décisions, {pct}% avec thème — "
              + "، ".join(f"{t} ({c})" for t, c in s["top"]))


if __name__ == "__main__":
    main()
