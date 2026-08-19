import sys
sys.path.insert(0, "/workspace/aiocr")
from rag.chunker import chunk_text

sample = (
    "ديباجة عامة حول تنظيم القانون والعدالة الجنائية في المملكة. "
    "المادة 41 يعتبر الصلح بديلا عن الدعوى العمومية إذا توفرت شروط إقامتها، ولا يمس بقرينة البراءة. "
    "يمكن للمضرر أو للمشتكى به أن يطلب من وكيل الملك تضمين الصلح الحاصل بينهما في محضر. "
    "المادة 41-1 يمكن سلوك مسطرة الصلح في الجنح المعاقب عليها بالحبس سنتين أو أقل. "
    "ويشمل ذلك الجرائم المنصوص عليها في المادة 316 من مدونة التجارة أو إذا نص القانون صراحة على ذلك. "
    "المادة 42 يقوم وكيل الملك بتنفيذ هذه المسطرة وفق الشروط المحددة قانونا."
)

print("=== chunks ===")
for i, c in enumerate(chunk_text(sample)):
    print(f"[{i}] article={c['article']!r}")
    print("    ", c["text"][:90])

# assertions
arts = [c["article"] for c in chunk_text(sample)]
print("\narticles:", arts)
assert "316" not in arts, "FAIL: split on cross-reference 316!"
assert "41" in arts and "41-1" in arts and "42" in arts, "FAIL: missing real articles"
print("PASS: no cross-ref split; real articles captured")
