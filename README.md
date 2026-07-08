# stacksTUI

A Textual interface for the UNO [stackslib](https://github.com/workonfire/stackslib) card game engine.

### ⚠️ WARNING: WORK IN PROGRESS.

![img.png](img.png)

## Installation

Clone the repository, create a virtual environment, and install the project in editable mode:

```bash
git clone https://github.com/workonfire/stacksTUI.git
cd stacksTUI
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```
## Running

After installation, run the app with:

```bash
stacksTUI
```

You can also run it as a Python module:

```bash
python -m stacksTUI
```

## Multiplayer

Start a local multiplayer server:

```bash
stacksTUI --serve
```

Or use `--help` to discover more options

## Development

For local development without installing the package, use:

```bash
make run
```
