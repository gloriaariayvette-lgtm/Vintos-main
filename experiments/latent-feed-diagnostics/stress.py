#!/usr/bin/env python3
"""Run the synthetic latent-feed suite in fresh workers; capture reproducible order."""
import argparse
import importlib.util
import json
import locale
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
ZONES=('UTC','America/Chicago','Europe/London','Pacific/Auckland','Asia/Tokyo')


def worker(seed,zone,locale_name):
    sys.path.insert(0,str(ROOT/'broker/tests'))
    spec=importlib.util.spec_from_file_location('latent_stress_suite',ROOT/'broker/tests/test_latent_feed.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    locale.setlocale(locale.LC_ALL,locale_name)
    setup=module.Tests.setUp
    def varied_setup(test):
        os.environ['TZ']=zone;time.tzset();setup(test)
    module.Tests.setUp=varied_setup
    names=unittest.defaultTestLoader.getTestCaseNames(module.Tests)
    random.Random(seed).shuffle(names)
    print(json.dumps({'seed':seed,'timezone':zone,'locale':locale_name,'order':names}),flush=True)
    try:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(module.Tests(name) for name in names))
        return 0 if result.wasSuccessful() else 1
    finally:
        shutil.rmtree(module.ROOT)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--seed',type=int,default=20261109)
    parser.add_argument('--timezone',choices=ZONES,default='UTC');parser.add_argument('--locale',default='C')
    args=parser.parse_args()
    if args.worker:return worker(args.seed,args.timezone,args.locale)
    # This driver is intended to run through scripts/run_isolated_test.py. Each
    # worker already uses scratch paths and stubbed providers/senders in the suite.
    previous=locale.setlocale(locale.LC_ALL);locales=[]
    for candidate in ('C','en_US.UTF-8','C.UTF-8','en_GB.UTF-8'):
        try:locale.setlocale(locale.LC_ALL,candidate);locales.append(candidate)
        except locale.Error:pass
    locale.setlocale(locale.LC_ALL,previous)
    started=time.monotonic()
    for i in range(50):
        zone=ZONES[i%len(ZONES)];loc=locales[(i//len(ZONES))%len(locales)];seed=args.seed+i
        result=subprocess.run([sys.executable,__file__,'--worker','--seed',str(seed),'--timezone',zone,'--locale',loc],
                              capture_output=True,text=True,timeout=120)
        if result.returncode:
            print(json.dumps({'status':'first_failure','iteration':i+1,'seed':seed,'timezone':zone,'locale':loc,
                              'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-started,3)}),flush=True)
            print(result.stdout);print(result.stderr,file=sys.stderr)
            return result.returncode
        print(json.dumps({'iteration':i+1,'tests':15,'seed':seed,'timezone':zone,'locale':loc,'status':'pass'}),flush=True)
    print(json.dumps({'status':'passed','iterations':50,'tests':750,'timezones':list(ZONES),'locales':locales,
                      'elapsed_seconds':round(time.monotonic()-started,3)}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
