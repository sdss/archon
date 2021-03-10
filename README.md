# archon

![Versions](https://img.shields.io/badge/python->3.8-blue)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Documentation Status](https://readthedocs.org/projects/sdss-archon/badge/?version=latest)](https://sdss-archon.readthedocs.io/en/latest/?badge=latest)
[![Test](https://github.com/sdss/archon/actions/workflows/test.yml/badge.svg)](https://github.com/sdss/archon/actions/workflows/test.yml)
[![Docker](https://github.com/sdss/archon/actions/workflows/docker.yml/badge.svg)](https://github.com/sdss/archon/actions/workflows/docker.yml)
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


## Docker

The actor can run as a Docker container; new images for ``main`` (pointing to tag ``latest``) and tags are created via a GitHub Action. The images are stored in the GitHub Container Registry. To pull the latest image run

```console
docker pull ghcr.io/sdss/archon:latest
```

To run a container

```console
docker run --name archon --rm --detach --network host ghcr.io/sdss/archon:latest
```

This assumes that RabbitMQ is running on the default port in the host computer and that the Archon controller are accessible over the host network.


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

### Style and type checking

This project uses the [black](https://github.com/psf/black) code style with 88-character line lengths for code and docstrings. It is recommended that you run `black` on save. Imports must be sorted using [isort](https://pycqa.github.io/isort/). The GitHub test workflow checks all the Python file to make sure they comply with the black formatting.

Configuration files for [flake8](https://flake8.pycqa.org/en/latest/), [isort](https://pycqa.github.io/isort/), and [black](https://github.com/psf/black) are provided and will be applied by most editors. For Visual Studio Code, the following project file is compatible with the project configuration:

```json
{
    "python.formatting.provider": "black",
    "[python]" : {
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        },
        "editor.formatOnSave": true
    },
    "[markdown]": {
        "editor.wordWrapColumn": 88
    },
    "[restructuredtext]": {
        "editor.wordWrapColumn": 88
    },
    "editor.rulers": [88],
    "editor.wordWrapColumn": 88,
    "python.analysis.typeCheckingMode": "basic"
}
```

This assumes that the [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) and [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance) extensions are installed.

This project uses [type hints](https://docs.python.org/3/library/typing.html). Typing is enforced by the test workflow using [pyright](https://github.com/microsoft/pyright) (in practice this means that if ``Pylance`` doesn't produce any errors in basic mode, ``pyright`` shouldn't).
