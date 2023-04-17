set -e

coverage erase

coverage run --append -m odmpy --version
coverage run --append -m unittest -v tests
