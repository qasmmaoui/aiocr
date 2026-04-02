# ⚖️ Adala — البوابة القانونية لوزارة العدل

> **DMSI · Ing. Mouad** — Plateforme d'extraction et de recherche intelligente de documents juridiques arabes.

---

## 📐 Architecture

```
adala_app/
│
├── app.py                        # 🖥️  Frontend Streamlit  (UI)
│
├── api/
│   ├── __init__.py
│   └── main.py                   # 🚀  Backend FastAPI     (API REST)
│
├── core/
│   ├── __init__.py
│   ├── config.py                 # ⚙️  Configuration centrale (chemins, modèles…)
│   └── utils.py                  # 🔧  Utilitaires (hash, logo, Ollama)
│
├── services/
│   ├── __init__.py
│   ├── correction_service.py     # ✍️  Correction OCR arabe (dict + regex)
│   ├── ocr_service.py            # 📷  OCR : Tesseract → Ollama Vision (fallback)
│   └── extraction_service.py    # 📄  Extraction PDF, cache JSON, classification
│
├── search/
│   ├── __init__.py
│   ├── engine.py                 # 🔍  Normalisation arabe, distance d'édition, highlight
│   └── indexer.py                # 📑  Index inversé, correction requête, suggestions
│
├── data/
│   ├── uploads/                  # PDFs téléversés
│   ├── cache_corrections/        # Cache JSON par hash MD5
│   └── search_index/             # index.json
│
├── assets/
│   └── zz.png                    # Logo Adala
│
├── requirements.txt
└── README.md
```

### Flux de données

```
Utilisateur (navigateur)
       │  HTTP
       ▼
 ┌─────────────┐   REST /api/*   ┌──────────────────┐
 │  Streamlit  │ ─────────────▶ │   FastAPI         │
 │  app.py     │ ◀───────────── │   api/main.py     │
 └─────────────┘    JSON        └──────┬───────────┘
                                       │
                     ┌─────────────────┼──────────────────┐
                     ▼                 ▼                    ▼
              extraction_service  ocr_service         indexer.py
              (PyMuPDF)           (Tesseract/Ollama)  (index JSON)
                     │                 │
                     └────── correction_service ──────────┘
```

---

## 🛠️ Prérequis

| Outil | Version minimale | Rôle |
|-------|-----------------|------|
| Python | 3.11+ | Runtime |
| Tesseract OCR | 5.x | OCR arabe/français |
| Ollama | 0.3+ | Modèle vision (fallback OCR) |
| Git | 2.x | Versioning |

---

## 🚀 Installation — Étape par étape

### 1. Cloner le dépôt

```bash
git clone https://github.com/<votre-org>/adala_app.git
cd adala_app
```

### 2. Créer un environnement virtuel

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Installer les dépendances Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Installer Tesseract OCR

**Windows :**
```
https://github.com/UB-Mannheim/tesseract/wiki
→ Télécharger tesseract-ocr-w64-setup-5.x.exe
→ Cocher les langues : Arabic, French
→ Chemin par défaut : C:\Program Files\Tesseract-OCR\tesseract.exe
```

**Ubuntu / Debian :**
```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra
```

**macOS :**
```bash
brew install tesseract tesseract-lang
```

### 5. Installer et démarrer Ollama (optionnel — fallback vision)

```bash
# Installation
curl -fsSL https://ollama.com/install.sh | sh

# Télécharger le modèle vision recommandé
ollama pull qwen2.5vl:3b
```

> ℹ️ Sans Ollama, seul Tesseract est utilisé. Les pages « scan » sans Tesseract ne seront pas extraites.

### 6. (Optionnel) Ajouter votre logo

```bash
cp votre_logo.png assets/zz.png
```

---

## ▶️ Démarrage du projet

### Terminal 1 — Backend FastAPI

```bash
# Depuis la racine du projet
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

✅ API disponible sur : `http://localhost:8000`  
📖 Documentation Swagger : `http://localhost:8000/docs`  
📖 Documentation Redoc : `http://localhost:8000/redoc`

### Terminal 2 — Frontend Streamlit

```bash
streamlit run app.py
```

✅ Interface disponible sur : `http://localhost:8501`

---

## 📡 Endpoints de l'API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/api/health` | Vérification de l'état du service |
| `GET` | `/api/stats` | Statistiques de l'index |
| `GET` | `/api/documents` | Liste des documents indexés |
| `POST` | `/api/upload` | Upload + extraction + indexation d'un PDF |
| `DELETE` | `/api/documents/{id}` | Suppression d'un document |
| `GET` | `/api/search?q=…` | Recherche full-text en arabe |
| `GET` | `/api/pdf/{filename}` | Téléchargement du PDF original |
| `GET` | `/api/documents/{id}/text` | Export du texte brut d'un document |

### Exemple — Upload via curl

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@mon_document.pdf"
```

### Exemple — Recherche via curl

```bash
curl "http://localhost:8000/api/search?q=الظهير+الشريف"
```

### Exemple — Intégration Python

```python
import requests

# Upload
with open("doc.pdf", "rb") as f:
    r = requests.post("http://localhost:8000/api/upload", files={"file": f})
    print(r.json())

# Recherche
r = requests.get("http://localhost:8000/api/search", params={"q": "الدستور"})
for result in r.json()["results"]:
    print(result["filename"], "—", len(result["matches"]), "correspondances")
```

---

## ⚙️ Configuration

Toute la configuration est centralisée dans `core/config.py` :

```python
# Changer le port de l'API
API_PORT = 8000

# Changer l'URL que Streamlit utilise pour appeler FastAPI
API_BASE_URL = "http://localhost:8000"

# Changer le modèle Ollama préféré
PREFERRED_MODELS = ["qwen2.5vl:7b", "qwen2.5vl:3b"]
```

---

## 🗂️ Structure des données

### Cache (data/cache_corrections/{hash}.json)

```json
{
  "pages": [
    {"num": 1, "type": "native", "text": "..."},
    {"num": 2, "type": "scan",   "text": "..."}
  ],
  "doc_type": "mixed",
  "nb_pages": 10,
  "n_native": 7,
  "n_scan": 3
}
```

### Index de recherche (data/search_index/index.json)

```json
{
  "v": {
    "القضاء": { "f": {"القضاء": 42}, "n": 42 }
  },
  "d": {
    "<md5_hash>": {
      "fn": "ظهير_شريف.pdf",
      "np": 15,
      "dt": "2025-01-15T10:30:00",
      "p":  {"1": "نص الصفحة الأولى..."},
      "pn": {"1": "نص منقح..."}
    }
  }
}
```

---

## 🧪 Tester l'installation

```bash
# Vérifier que l'API répond
curl http://localhost:8000/api/health
# {"status":"ok","version":"1.0.0"}

# Vérifier les stats
curl http://localhost:8000/api/stats
# {"docs":0,"words":0,"pages":0}
```

---

## 🔒 Déploiement en production

### Variables d'environnement recommandées

```bash
export ADALA_API_HOST=0.0.0.0
export ADALA_API_PORT=8000
export ADALA_STREAMLIT_PORT=8501
```

### Avec Docker Compose (recommandé)

```yaml
# docker-compose.yml (à créer)
version: '3.9'
services:
  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    volumes: ["./data:/app/data", "./assets:/app/assets"]

  frontend:
    build: .
    command: streamlit run app.py --server.port 8501
    ports: ["8501:8501"]
    depends_on: [api]
    environment:
      - API_BASE_URL=http://api:8000
```

### Sécuriser l'API en production

Dans `api/main.py`, remplacer :
```python
allow_origins=["*"]
```
par :
```python
allow_origins=["http://votre-domaine.ma"]
```

---

## 👥 Contribution

```bash
# Créer une branche feature
git checkout -b feature/nom-de-la-fonctionnalite

# Committer
git add .
git commit -m "feat: description de la modification"

# Pousser
git push origin feature/nom-de-la-fonctionnalite
```

---

## 📋 Feuille de route

- [ ] Pagination des résultats de recherche
- [ ] Analyse sémantique avec embeddings arabes
- [ ] Export PDF annoté
- [ ] Interface d'administration des documents
- [ ] Tests unitaires (pytest)

---

## 📄 Licence

© 2025 وزارة العدل — المملكة المغربية · DMSI . Ing. Mouad Boukhari
Usage interne uniquement.
