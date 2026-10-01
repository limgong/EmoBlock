"""Start the appropriate EmoBlocks desktop frontend."""
from emoblocks_bootstrap import configure
if __name__=='__main__':
    configure()
    from app import main
    main()
