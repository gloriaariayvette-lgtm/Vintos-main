#!/usr/bin/env python3
"""Synthetic CPU observation-cost benchmark; no model, input store or live sink."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay
import numpy as np
from witness_self_artifacts import FeatureEncoder


def validate(mib, tensors, iterations, layout, runtime_profile="minimal"):
    if (type(mib) is not int or not 1 <= mib <= 512
            or type(tensors) is not int or tensors not in (1, 8, 64, 128)
            or type(iterations) is not int or not 1 <= iterations <= 10
            or layout not in ('contiguous', 'strided')
            or runtime_profile not in ('minimal', 'configured')):
        raise ValueError('invalid bounded synthetic benchmark options')


class SyntheticEncoder:
    def __init__(self, mib, tensors, layout, runtime_profile="minimal"):
        size = mib * 1024 * 1024 // 4 // tensors
        stride = 2 if layout == 'strided' else 1
        self.buffers = [np.ones(size * stride, dtype=np.float32) for _ in range(tensors)]
        self.parameters = {f'synthetic_{i}': b[::stride] for i, b in enumerate(self.buffers)}
        self.output = np.tile(np.linspace(.01, .99, 768, dtype=np.float64), (13, 1))
        self.encode_calls = self.snapshot_calls = 0
        if runtime_profile == 'configured':
            self.training = False
            self.max_seq_length = 256
            self.prompts = {'synthetic': 'synthetic instruction'}
            self.default_prompt_name = 'synthetic'
            self._modules = {
                'encoder': SimpleNamespace(training=False,
                    config=SimpleNamespace(hidden_size=768, layer_count=12, dropout=0.0),
                    tokenizer=SimpleNamespace(model_max_length=256, padding_side='right',
                        truncation_side='right', init_kwargs={'lower_case':False}),
                    _modules={'normalizer':SimpleNamespace(training=False)}),
                'pooling':SimpleNamespace(training=False)}

    def state_dict(self):
        self.snapshot_calls += 1
        return self.parameters

    def encode(self, texts, **kwargs):
        self.encode_calls += 1
        return self.output


def measure(call):
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    result = call()
    return result, {'wall_ms': (time.perf_counter_ns()-wall)/1e6,
                    'process_cpu_ms': (time.process_time_ns()-cpu)/1e6}


def benchmark(mib=64, tensors=8, iterations=3, layout='contiguous', runtime_profile='minimal'):
    validate(mib, tensors, iterations, layout, runtime_profile)
    import witness_capture  # Preload the receipt helper before timed observations.
    enc = SyntheticEncoder(mib, tensors, layout, runtime_profile)
    texts = [f'synthetic feature {i}' for i in range(13)]
    fresh_texts = [f'synthetic repeat feature {i}' for i in range(13)]
    timings = {name: [] for name in ('bare_stub', 'first_observed_call', 'repeat_without_snapshot',
                                   'repeat_new_inputs_without_snapshot')}
    coverage = {'first_observed_call':0, 'repeat_new_inputs_without_snapshot':0}
    expected_runtime = ({'modules':4,'module_settings':4,'configs':1,'tokenizers':1,'tokenizer_settings':1}
                        if runtime_profile == 'configured' else
                        {'modules':1,'module_settings':0,'configs':0,'tokenizers':0,'tokenizer_settings':0})
    for _ in range(iterations):
        wrapped = FeatureEncoder(enc)
        for name, call in (('bare_stub', lambda: enc.encode(texts, show_progress_bar=False)),
                           ('first_observed_call', lambda: wrapped.encode(texts, show_progress_bar=False)),
                           ('repeat_without_snapshot', lambda: wrapped.encode(texts, show_progress_bar=False)),
                           ('repeat_new_inputs_without_snapshot', lambda: wrapped.encode(fresh_texts, show_progress_bar=False))):
            value, elapsed = measure(call)
            if value is not enc.output: raise RuntimeError('observer changed the return object')
            timings[name].append(elapsed)
            if name in coverage:
                current = texts if name == 'first_observed_call' else fresh_texts
                records = [wrapped.records.get(text) for text in current]
                if any(record is None for record in records): raise RuntimeError('missing synthetic observations')
                for record in records:
                    obs = record['call']
                    if name == 'first_observed_call':
                        if (obs['parameter_state'] != 'observed_equal'
                                or obs['parameter_before']['bytes'] != mib*1024*1024
                                or obs['parameter_before']['tensors'] != tensors):
                            raise RuntimeError('synthetic snapshot unavailable or inconsistent')
                    elif obs['parameter_state'] != 'unavailable':
                        raise RuntimeError('repeat unexpectedly sampled parameters')
                    for field in ('runtime','entrypoint'):
                        pair = obs.get(field)
                        if not isinstance(pair,dict) or pair.get('state') != 'observed_equal':
                            raise RuntimeError('synthetic runtime or entrypoint observation unavailable or inconsistent')
                        if pair['before'] != pair['after']:
                            raise RuntimeError('synthetic observation changed across encode')
                    if any(obs['runtime']['before'][k] != n for k,n in expected_runtime.items()):
                        raise RuntimeError('synthetic runtime profile coverage mismatch')
                if len({record['call']['invocation'] for record in records}) != 1:
                    raise RuntimeError('synthetic vectors do not belong to one call')
                if name == 'repeat_new_inputs_without_snapshot':
                    prior = wrapped.records[texts[0]]['call']['invocation']
                    if records[0]['call']['invocation'] == prior:
                        raise RuntimeError('repeat reused a stale observation')
                coverage[name] += 1
    if enc.encode_calls != iterations*4 or enc.snapshot_calls != iterations*2:
        raise RuntimeError('unexpected encode or snapshot call count')
    return {'schema': 'judges-encoder-cost-v2', 'input_kind': 'synthetic_cpu_arrays',
            'logical_parameter_bytes': mib*1024*1024,
            'allocated_parameter_array_bytes': sum(b.nbytes for b in enc.buffers),
            'layout': layout, 'tensors': tensors, 'iterations': iterations,
            'runtime_profile':runtime_profile,
            'observation_coverage':{'checked_calls':coverage, 'vectors_per_checked_call':len(texts),
                                    'stored_runtime_components_per_snapshot':expected_runtime,
                                    'parameter_pairs_per_iteration':1,
                                    'entrypoint':'loaded_synthetic_python_function',
                                    'same_input_repeat_receipts':'first_call_retained_not_reobserved'},
            'encode_calls': enc.encode_calls, 'snapshot_calls': enc.snapshot_calls,
            'raw_output_values': int(enc.output.size), 'receipt_helpers_preloaded': True,
            'timings': {name: {metric: {'median': statistics.median(r[metric] for r in rows),
                                      'max': max(r[metric] for r in rows)}
                               for metric in ('wall_ms', 'process_cpu_ms')}
                        for name, rows in timings.items()},
            'python_version': list(sys.version_info[:3]), 'numpy_version': np.__version__,
            'meaning': 'synthetic observation overhead only; no real encode, serving latency, loaded-runtime compatibility or pass verdict'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scratch', required=True)
    p.add_argument('--output', required=True, help='new directory strictly inside private scratch')
    p.add_argument('--mib', type=int, default=64)
    p.add_argument('--tensors', type=int, choices=(1,8,64,128), default=8)
    p.add_argument('--iterations', type=int, default=3)
    p.add_argument('--layout', choices=('contiguous','strided'), default='contiguous')
    p.add_argument('--runtime-profile', choices=('minimal','configured'), default='minimal')
    args = p.parse_args()
    validate(args.mib, args.tensors, args.iterations, args.layout, args.runtime_profile)
    root = replay.scratch_root(args.scratch)
    output = replay.inside(root, args.output)
    if output.exists(): raise ValueError('benchmark output already exists')
    replay.install_guard(root, output)
    result = benchmark(args.mib, args.tensors, args.iterations, args.layout, args.runtime_profile)
    repo = Path(__file__).resolve().parents[2]
    result['code_sha256'] = {name: hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in (
        'experiments/judges-witness/benchmark_encoder.py', 'experiments/judges-witness/replay.py',
        'scripts/witness_self_artifacts.py', 'scripts/witness_receipts.py', 'scripts/witness_capture.py')}
    output.mkdir(mode=0o700)
    with (output/'benchmark.json').open('xb') as f:
        os.chmod(f.name, 0o600)
        f.write((json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+'\n').encode())
    print('Synthetic CPU benchmark written in private scratch; not serving acceptance.')


if __name__ == '__main__': main()
