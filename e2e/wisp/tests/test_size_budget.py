import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import size_budget


class SizeBudget(unittest.TestCase):
    def test_thresholds_and_missing_measurements(self):
        budget = dict.fromkeys(size_budget.FIELDS, 100)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "pc").mkdir()
            sizes = out / "pc/sizes"
            for value, ok, message in [(105, True, ""), (95, True, ""), (106, False, "::error::"),
                                       (94, True, "::notice::"), ("-", False, "::error::"),
                                       (None, False, "::error::")]:
                with self.subTest(value=value):
                    actual = dict(budget, kernel_net_bytes=value)
                    if value is None:
                        del actual["kernel_net_bytes"]
                    sizes.write_text("arch=pc " + " ".join(f"{k}={v}" for k, v in actual.items()))
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(size_budget.check(out, {"pc": budget}), ok)
                    if message:
                        self.assertIn(message, output.getvalue())
                    else:
                        self.assertEqual(output.getvalue(), "")

    def test_framebuffer_measurement_required_when_budgeted(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            arch = out / "sparc32"
            arch.mkdir()
            budget = dict.fromkeys(size_budget.FIELDS, 100)
            values = " ".join(f"{key}=100" for key in budget)
            budget["kernel_fb_bytes"] = 100
            for extra, ok in [("", False), (" kernel_fb_bytes=105", True),
                              (" kernel_fb_bytes=106", False)]:
                with self.subTest(extra=extra), contextlib.redirect_stdout(io.StringIO()):
                    (arch / "sizes").write_text(f"arch=sparc32 {values}{extra}")
                    self.assertEqual(size_budget.check(out, {"sparc32": budget}), ok)
