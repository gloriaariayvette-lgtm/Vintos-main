#!/usr/bin/env python3
"""The real Markdown writer format is readable without an index or promotion."""
import ast,json,os,pathlib,socket,sys,tempfile,types
ROOT=pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='pearl-reader-') as tmp:
 os.environ['HOME']=tmp
 sys.path.insert(0,str(ROOT/'scripts'))
 def forbidden(*a,**k):raise AssertionError('sender forbidden')
 socket.socket.connect=forbidden
 import pearl_engine as P
 assert P.MEMORY.startswith(tmp) and P.CANDIDATES_FILE.startswith(tmp)
 root=pathlib.Path(P.PEARLS_DIR);root.mkdir(parents=True)
 content='An existing remembered event, preserved as written.'
 (root/'pearl_20261009_224046.md').write_text('# Pearl — 2026-10-09 22:40\n\n'+content+'\n\n---\n**Source:** wal-graduation\n')
 (root/'pearl_20261010_100000.md').write_text('# Pearl — 2026-10-10 10:00\n\nAn already-formed integration.\n\n---\n**Irritant:** an old friction\n**Source:** mirror:2026-10-10\n**Candidate ID:** cp-fixture\n')
 pathlib.Path(P.CANDIDATES_FILE).write_text(json.dumps({'candidates':[{'id':'failed','stage':1,'dissolved':True,'declaration':'Not a Pearl'}]}))
 rows=P.list_formed_pearls();assert len(rows)==2
 assert {x['source'] for x in rows}=={'wal-graduation','mirror:2026-10-10'}
 assert all(x['content']!='Not a Pearl' for x in rows)
 (root/'index.json').write_text(json.dumps({'pearls':[{'content':content,'created':'2026-10-09','id':'existing-index'}]}))
 assert len(P.list_formed_pearls())==2
 tree=ast.parse((ROOT/'bin/server.py').read_text());fn=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='get_pearls')
 assert fn.args.args[0].arg=='request'
 assert isinstance(fn.body[1],ast.Expr) and isinstance(fn.body[1].value,ast.Call) and fn.body[1].value.func.id=='_require_secret'
 assert socket.socket.connect is forbidden
 print('PASS real Markdown plus index deduplication, original source/content, no failed-candidate promotion, authenticated API; scratch only and no sender')
