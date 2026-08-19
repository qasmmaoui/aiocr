#!/bin/bash
# Installation isolée de baidu/Unlimited-OCR (n'touche pas au venv ollama/RAG).
set -x
V=/workspace/venv_uocr
python3 -m venv $V
$V/bin/pip install -q --upgrade pip
# torch cu129 : sm_120 (Blackwell) exige CUDA >= 12.8
$V/bin/pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu129
$V/bin/pip install transformers==4.57.1 'Pillow==12.1.1' matplotlib einops addict easydict pymupdf psutil accelerate 'huggingface_hub[cli]'
export HF_HOME=/workspace/hf_home
$V/bin/hf download baidu/Unlimited-OCR
echo UOCR_SETUP_DONE
