"""Entry point: python -m photo_editor."""

import sys
from photo_editor.app import run


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
