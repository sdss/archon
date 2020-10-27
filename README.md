# archon

![Versions](https://img.shields.io/badge/python->3.7-blue)
[![Documentation Status](https://readthedocs.org/projects/sdss-archon/badge/?version=latest)](https://sdss-archon.readthedocs.io/en/latest/?badge=latest)
[![Build](https://img.shields.io/github/workflow/status/sdss/archon/Test)](https://github.com/sdss/archon/actions)
[![codecov](https://codecov.io/gh/sdss/archon/branch/master/graph/badge.svg)](https://codecov.io/gh/sdss/archon)


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
