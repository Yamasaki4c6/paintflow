"""Paintflow Studio 起動スクリプト(PyInstallerのエントリにもなる)
使い方:  python studio_main.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from studio.app import main

if __name__ == "__main__":
    sys.exit(main())
