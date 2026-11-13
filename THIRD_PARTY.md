# Dependências e protocolo

O ícone usa o traçado Activity de Lucide, com fundo e cores adaptados. A licença
ISC/MIT do projeto acompanha `src/kardiaos/assets/LUCIDE-LICENSE`.
Fonte: https://github.com/lucide-icons/lucide/blob/main/icons/activity.svg

O protocolo de interoperabilidade M2 foi implementado a partir das evidências de
ShaneBreazeale/kardia-rs, disponível sob MIT ou Apache-2.0:
https://github.com/ShaneBreazeale/kardia-rs

As dependências são distribuídas sem modificações. Seus avisos de licença estão
em `licenses` na distribuição. Qt/PySide6 é usado sob LGPLv3; DLLs permanecem
separadas e podem ser substituídas por versões compatíveis. O código-fonte do
KardiaOS e as instruções para reconstruir o executável acompanham a distribuição.
Não se impõem restrições adicionais à modificação ou à engenharia reversa para
depuração dessas modificações.

Fontes das dependências:

- Qt/PySide6: https://code.qt.io/cgit/pyside/pyside-setup.git/ e https://code.qt.io/
- NumPy: https://github.com/numpy/numpy
- SciPy: https://github.com/scipy/scipy
- Bleak: https://github.com/hbldh/bleak
- ReportLab: https://hg.reportlab.com/hg-public/reportlab/
- Python: https://www.python.org/downloads/source/
- PyInstaller: https://github.com/pyinstaller/pyinstaller

KardiaMobile e AliveCor são marcas de seus respectivos titulares. KardiaOS não
é afiliado nem endossado por esses fabricantes.
