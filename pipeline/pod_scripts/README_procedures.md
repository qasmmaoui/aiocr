# Séquence pod — module « procédures »

Quatre fichiers à téléverser dans /workspace :
  fiches_enrichies.json   112 fiches, 792 étapes
  ingest_procedures.py    crée la collection adala_procedures + lignes BM25
  procedures.py           intention, avertissement nommé, article 643
  inspect_answer.py       repère les ancrages avant de câbler answer.py

Puis, sur le pod :

  cd /workspace
  cp data/laws_corpus_v2.jsonl data/laws_corpus_v2.jsonl.bak-procedures
  python inspect_answer.py            # lire les ancrages
  cp procedures.py aiocr/rag/procedures.py
  python ingest_procedures.py         # ~112 vecteurs, quelques secondes

Câblage dans aiocr/rag/answer.py, à l'endroit révélé par l'inspection :
  - si procedures.veut_une_procedure(question) : interroger aussi
    adala_procedures et fusionner les hits ;
  - insérer procedures.bloc_procedures(hits) dans le contexte, avant les
    articles de loi ;
  - l'avertissement part avec le bloc : rien à ajouter au prompt système.

Vérification :
  « كيف أفتح ملف مدني ؟ »       -> fiche p.32 + avertissement nommé (art. 31, 36…)
  « ما هي عقوبة النصب ؟ »        -> aucune fiche, aucun avertissement
  « comment déposer une plainte » -> fiche + avertissement

Retour arrière : mv data/laws_corpus_v2.jsonl.bak-procedures data/laws_corpus_v2.jsonl
                 puis client.delete_collection("adala_procedures")
