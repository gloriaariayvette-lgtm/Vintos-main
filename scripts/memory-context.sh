#!/bin/bash
# memory-context.sh — Returns relevant memories for a given prompt
# Used by other scripts to give Vintos his own history
QUERY="$1"
[ -z "$QUERY" ] && exit 0
INDEX="$HOME/.vintos/workspace/memory/embeddings.jsonl"
[ ! -f "$INDEX" ] && exit 0
Q_EMB=$(curl -s --max-time 30 http://172.18.16.1:1234/v1/embeddings \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$QUERY" '{model:"text-embedding-nomic-embed-text-v1.5",input:$text}')" | jq -c '.data[0].embedding')
[ "$Q_EMB" = "null" ] || [ -z "$Q_EMB" ] && exit 0
python3 - "$Q_EMB" "$INDEX" << 'PYEOF'
import json,sys,math
def cos(a,b):
    d=sum(x*y for x,y in zip(a,b));na=math.sqrt(sum(x*x for x in a));nb=math.sqrt(sum(x*x for x in b))
    return d/(na*nb) if na and nb else 0
q=json.loads(sys.argv[1])
results=[]
with open(sys.argv[2]) as f:
    for line in f:
        line=line.strip()
        if not line: continue
        e=json.loads(line)
        results.append((cos(q,e["embedding"]),e))
results.sort(key=lambda x:x[0],reverse=True)
for s,e in results[:3]:
    if s>0.4:
        print(e["text"].strip()[:200])
        print("---")
PYEOF
