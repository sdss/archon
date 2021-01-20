# archon

![Versions](https://img.shields.io/badge/python->3.8-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Documentation Status](https://readthedocs.org/projects/sdss-archon/badge/?version=latest)](https://sdss-archon.readthedocs.io/en/latest/?badge=latest)
[![Build](https://img.shields.io/github/workflow/status/sdss/archon/Test)](https://github.com/sdss/archon/actions)
[![codecov](https://codecov.io/gh/sdss/archon/branch/main/graph/badge.svg)](https://codecov.io/gh/sdss/archon)


A library and actor to communicate with an STA Archon controller.


## Installation

In general you should be able to install ``archon`` by doing

```console
pip install sdss-archon
```

To build from source, use

```console
git clone git@github.com:sdss/archon
cd archon
pip install .
```

## Development

`archon` uses [poetry](http://poetry.eustace.io/) for dependency management and packaging. To work with an editable install it's recommended that you setup `poetry` and install `archon` in a virtual environment by doing

```console
poetry install
```

Pip does not support editable installs with PEP-517 yet. That means that running `pip install -e .` will fail because `poetry` doesn't use a `setup.py` file. As a workaround, you can use the `create_setup.py` file to generate a temporary `setup.py` file. To install `archon` in editable mode without `poetry`, do

```console
pip install --pre poetry
python create_setup.py
pip install -e .
```

Note that this will only install the production dependencies, not the development ones. You'll need to install those manually (see `pyproject.toml` `[tool.poetry.dev-dependencies]`).

### Style

This project uses the [black](https://github.com/psf/black) code style with 88-character line lengths. It is recommended that you run `black` on save. The GitHub test workflow checks all the Python file to make sure they comply with the black formatting.
