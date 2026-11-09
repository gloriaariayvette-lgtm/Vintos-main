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

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay
import numpy as np
from witness_self_artifacts import FeatureEncoder


def validate(mib, tensors, iterations, layout):
    if (type(mib) is not int or not 1 <= mib <= 512
            or type(tensors) is not int or tensors not in (1, 8, 64, 128)
            or type(iterations) is not int or not 1 <= iterations <= 10
            or layout not in ('contiguous', 'strided')):
        raise ValueError('invalid bounded synthetic benchmark options')


class SyntheticEncoder:
    def __init__(self, mib, tensors, layout):
        size = mib * 1024 * 1024 // 4 // tensors
        stride = 2 if layout == 'strided' else 1
        self.buffers = [np.ones(size * stride, dtype=np.float32) for _ in range(tensors)]
        self.parameters = {f'synthetic_{i}': b[::stride] for i, b in enumerate(self.buffers)}
        self.output = np.tile(np.linspace(.01, .99, 768, dtype=np.float64), (13, 1))
        self.encode_calls = self.snapshot_calls = 0

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


def benchmark(mib=64, tensors=8, iterations=3, layout='contiguous'):
    validate(mib, tensors, iterations, layout)
    import witness_capture  # Preload the receipt helper before timed observations.
    enc = SyntheticEncoder(mib, tensors, layout)
    texts = [f'synthetic feature {i}' for i in range(13)]
    timings = {name: [] for name in ('bare_stub', 'first_observed_call', 'repeat_without_snapshot')}
    for _ in range(iterations):
        wrapped = FeatureEncoder(enc)
        for name, call in (('bare_stub', lambda: enc.encode(texts, show_progress_bar=False)),
                           ('first_observed_call', lambda: wrapped.encode(texts, show_progress_bar=False)),
                           ('repeat_without_snapshot', lambda: wrapped.encode(texts, show_progress_bar=False))):
            value, elapsed = measure(call)
            if value is not enc.output: raise RuntimeError('observer changed the return object')
            timings[name].append(elapsed)
            if name == 'first_observed_call':
                if len(wrapped.records) != len(texts): raise RuntimeError('missing synthetic observations')
                for record in wrapped.records.values():
                    obs = record['call']
                    if (obs['parameter_state'] != 'observed_equal'
                            or obs['parameter_before']['bytes'] != mib*1024*1024
                            or obs['parameter_before']['tensors'] != tensors):
                        raise RuntimeError('synthetic snapshot unavailable or inconsistent')
    if enc.encode_calls != iterations*3 or enc.snapshot_calls != iterations*2:
        raise RuntimeError('unexpected encode or snapshot call count')
    return {'schema': 'judges-encoder-cost-v1', 'input_kind': 'synthetic_cpu_arrays',
            'logical_parameter_bytes': mib*1024*1024,
            'allocated_parameter_array_bytes': sum(b.nbytes for b in enc.buffers),
            'layout': layout, 'tensors': tensors, 'iterations': iterations,
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
    args = p.parse_args()
    validate(args.mib, args.tensors, args.iterations, args.layout)
    root = replay.scratch_root(args.scratch)
    output = replay.inside(root, args.output)
    if output.exists(): raise ValueError('benchmark output already exists')
    replay.install_guard(root, output)
    result = benchmark(args.mib, args.tensors, args.iterations, args.layout)
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
