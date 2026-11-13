"""Copy installed dependency notices into the distributable, without user data."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
destination = root / 'build' / 'licenses'
destination.mkdir(parents=True, exist_ok=True)
for distribution in distributions():
    name = distribution.metadata['Name']
    if name.lower() == 'kardiaos':
        continue
    for item in distribution.files or []:
        if any(token in item.name.lower() for token in ('license', 'copying', 'copyright', 'notice')) and not item.name.endswith(('.py', '.pyc', '.pyd', '.dll')):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                target = destination / name / str(item).replace('..', '_').replace('/', '_').replace('\\', '_')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
print('Avisos de dependências coletados.')
