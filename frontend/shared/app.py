"""Single-window entry point; independent Step 1/2 programs remain available."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from unified_ui import UnifiedApp
import tkinter as tk


def main():
    parser=argparse.ArgumentParser(description='EmoBlocks single-window studio')
    parser.add_argument('--structure',help='Open a structure or studio project in the same window')
    args=parser.parse_args()
    import ui_platform
    root=ui_platform.create_root()
    app=UnifiedApp(root)
    if args.structure:app.safe(lambda:app.load_project(args.structure))
    root.mainloop()


if __name__=='__main__':main()
