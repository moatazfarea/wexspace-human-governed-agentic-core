import sys, tempfile, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Mock pytest for tests
class RaisesContext:
    def __init__(self, expected_exc, match=None):
        self.expected_exc = expected_exc
        self.match = match
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.expected_exc}, but nothing was raised")
        if not issubclass(exc_type, self.expected_exc):
            return False
        if self.match and self.match not in str(exc_val):
            raise AssertionError(f"Expected match {self.match!r} in {str(exc_val)!r}")
        return True

class PytestMock:
    @staticmethod
    def raises(exc, match=None):
        return RaisesContext(exc, match)

sys.modules["pytest"] = PytestMock()

import importlib.util
spec = importlib.util.spec_from_file_location("test_core", "tests/test_core.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

tests = [getattr(mod, f) for f in dir(mod) if f.startswith("test_") and callable(getattr(mod, f))]
print(f"Running {len(tests)} deterministic tests...")
passed = 0
for t in tests:
    import inspect
    sig = inspect.signature(t)
    if "tmp_path" in sig.parameters:
        td = tempfile.mkdtemp()
        try:
            t(Path(td))
            print(f"  PASS: {t.__name__}")
            passed += 1
        finally:
            shutil.rmtree(td, ignore_errors=True)
    else:
        t()
        print(f"  PASS: {t.__name__}")
        passed += 1
print(f"RESULT: {passed}/{len(tests)} PASS")
