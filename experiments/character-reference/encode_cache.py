#!/usr/bin/env python3
"""Explicit private GGUF cache producer; no live hooks, downloads or discovery."""
import contextlib
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cache_evidence_runner',HERE.parent/'nonllm-judges/run_private.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
C=R.C;P=R.P
MAX_ARTIFACT=4*1024**3


def signature(info):
    return tuple(getattr(info,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))


def regular(path):
    if path.absolute()!=path.resolve(strict=True) or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('explicit nonsymlink regular file required')
    return path.stat()


def pin_copy(path):
    before=regular(path)
    if not 4<=before.st_size<=MAX_ARTIFACT:raise ValueError('artifact size outside bound')
    h=hashlib.sha256()
    with path.open('rb') as f:
        if signature(os.fstat(f.fileno()))!=signature(before):raise ValueError('artifact changed')
        while chunk:=f.read(1024*1024):h.update(chunk)
        if signature(os.fstat(f.fileno()))!=signature(before):raise ValueError('artifact changed')
    if signature(regular(path))!=signature(before):raise ValueError('artifact changed')
    return h.hexdigest(),signature(before)


def copy_artifact(source,target):
    before=regular(source)
    if not 4<=before.st_size<=MAX_ARTIFACT:raise ValueError('artifact size outside bound')
    total=0
    with source.open('rb') as src,target.open('xb') as dst:
        target.chmod(0o600)
        if signature(os.fstat(src.fileno()))!=signature(before):raise ValueError('source changed')
        first=src.read(4)
        if first!=b'GGUF':raise ValueError('GGUF artifact required')
        dst.write(first);total=4
        while chunk:=src.read(1024*1024):
            total+=len(chunk)
            if total>MAX_ARTIFACT:raise ValueError('artifact too large')
            dst.write(chunk)
        if total!=before.st_size or signature(os.fstat(src.fileno()))!=signature(before):raise ValueError('source changed')
        dst.flush();os.fsync(dst.fileno())
    if signature(regular(source))!=signature(before):raise ValueError('source changed')
    target.chmod(0o400)
    frozen_at=time.time()
    digest,sig=pin_copy(target)
    return digest,sig,frozen_at


class LocalEncoder:
    """Only the installed in-process embedding API; never a runtime downloader."""
    def __init__(self,path,settings):
        import llama_cpp
        self.version=getattr(llama_cpp,'__version__',None)
        if not P.identifier(self.version):raise ValueError('runtime version unavailable')
        pool=getattr(llama_cpp,'LLAMA_POOLING_TYPE_'+settings['pooling'].upper())
        self.model=llama_cpp.Llama(model_path=str(path),embedding=True,n_gpu_layers=0,
            n_ctx=settings['context_tokens'],n_batch=settings['context_tokens'],pooling_type=pool,
            n_threads=settings['threads'],n_threads_batch=settings['threads'],verbose=False,use_mmap=False,
            offload_kqv=False,op_offload=False,flash_attn=False)
        if self.model.pooling_type()!=pool:
            self.model.close();raise ValueError('runtime pooling mismatch')
        self.runtime={'name':'llama-cpp-python','version':self.version,'native_version':None}

    def encode(self,text):return self.model.embed(text,normalize=False,truncate=False)
    def close(self):self.model.close()


@contextlib.contextmanager
def quiet_native(null_fd):
    # Native loaders can print private paths even when their Python exception is sanitized.
    saved=[os.dup(1),os.dup(2)]
    try:
        sys.stdout.flush();sys.stderr.flush()
        os.dup2(null_fd,1);os.dup2(null_fd,2)
        yield
    finally:
        sys.stdout.flush();sys.stderr.flush()
        for fd,old in zip((1,2),saved):os.dup2(old,fd);os.close(old)


def selected_rows(bundle,cutoff):
    if bundle.get('input_kind') not in ('synthetic','retained_snapshot'):raise ValueError('explicit input kind required')
    if bundle.get('numerical_evidence') is not None:raise ValueError('encode before deriving numerical evidence')
    # Existing control embeddings cannot be silently relabelled with the new encoder.
    if bundle.get('controls') or bundle.get('control_pool'):raise ValueError('control caches require separate production')
    if not isinstance(bundle.get('rows'),list) or len(bundle['rows'])>10000:raise ValueError('bounded rows required')
    by_id={};by_hash={}
    for row in bundle['rows']:
        if row.get('role')!='assistant' or P.stamp(row['timestamp'])>=cutoff:continue
        key=row.get('turn_id');text=C.final_response(row);context=row.get('context')
        if (not P.identifier(key) or not isinstance(text,str) or not 0<len(text)<=65536
                or not isinstance(context,str) or not 0<len(context)<=65536):raise ValueError('exact reply identity and nonempty context required')
        sha=C.digest(text);ctx=C.digest(context);identity=(sha,ctx,P.stamp(row['timestamp']))
        if key in by_id and by_id[key]!=identity:raise ValueError('conflicting reply identity')
        by_id[key]=identity
        if sha in by_hash:
            if by_hash[sha]['context_sha256']!=ctx:raise ValueError('same reply has multiple contexts')
            by_hash[sha]['reply_ids'].add(key)
        else:by_hash[sha]=dict(text=text,context=context,reply_ids={key},reply_sha256=sha,input_sha256=sha,context_sha256=ctx,at=identity[2])
    if not by_hash or len(by_id)>512:raise ValueError('requires one to 512 explicit replies')
    return list(by_hash.values()),by_id


def unit(value,dimension=None):
    if (not isinstance(value,list) or not 1<=len(value)<=2048 or (dimension is not None and len(value)!=dimension)
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in value)):raise ValueError('invalid pooled vector')
    norm=math.hypot(*value)
    if not math.isfinite(norm) or norm==0:raise ValueError('invalid vector norm')
    return [v/norm for v in value]


def run(argv=None,factory=LocalEncoder):
    p=R.Parser(description=__doc__)
    for k in ('gguf','input','scratch','output','cutoff','pooling'):p.add_argument('--'+k,required=True)
    p.add_argument('--context-tokens',type=int,default=8192);p.add_argument('--threads',type=int,default=2)
    args=p.parse_args(argv)
    if args.pooling not in ('mean','cls','last') or not 128<=args.context_tokens<=32768 or not 1<=args.threads<=32:raise ValueError('invalid encoder settings')
    root=C.scratch_root(args.scratch)
    if any((parent/'.git').exists() for parent in (root,*root.parents)):raise ValueError('scratch cannot be inside repository')
    source=Path(args.gguf).absolute();regular(source)
    if any(part in ('.vintos','.openclaw') for part in source.parts):raise ValueError('use an explicitly retained model artifact')
    inp=C.inside(root,args.input);out=C.inside(root,args.output)
    if out.exists() or out in inp.parents or out in source.parents:raise ValueError('new output directory required')
    regular(inp)
    null_fd=os.open(os.devnull,os.O_WRONLY)
    try:
        C.install_guard(root,out)
        bundle,input_hash=R.read_projection(inp,64*1024*1024)
        cutoff=P.stamp(args.cutoff);rows,ids=selected_rows(bundle,cutoff)
        check=copy.deepcopy(bundle);check['embeddings']=[];C.prepare(check,cutoff)
        out.mkdir(mode=0o700);artifact=out/'encoder-copy.gguf'
        artifact_hash,artifact_sig,frozen_at=copy_artifact(source,artifact)
        settings=dict(pooling=args.pooling,normalization='l2',input_policy='exact_full_strings',truncate=False,
                      context_tokens=args.context_tokens,threads=args.threads,n_gpu_layers=0,use_mmap=False,
                      offload_kqv=False,op_offload=False,flash_attn=False)
        def unchanged(full=False):
            if signature(regular(artifact))!=artifact_sig:raise ValueError('copied artifact changed')
            if full and pin_copy(artifact)!=(artifact_hash,artifact_sig):raise ValueError('copied artifact changed')
        vectors={};clocks={};dimension=None;encoder=None
        with quiet_native(null_fd):
            try:
                unchanged(True);encoder=factory(artifact,settings);unchanged(True)
                runtime=encoder.runtime
                if (not isinstance(runtime,dict) or not P.identifier(runtime.get('name')) or not P.identifier(runtime.get('version'))):raise ValueError('runtime identity unavailable')
                for row in rows:
                    for text in (row['text'],row['context']):
                        if text in vectors:continue
                        unchanged();started=time.time();vector=unit(encoder.encode(text),dimension);finished=time.time();unchanged()
                        if started<frozen_at or finished<started:raise ValueError('encoding clock inconsistent')
                        clocks[text]={'started_at':started,'finished_at':finished}
                        dimension=len(vector);vectors[text]=vector
            finally:
                if encoder is not None:encoder.close()
        unchanged(True)
        encoder_id='gguf-'+C.digest(P.canonical({'artifact_sha256':artifact_hash,'runtime':runtime,'settings':settings}))
        enc=dict(family=bundle['encoder']['family'],id=encoder_id,revision='sha256:'+artifact_hash,pooling=args.pooling,
                 normalization='l2',prefix_chars=65536,frozen=True,artifact_sha256=artifact_hash)
        entries=[];embeddings=[]
        for row in rows:
            binding={k:row[k] for k in ('reply_sha256','input_sha256','context_sha256')}
            entry=dict(binding,reply_ids=sorted(row['reply_ids']),encoder_id=encoder_id,artifact_sha256=artifact_hash,
                       frozen_at=frozen_at,runtime=runtime,settings=settings,reply_encoding=clocks[row['text']],context_encoding=clocks[row['context']])
            entries.append(entry)
            embeddings.append(dict(binding,encoder_id=encoder_id,vector=vectors[row['text']],context_vector=vectors[row['context']]))
        projection=copy.deepcopy(bundle);projection['encoder']=enc;projection['embeddings']=embeddings
        manifest={'schema':'private-cache-producer-v1','input_sha256':input_hash,'source_encoder_declaration':bundle['encoder'],
                  'artifact_sha256':artifact_hash,'artifact_bytes':artifact_sig[2],'frozen_at':frozen_at,'runtime':runtime,'settings':settings,
                  'encoder_id':encoder_id,'embedding_calls':len(vectors),'completion_calls':0,'historical_backfill':False,
                  'code_sha256':{str(path.relative_to(R.REPO)):C.digest(path.read_text()) for path in
                    (Path(__file__),HERE/'prototype.py',HERE.parent/'nonllm-judges/run_private.py',HERE.parent/'judges-witness/replay.py')},
                  'native_code_sandboxed_by_python_audit':False}
        projection['cache_producer']=manifest
        # Validate the fresh cache contract without selecting or changing lineage/controls.
        C.prepare(projection,cutoff)
        payloads={'character-input.json':projection,'cache.json':{'schema':'character-cache-v1','encoder':enc,'embeddings':embeddings,'manifest':manifest},
                  'cache-metadata.json':{'schema':'encoder-cache-metadata-v1','entries':entries},
                  'counts.json':{'schema':'cache-producer-counts-v1','reply_ids':len(ids),'cache_entries':len(entries),
                      'unique_encoded_strings':len(vectors),'dimension':dimension,'replies_predating_freeze':sum(i[2]<=frozen_at for i in ids.values()),
                      'completion_calls':0,'historical_backfill':False}}
        serialized={k:json.dumps(v,sort_keys=True,allow_nan=False)+'\n' for k,v in payloads.items()}
        unchanged(True)
        for name,value in serialized.items():
            with (out/name).open('x') as f:(out/name).chmod(0o600);f.write(value)
        print(json.dumps({'written':True,'reports':4}))
    finally:os.close(null_fd)


if __name__=='__main__':
    try:run()
    except Exception:
        print(json.dumps({'written':False,'error':'cache_production_failed'}),file=sys.stderr);sys.exit(1)
