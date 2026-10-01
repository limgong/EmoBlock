"""Windows entry uses the shared UI and Windows adapters."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from emoblocks_bootstrap import configure
if __name__=='__main__':
    configure('windows')
    from app import main
    main()
