"""Download and verify the two archives used for the framebuffer timedemo."""

import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen
import zipfile

COMMIT = "e52885ff8a4cba99586c33b09339a9a56a69c041"
VERSION = "0.13.0"
SOURCE = f"fbDOOM-{COMMIT}.tar.gz"
DATA = f"freedoom-{VERSION}.zip"
SOURCE_SHA = "216901bd4afeb0d37fd0100e986c909d8b4300d9c4eb9feeabe569b1e8b0551e"
DATA_SHA = "3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59"


def verify(path, digest):
    with path.open("rb") as src:
        if hashlib.file_digest(src, "sha256").hexdigest() != digest:
            raise ValueError(f"SHA-256 mismatch for {path.name}")


def fetch(directory, name, url, digest):
    path = directory / name
    if path.exists():
        verify(path, digest)
        return
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        download = Path(tmp) / name
        with urlopen(url, timeout=90) as response, download.open("wb") as out:
            shutil.copyfileobj(response, out)
        verify(download, digest)
        download.replace(path)


DATA_URL = f"https://github.com/freedoom/freedoom/releases/download/v{VERSION}/{DATA}"


def wad(directory):
    """Fetch and verify only the Freedoom archive and extract freedoom1.wad (doom.py --play)."""
    directory.mkdir(parents=True, exist_ok=True)
    fetch(directory, DATA, DATA_URL, DATA_SHA)
    with zipfile.ZipFile(directory / DATA) as archive:
        with archive.open(f"freedoom-{VERSION}/freedoom1.wad") as src:
            with (directory / "freedoom1.wad").open("wb") as out:
                shutil.copyfileobj(src, out)
    return directory / "freedoom1.wad"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    directory = parser.parse_args().directory
    directory.mkdir(parents=True, exist_ok=True)
    fetch(directory, SOURCE, f"https://codeload.github.com/maximevince/fbDOOM/tar.gz/{COMMIT}", SOURCE_SHA)
    wad(directory)


if __name__ == "__main__":
    main()
