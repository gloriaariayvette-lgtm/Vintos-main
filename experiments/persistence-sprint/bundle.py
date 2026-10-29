"""Self-contained offline capture dependencies; never import a live head to fit it."""
from pathlib import Path
import shutil

# The collector uses only exchange admission and section parsing from these
# modules. Include evidence provenance too: its optional-import fallback must
# not silently change the admission contract in a stripped sealed directory.
SCRIPTS = (
    'latent_stream_model.py', 'latent_stream_linear.py', 'latent_stream_replay.py',
    'latent_feed.py', 'jepa_self_head.py', 'jepa_predictor.py',
    'evidence_view.py', 'evidence_provenance.py', 'her_words.py',
)


def package_code(destination, repo):
    destination, repo = Path(destination), Path(repo)
    exp = destination/'experiments/persistence-sprint'
    exp.mkdir(parents=True)
    for path in (repo/'experiments/persistence-sprint').glob('*.py'):
        shutil.copyfile(path, exp/path.name)
    scripts = destination/'scripts'
    scripts.mkdir()
    for name in SCRIPTS:
        shutil.copyfile(repo/'scripts'/name, scripts/name)
