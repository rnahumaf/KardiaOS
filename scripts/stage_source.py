"""Stage distributable source; never include captures, outputs, runtimes or checkpoints."""
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
destination=root/'dist/KardiaOS/source'
allowed={'.py','.ps1','.md','.toml','.txt','.iss','.svg','.json'}
for directory in ['src/kardiaos','tests','scripts','docs','installer']:
    for path in (root/directory).rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:continue
        if path.suffix not in allowed and 'LICENSE' not in path.name:continue
        target=destination/path.relative_to(root)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
for name in ['pyproject.toml','requirements-lock.txt','requirements-research-lock.txt','requirements-validation.txt','run.py','README.md','LICENSE','THIRD_PARTY.md']:
    shutil.copyfile(root/name,destination/name)
print('Source and license files staged; no clinical inputs or model weights.')
