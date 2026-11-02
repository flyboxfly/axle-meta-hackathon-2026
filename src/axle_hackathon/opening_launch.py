"""Dedicated real opening-test launcher entry. Never import-starts a listener."""
from .pilot_launch import main_real

if __name__ == '__main__':
    raise SystemExit(main_real())
