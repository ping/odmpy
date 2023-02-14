# helper script for linting
flake8 setup.py odmpy tests
pylint setup.py odmpy tests
black --check setup.py odmpy tests
mypy --package odmpy --package tests
