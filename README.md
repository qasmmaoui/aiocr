# ⚖️ Adala — المساعد القانوني الذكي لوزارة العدل

> **DMSI · Ing. Mouad** — Assistant juridique marocain fondé sur l'IA : OCR arabe,
> recherche sémantique (RAG) ancrée sur les textes officiels, citations vérifiables
> page par page, et gestion versionnée du corpus législatif et jurisprudentiel.

**Principe directeur : la confiance se prouve.** Chaque réponse cite ses sources ;
chaque source s'ouvre sur la page originale du Bulletin/portail Adala avec le
passage surligné. Le LLM n'est jamais cru sur parole.

---

## 🧱 Vue d'ensemble

```
                     ┌────────────────────────────────────────────────┐
   Open WebUI /      │  FastAPI (api/)                                │
   tout client  ───▶ │   /v1/chat/completions   OpenAI-compatible     │
   OpenAI            │   /v1/chat               natif (sources JSON)  │
                     │   /api/viewer            preuve page/OCR       │
                     │   /api/admin             console du corpus     │
                     └──────┬──────────────────────┬──────────────────┘
                            │ retrieval            │ génération
                            ▼                      ▼
                     Qdrant (bge-m3)         Ollama (LLM)
                     collections laws_*      prompt ancré + règles
                            ▲                      métier (versions,
                            │ ingestion            jurisprudence, FR)
                     pipeline/ (voir plus bas)
```

### Les trois collections de données

| Collection | Contenu | Volume |
|---|---|---|
| `laws` | Textes consolidés (نصوص محينة) — base des réponses | 585 PDF → 13 098 chunks |
| `adala_pdfs` | Scrape complet du portail adala.justice.gov.ma | ~4 456 PDF |
| `juris` | Arrêts de la Cour de cassation (Chambre 6 + métadonnées Excel) | ~6 858 PDF |

---

## 🔎 Vérifiabilité — la visionneuse de preuves

`GET /api/viewer?file=<pdf>&chunk=<n>` — page RTL côte à côte :

- **Image de la page originale** (rendu PyMuPDF) avec le **passage cité surligné
  en jaune** (localisation par recherche dans la couche texte)
- **Texte OCR** effectivement utilisé par le modèle, en regard
- Navigation page précédente/suivante, **suppression du filigrane à l'affichage**
  (`clean=1` — les PDF originaux ne sont jamais modifiés)
- **Badges de version** : 📌 نص محيَّن (+ lien «عرض النص المعدِّل» si l'acte
  modificatif est dans le corpus) · ⚠ تحقق من التعديلات · 🛑 منسوخ محتمل
- `GET /api/viewer/samples` — échantillon aléatoire cliquable : sert d'outil
  d'audit qualité OCR

Chaque réponse du chat ajoute automatiquement des liens
«🔎 التحقق من النص الأصلي (ص. N)» vers cette visionneuse
(base configurable via `VIEWER_BASE_URL`).

---

## 🗂 Gestion du corpus

### Console d'administration (lecture seule)

- `GET /api/admin` — tableau de bord : volumes par collection, chunks, statuts
  de version, backlog OCR, doublons, dernière ingestion
- `GET /api/admin/docs` — inventaire filtrable (nom, numéro officiel, collection,
  statut) avec étiquettes d'état par document
- `GET /api/admin/doc?file=…` — fiche document : métadonnées + liste des chunks
  (page, statut, extrait) reliés à la visionneuse
- `GET /api/admin/refresh` — recharge les caches après régénération des données

### Guichet d'ingestion (`pipeline/ingest.py`)

```bash
python pipeline/ingest.py init          # registre des 3 collections (sha1,
                                        # empreinte texte, numéros officiels)
python pipeline/ingest.py add [dossier] # traite la boîte d'entrée (défaut: inbox/)
```

Verdicts par fichier : **doublon octets** (rejeté) · **doublon contenu** —
même texte sous un autre nom/date (rejeté) · **version potentielle** — même
numéro officiel (accepté + signalé pour arbitrage) · **nouveau** (accepté ;
les scans partent au backlog OCR). Rapport JSON à chaque passage.

### Versionnement des textes (`pipeline/version_graph.py`)

- Extraction des notes de consolidation («تم تغيير وتتميم المادة … بمقتضى …
  رقم …») → graphe article par article (`version_graph.json`)
- Détection des abrogations et des actes modificatifs
- Corpus enrichi `laws_corpus_v2.jsonl` : chaque chunk porte
  `status` / `amended_by` / `page`
- Ces statuts sont **injectés dans le contexte du LLM** (rag/answer.py), qui a
  pour instruction de les restituer ; en cas de jurisprudences contradictoires,
  le prompt impose de présenter les deux positions datées **sans trancher**

---

## ⚙️ Pipeline de données (`pipeline/`)

| Script | Rôle |
|---|---|
| `poc_ocr.py` | OCR GPU des PDF scannés (Nanonets-OCR, pod RunPod) |
| `rechunk_core.py` / `export_corpus.py` | Découpage article-aware → corpus JSONL |
| `page_map.py` | Rattachement chunk → page PDF (94 % exact via couche texte) |
| `version_graph.py` | Dédoublonnage + graphe d'amendements + corpus v2 |
| `ingest.py` | Registre + boîte d'entrée avec dédoublonnage |
| `juris_extract.py` | Extraction texte des arrêts (couche texte) + backlog OCR |
| `adala_alias_index.py` | Index numéro officiel → fichiers (bloc-titre, contenu) |
| `catalog_pass1.py` / `juris_link_analysis.py` | Catalogage du scrape + analyse des liens قاعدة |

---

## 🚀 Démarrage

### Prérequis

| Outil | Rôle |
|---|---|
| Python 3.11+ | Runtime (PyMuPDF, FastAPI, numpy…) |
| Qdrant | Vector store (collections `laws_*`, embeddings bge-m3 1024d) |
| Ollama | Embeddings `bge-m3` + LLM de génération |
| GPU (pod RunPod ou local) | OCR Nanonets + LLM 32B (la génération de qualité) |

```bash
pip install -r requirements.txt

# Backend API (port 8000)
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Interface conseillée : Open WebUI branché en OpenAI-compatible
#   base_url = http://localhost:8000/v1   +   clé API (générée au 1er démarrage,
#   voir logs / fichier api_keys)
```

Chemins des données : `core/config.py` et en-têtes des scripts `pipeline/*`
(déploiement local actuel : `Y:\adala-project\` ; pod : `/workspace`).

### Endpoints principaux

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/chat/completions` | Chat OpenAI-compatible (clé API requise) |
| `GET` | `/v1/models` | Découverte du modèle `adala-legal` |
| `POST` | `/v1/chat` | Chat natif : `sources` structurées + sessions |
| `GET` | `/api/viewer` | Visionneuse de preuves |
| `GET` | `/api/admin` | Console d'administration |
| `POST` | `/api/upload`, `GET /api/search` | OCR + recherche plein-texte (app historique) |

---

## 🧭 Règles métier du prompt (rag/answer.py)

1. Réponses **exclusivement** fondées sur les extraits fournis ; refus explicite
   sinon (« لم أعثر على نص قانوني مطبّق… ») — jamais d'article inventé
2. Citation systématique : numéro d'article + nom du texte
3. Statuts de version restitués (نص محيَّن / تحقق من التعديلات / منسوخ محتمل)
4. Jurisprudences contradictoires : les deux positions, datées, sans arbitrage
5. Question en français → réponse en français, citations en arabe officiel ;
   toute traduction accompagne le **texte arabe original**, seul faisant foi

---

## 📋 Feuille de route

- [ ] OCR du backlog jurisprudence (5 141 arrêts scannés) — pod GPU
- [ ] Indexation Qdrant des arrêts extraits (1 707 disponibles) + clustering
      des questions juridiques pour détecter les divergences d'اجتهاد
- [ ] Scrape ciblé des actes modificatifs manquants (~36 numéros cités par les
      notes de consolidation, liste dans `version_graph.json`)
- [ ] Ré-ingestion Qdrant avec les champs de version (jointure au service
      aujourd'hui) ; corpus français officiel (BO) pour les réponses FR
- [ ] Jeu de test « golden » (50–100 Q/R validées) + évaluation de régression
- [ ] Authentification de la console d'administration avant tout déploiement
      hors localhost ; actions d'administration (exclusion, ré-indexation)

---

## 📄 Licence

© 2025-2026 وزارة العدل — المملكة المغربية · DMSI · Ing. Mouad Boukhari
Usage interne uniquement.
