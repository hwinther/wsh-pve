"""fetch_media.py, the download and check of the pinned media the workflows keep in the Actions cache, and
the FreeDOS zip's single pin: targets_dos.FREEDOS_ZIP is the only copy, the 3dfx DOS test and the audio
matrix import it (and their images carry it), and the workflows that restore it use one key and path.
Offline: the downloads here are file:// URLs of fake pins, never a real medium. Standard library only:

    cd e2e/sparc && python3 -m unittest -v tests/test_fetch_media.py
"""
import contextlib
import hashlib
import io
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import fetch_media  # noqa: E402
import targets_dos  # noqa: E402

TOP = os.path.abspath(os.path.join(HERE, "..", ".."))
ZIP = "FD14-FloppyEdition.zip"
# The workflows that restore the FreeDOS zip, and media-cache.yml, which keeps main's entry
FREEDOS_WORKFLOWS = ["3dfx-dos.yml", "sparc-lab-dos.yml", "audio-matrix.yml", "media-cache.yml"]


def read(*parts):
    with open(os.path.join(TOP, *parts), encoding="utf-8") as f:
        return f.read()


def fake_pin(directory, content, **override):
    """A medium served from a local file: its file:// URL, size and sha256 (overridable)."""
    src = os.path.join(directory, "source.bin")
    with open(src, "wb") as f:
        f.write(content)
    pin = {"url": pathlib.Path(src).as_uri(), "size": len(content),
           "sha256": hashlib.sha256(content).hexdigest()}
    pin.update(override)
    return src, pin


class FreedosPin(unittest.TestCase):
    def test_lookup_and_key(self):
        self.assertEqual(fetch_media.FREEDOS_ZIP_NAME, ZIP)
        self.assertIs(fetch_media.medium(ZIP), targets_dos.FREEDOS_ZIP)
        self.assertEqual(fetch_media.cache_key(ZIP), "freedos-fd14-floppy-" + targets_dos.FREEDOS_ZIP["sha256"][:16])
        for field in ("url", "size", "sha256", "cache"):
            self.assertIn(field, targets_dos.FREEDOS_ZIP)
        self.assertTrue(targets_dos.FREEDOS_ZIP["url"].startswith("https://"))

    def test_key_of_other_media_is_name_and_sha(self):
        name = "NetBSD-11.1-sparc64.iso"
        med = fetch_media.medium(name)
        self.assertEqual(fetch_media.cache_key(name), f"{name}-{med['sha256'][:16]}")

    def test_main_key(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fetch_media.main(["--key", ZIP]), 0)
        self.assertEqual(out.getvalue().strip(), fetch_media.cache_key(ZIP))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(fetch_media.main(["--key", "no-such-medium.img"]), 2)
            # a floppy image from the zip has a pin but no URL: not downloadable
            self.assertEqual(fetch_media.main(["--key", "freedos14-boot.img"]), 2)
            self.assertEqual(fetch_media.main([tempfile.gettempdir(), "freedos14-boot.img"]), 2)

    def test_single_copy_of_the_pin(self):
        """The zip's sha256 and URL, and the boot floppy's sha256, are only in targets_dos.py."""
        needles = [targets_dos.FREEDOS_ZIP["sha256"], targets_dos.MEDIA["freedos14-boot.img"]["sha256"],
                   "freedos/files/distributions/1.4"]
        found = []
        for base in ("e2e", ".github", "scripts", "docs"):
            for root, dirs, files in os.walk(os.path.join(TOP, base)):
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist")]
                for name in files:
                    path = os.path.join(root, name)
                    if any(os.path.samefile(path, f) for f in (targets_dos.__file__, __file__)) or not name.endswith(
                            (".py", ".sh", ".yml", ".yaml", ".md", ".mdx", "Dockerfile")):
                        continue
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    found += [f"{os.path.relpath(path, TOP)}: {n}" for n in needles if n in text]
        self.assertEqual(found, [], "a second copy of a FreeDOS pin; import targets_dos instead")

    def test_harness_images_carry_the_pin(self):
        """The 3dfx DOS and audio images copy targets_dos.py and fetch_media.py (their build contexts
        send only what the dockerignore lets through)."""
        for d in ("e2e/3dfx/dos", "e2e/audio"):
            ignore = read(d, "Dockerfile.dockerignore").splitlines()
            docker = read(d, "Dockerfile")
            for f in ("e2e/sparc/targets_dos.py", "e2e/sparc/fetch_media.py"):
                self.assertIn("!" + f, ignore, d)
                self.assertIn(f, docker, d)

    def test_workflows_share_key_and_path(self):
        for wf in FREEDOS_WORKFLOWS:
            text = read(".github", "workflows", wf)
            self.assertIn(f"python3 e2e/sparc/fetch_media.py --key {ZIP}", text, wf)
            self.assertIn(f'python3 e2e/sparc/fetch_media.py "$RUNNER_TEMP/freedos" {ZIP}', text, wf)
            blocks = re.findall(r"uses: actions/cache/(restore|save)@[0-9a-f]{40} # v[\d.]+\n"
                                r"\s+with:\n\s+path: (.+)\n\s+key: (.+)", text)
            freedos = [b for b in blocks if "freedos" in b[1] + b[2]]
            self.assertTrue(freedos, wf)
            for _, path, _key in freedos:
                self.assertEqual(path, "${{ runner.temp }}/freedos", wf)
            if wf != "media-cache.yml":
                self.assertEqual(sorted(b[0] for b in freedos), ["restore", "save"], wf)
                self.assertIn("github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
                              " && steps.freedos-cache.outputs.cache-hit != 'true'", text, wf)


class Harnesses(unittest.TestCase):
    """The 3dfx DOS test and the audio matrix find the pin from their place in the repository (the
    images keep the same relative layout)."""

    def test_dos_test_imports_the_pin(self):
        sys.path.insert(0, os.path.join(TOP, "e2e", "3dfx", "dos"))
        try:
            import dos_test
        finally:
            sys.path.pop(0)
        self.assertIs(dos_test.targets_dos, targets_dos)
        self.assertIs(dos_test.FREEDOS_BOOT, targets_dos.MEDIA["freedos14-boot.img"])
        self.assertEqual(dos_test.FREEDOS_BOOT["zip"], "144m/x86BOOT.img")

    def test_audio_matrix_imports_the_pin(self):
        sys.path.insert(0, os.path.join(TOP, "e2e", "audio"))
        try:
            import audio_matrix
        finally:
            sys.path.pop(0)
        self.assertIs(audio_matrix.targets_dos, targets_dos)
        self.assertIs(audio_matrix.FREEDOS_BOOT, targets_dos.MEDIA["freedos14-boot.img"])

    def test_dos_test_given_zip(self):
        """dos_test.freedos_zip with FREEDOS_ZIP: the given file, checked (a fake pin here), and the
        cache directory made for the floppy; a file that isn't the pinned one stops the run."""
        sys.path.insert(0, os.path.join(TOP, "e2e", "3dfx", "dos"))
        try:
            import dos_test
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as d:
            src, pin = fake_pin(d, b"a fake Floppy Edition\n")
            cache = os.path.join(d, "cache")
            with mock.patch.object(fetch_media, "medium", lambda name: pin if name == ZIP else None), \
                    mock.patch.dict(os.environ, {"FREEDOS_ZIP": src}):
                self.assertEqual(dos_test.freedos_zip(cache), src)
                self.assertTrue(os.path.isdir(cache))
                with open(src, "ab") as f:
                    f.write(b"changed")
                with self.assertRaises(SystemExit):
                    dos_test.freedos_zip(cache)


class Fetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.content = b"not FreeDOS, a fake medium\n" * 100

    def tearDown(self):
        self.tmp.cleanup()

    def pin(self, **override):
        src, pin = fake_pin(self.dir, self.content, **override)
        patcher = mock.patch.object(fetch_media, "medium", lambda name: pin if name == "fake.zip" else None)
        patcher.start()
        self.addCleanup(patcher.stop)
        return src, pin

    def test_download_then_keep(self):
        src, pin = self.pin()
        cache = os.path.join(self.dir, "cache")
        path = fetch_media.fetch("fake.zip", cache, attempts=1)
        self.assertEqual(path, os.path.join(cache, "fake.zip"))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), self.content)
        self.assertFalse(os.path.exists(path + ".part"))
        # the pinned file is kept: no download (the source is gone)
        os.unlink(src)
        self.assertEqual(fetch_media.fetch("fake.zip", cache, attempts=1), path)
        self.assertEqual(fetch_media.checked(path, "fake.zip"), path)

    def test_wrong_file_is_replaced(self):
        self.pin()
        cache = os.path.join(self.dir, "cache")
        os.makedirs(cache)
        with open(os.path.join(cache, "fake.zip"), "wb") as f:
            f.write(b"x" * len(self.content))  # right size, wrong content
        with open(fetch_media.fetch("fake.zip", cache, attempts=1), "rb") as f:
            self.assertEqual(f.read(), self.content)

    def test_mismatch_after_download(self):
        self.pin(sha256="0" * 64)
        with self.assertRaises(RuntimeError):
            fetch_media.fetch("fake.zip", os.path.join(self.dir, "cache"), attempts=1)

    def test_given_file_is_checked_not_replaced(self):
        src, _ = self.pin()
        other = os.path.join(self.dir, "other.zip")
        with open(other, "wb") as f:
            f.write(b"something else")
        with self.assertRaises(RuntimeError):
            fetch_media.checked(other, "fake.zip")
        with open(other, "rb") as f:
            self.assertEqual(f.read(), b"something else")
        self.assertEqual(fetch_media.checked(src, "fake.zip"), src)

    def test_download_error_after_last_attempt(self):
        self.pin(url=pathlib.Path(os.path.join(self.dir, "missing.bin")).as_uri())
        with self.assertRaises(OSError):
            fetch_media.fetch("fake.zip", os.path.join(self.dir, "cache"), attempts=1)

    def test_main_fetches(self):
        self.pin()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fetch_media.main([os.path.join(self.dir, "cache"), "fake.zip"]), 0)
        self.assertIn(": ok", out.getvalue())


if __name__ == "__main__":
    unittest.main()
