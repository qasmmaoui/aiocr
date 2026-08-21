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

---

# Séquence pod — pièces jointes

Trois fichiers à téléverser :
  services/attachments.py       -> /workspace/aiocr/services/
  tests/test_attachments.py     -> /workspace/aiocr/tests/
  pipeline/pod_scripts/wire_pieces.py + wire_api_pieces.py  -> /workspace/

Puis :

  cd /workspace
  /workspace/venv/bin/python aiocr/tests/test_attachments.py   # 10 épreuves
  /workspace/venv/bin/python wire_pieces.py        # rag/answer.py
  /workspace/venv/bin/python wire_api_pieces.py    # api/main.py
  setsid bash /workspace/restart_api2.sh </dev/null >/workspace/restart2.log 2>&1 &

Vérification :
  curl -F "file=@convocation.pdf" localhost:8000/api/attachments   -> {id, nb_pages}
  puis POST /api/chat/stream avec {"question": "...", "attachment_ids": ["<id>"]}
  une image .jpg doit passer aussi (page unique, OCR vision)
  après 5 min d'inactivité : le fichier sous data/pieces disparaît,
  mais une question de suivi doit toujours trouver le texte

Retour arrière : les deux scripts déposent answer.py.bak-pieces et
main.py.bak-pieces à côté des originaux.

À faire dans la même session (indépendant) :
  - reprendre la sauvegarde : 17 023 fichiers de jurisprudence manquants,
    rework/input/extracted (4 208), juris_y — PAR LOTS avec comptage,
    et sans rediriger stderr de tar (c'est ce masquage qui a caché la coupure)
  - comparer rework/input/laws_all à Y:\adala-project\adala_pdfs PAR EMPREINTE,
    pas par nombre de fichiers
