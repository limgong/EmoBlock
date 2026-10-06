"""Single-window entry point; independent Step 1/2 programs remain available."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import tkinter as tk


def main():
    parser=argparse.ArgumentParser(description='EmoBlocks single-window studio')
    parser.add_argument('--structure',help='Open a structure or studio project in the same window')
    args=parser.parse_args()
    import ui_platform
    from curve_workflow import Controller
    from curve_ui import CurveApplication
    ui_platform.prepare_process()
    controller=Controller()
    error=None
    if args.structure:
        try:controller.load(args.structure)
        except Exception as exc:error=str(exc)
    root=ui_platform.create_root()
    ui_platform.configure_scaling(root)
    app=CurveApplication(root,controller=controller)
    if error:
        from tkinter import messagebox
        root.after(0,lambda:messagebox.showerror('无法打开工程',error,parent=root))
    root.mainloop()


if __name__=='__main__':main()
