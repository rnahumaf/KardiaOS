"""Explicit, local setup for experimental models; never reads ECG captures.

Usage: python scripts/setup_research.py [--existing-python PATH] [--target APP_DIR]
The application itself never downloads or installs anything.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-python', type=Path)
    parser.add_argument('--target', type=Path, help='Application root receiving research-runtime.json')
    parser.add_argument('--model-source', type=Path, help='Use already downloaded, hash-verified checkpoints')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = (args.target or root).resolve()
    target.mkdir(parents=True, exist_ok=True)
    runtime = Path.home() / '.kardiaos-research'
    if args.existing_python:
        python = args.existing_python.resolve()
    else:
        if not (runtime / 'Scripts' / 'python.exe').is_file():
            venv.create(runtime, with_pip=True)
        python = runtime / 'Scripts' / 'python.exe'
        subprocess.run([str(python), '-m', 'pip', 'install', 'torch==2.15.0+cpu', '--index-url',
                        'https://download.pytorch.org/whl/cpu'], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root/'requirements-research-lock.txt')], check=True)
    if not python.is_file():
        raise SystemExit('Python de pesquisa não encontrado.')
    # Resolve the actual interpreter path, including Windows packaged-app filesystem redirection.
    probe = subprocess.check_output([str(python), '-c', 'import os,sys,torch,numpy,scipy,easydict; print(os.path.realpath(sys.executable))'], text=True).strip()
    python = Path(probe)
    models = runtime / 'models'
    models.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((root/'src'/'kardiaos'/'assets'/'research_catalog.json').read_text(encoding='utf-8'))
    for spec in catalog['models'].values():
        dest = models / spec['filename']
        def digest(p):
            with p.open('rb') as f:
                return hashlib.file_digest(f,'sha256').hexdigest()
        if dest.is_file() and digest(dest) == spec['sha256']:
            continue
        if dest.exists():
            raise SystemExit('Arquivo existente difere do checkpoint esperado; nada foi sobrescrito: ' + str(dest))
        incoming = dest.with_suffix(dest.suffix+'.download')
        if incoming.exists():
            raise SystemExit('Download parcial existente; revise antes de tentar novamente: ' + str(incoming))
        if args.model_source:
            source = args.model_source / spec['filename']
            if digest(source) != spec['sha256']:
                raise SystemExit('SHA-256 incorreto na origem local: '+spec['filename'])
            shutil.copyfile(source, incoming)
        else:
            with urllib.request.urlopen(spec['checkpoint_url'], timeout=120) as response, incoming.open('xb') as out:
                shutil.copyfileobj(response, out)
        if digest(incoming) != spec['sha256']:
            raise SystemExit('SHA-256 incorreto; arquivo parcial mantido para investigação, não ativado.')
        incoming.rename(dest)
    cfg = dict(schema=1, python=str(python), models_dir=str(models.resolve()))
    (target/'research-runtime.json').write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
    print('Ambiente local configurado em '+str(target)+'. Execute os testes técnicos antes de analisar capturas.')


if __name__ == '__main__':
    main()
