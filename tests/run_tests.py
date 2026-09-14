#!/usr/bin/env python3
"""Self-contained runner for the PA-07 tracker suite.

pytest is not installed against /usr/bin/python3 on this machine, so this walks
tests/test_*.py and calls every test_* function itself. The test files are plain
pytest-style functions, so `python3 -m pytest tests/ -q` works unchanged the day
pytest does turn up.

    python3 tests/run_tests.py          # everything
    python3 tests/run_tests.py alert    # only tests whose name contains "alert"
"""
import importlib.util
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def collect():
    for fn in sorted(os.listdir(HERE)):
        if not (fn.startswith("test_") and fn.endswith(".py")):
            continue
        spec = importlib.util.spec_from_file_location(fn[:-3], os.path.join(HERE, fn))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in sorted(vars(mod)):
            if name.startswith("test_") and callable(getattr(mod, name)):
                yield fn[:-3], name, getattr(mod, name)


def main(argv):
    want = argv[0] if argv else ""
    passed, failed, skipped = 0, [], 0
    here = os.getcwd()
    for modname, name, fn in collect():
        if want and want not in name and want not in modname:
            continue
        try:
            fn()
        except support.Skip:
            skipped += 1
            sys.stdout.write("s")
        except Exception:
            failed.append((modname, name, traceback.format_exc()))
            sys.stdout.write("F")
        else:
            passed += 1
            sys.stdout.write(".")
        finally:
            os.chdir(here)
        sys.stdout.flush()
    print("")
    for modname, name, tb in failed:
        print("\n=================== FAILED %s::%s ===================" % (modname, name))
        print(tb.rstrip())
    print("\n%d passed, %d failed%s" % (passed, len(failed), (", %d skipped" % skipped) if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
