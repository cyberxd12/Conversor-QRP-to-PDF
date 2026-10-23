"""
Ponto de entrada principal do Conversor QRP para PDF Desktop.
Executa a interface gráfica CustomTkinter.
"""

import sys
import os

# Garante que o diretório atual esteja no sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from gui import main

if __name__ == "__main__":
    main()
