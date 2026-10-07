"""Run the UI-v2 tests against the separated source tree."""
import argparse
import ast
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from emoblocks_bootstrap import configure
parser=argparse.ArgumentParser();parser.add_argument('--backend-only',action='store_true')
parser.add_argument('--platform',choices=('windows','macos'),help='Select adapters; does not emulate that OS')
args=parser.parse_args()
configure(args.platform)
TEST_FOLDERS = ('core','step1','step2','platform','ui')
for folder in TEST_FOLDERS:
    sys.path.insert(0,str(ROOT/'tests'/folder))
from runtime_config import ASSETS
suite=unittest.TestSuite();loader=unittest.TestLoader()
for folder in TEST_FOLDERS:
    if args.backend_only and folder == 'ui':
        continue
    for path in sorted((ROOT/'tests'/folder).glob('test_*.py')):
        if args.backend_only:
            tree=ast.parse(path.read_text(encoding='utf-8-sig'))
            names={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
            names.update(a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names)
            if names.intersection({'tkinter','unified_ui','story_ui'}):continue
        suite.addTests(loader.loadTestsFromName(path.stem))
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
