# Déploiement — المساعد القانوني الذكي (aiocr)

Application : **FastAPI** (API, port 8000) + **Streamlit** (UI, port 8888) + **Ollama** (OCR vision `qwen2.5vl:7b`, embeddings `bge-m3`) + **Tesseract** (ara+fra).

## Prérequis
- Python 3.11+
- Tesseract OCR (`tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra`)
- Ollama (`https://ollama.com`) + un GPU NVIDIA recommandé pour l'OCR vision
- `pip install -r requirements.txt`

## Démarrage générique (n'importe quel serveur)
```bash
# 1. Dépendances système
sudo apt-get install -y tesseract-ocr tesseract-ocr-ara tesseract-ocr-fra
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &                 # démarre Ollama
ollama pull qwen2.5vl:7b       # modèle OCR vision
ollama pull bge-m3             # embeddings (RAG)

# 2. Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Lancer
uvicorn api.main:app --host 127.0.0.1 --port 8000 &
streamlit run app.py --server.port 8888 --server.address 0.0.0.0 \
  --server.headless true --server.enableCORS false --server.enableXsrfProtection false
```
L'UI est sur `:8888`, elle appelle l'API en interne sur `localhost:8000`.

## Sur le pod RunPod (persistance /workspace)
Tout ce qui doit survivre à un redémarrage vit sous `/workspace`
(`/workspace/aiocr`, `/workspace/venv`, `/workspace/ollama`).

- **Relancer tout après un Start** : `bash deploy/pod-start.sh`
- **Relancer seulement l'UI** : `setsid bash deploy/restart-ui.sh </dev/null &`
- **Démarrage automatique** : pointer la *Container Start Command* du pod vers
  `pod-start.sh` (voir la note dans le README principal / l'historique de déploiement).

## Notes
- Les données (`data/uploads`, `data/cache_corrections`, `data/search_index`) sont
  ignorées par git — elles restent locales/privées sur le serveur.
- Correctif inclus : chemin Tesseract compatible Linux ; normalisation NFKC de l'arabe ;
  modèle vision en OCR principal ; `num_ctx`/`num_predict` élargis (anti-troncature).
