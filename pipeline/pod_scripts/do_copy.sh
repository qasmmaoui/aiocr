#!/bin/bash
SSHOPT="ssh -p 22101 -i /root/.ssh/id_copy -o StrictHostKeyChecking=no -o BatchMode=yes"
echo "=== COPY START $(date -u) ==="
rsync -a --partial --info=progress2 -e "$SSHOPT" root@69.30.85.210:/workspace/ /workspace/
echo "=== RSYNC_DONE rc=$? $(date -u) ==="
du -sh /workspace
