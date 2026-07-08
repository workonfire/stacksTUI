from stacksTUI.main import main
from sys import exit

if __name__ == '__main__':
    try:
        exit(main())
    except KeyboardInterrupt:
        pass
