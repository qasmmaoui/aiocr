#!/bin/bash
set -x
curl -fsSL https://ollama.com/install.sh | sh
export OLLAMA_MODELS=/workspace/ollama OLLAMA_NUM_PARALLEL=1 OLLAMA_KEEP_ALIVE=30m
nohup ollama serve > /workspace/ollama_cmp.log 2>&1 &
sleep 20
ollama list
IMG=/workspace/uocr_test/2007-265_2005-1-4-68_p1.png
/workspace/venv_uocr/bin/python - << 'PY'
import base64, json, time, urllib.request
img = base64.b64encode(open('/workspace/uocr_test/2007-265_2005-1-4-68_p1.png','rb').read()).decode()
body = json.dumps({model:qwen2.5vl:32b,
  prompt:استخرج النص العربي الكامل من هذه الصفحة حرفيا، دون تعليق ودون ترجمة.,
  images:[img], stream:False,
  options:{temperature:0.0,num_ctx:8192,num_predict:2000}}).encode()
t0=time.time()
r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/generate',
    body, {'Content-Type':'application/json'}), timeout=900)
out=json.loads(r.read())['response']
open('/workspace/uocr_test/qwen_p1.txt','w',encoding='utf-8').write(out)
print(f'QWEN {time.time()-t0:.1f}s {len(out)} caracteres')
print(out[:1500])
PY
echo CMP_DONE
