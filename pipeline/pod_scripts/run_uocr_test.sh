#!/bin/bash
# attend la fin de l'installation, puis lance le test — sans intervention
while ! grep -q UOCR_SETUP_DONE /workspace/uocr_setup.log 2>/dev/null; do
  if ! pgrep -f setup_uocr.sh > /dev/null; then
    echo 'INSTALLATION INTERROMPUE — voir uocr_setup.log'; exit 1
  fi
  sleep 20
done
export HF_HOME=/workspace/hf_home
/workspace/venv_uocr/bin/python /workspace/test_uocr.py
