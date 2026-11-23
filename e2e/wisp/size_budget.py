"""Compare the sizes reported by build.sh with the checked-in byte budgets."""

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
FIELDS = ("kernel_bytes", "kernel_t2_bytes", "kernel_net_bytes", "init_bytes")


def check(out, budgets):
    ok = True
    for arch, budget in budgets.items():
        sizes = out / arch / "sizes"
        try:
            values = dict(pair.split("=", 1) for pair in sizes.read_text().split())
            if values["arch"] != arch:
                raise ValueError(f"expected arch={arch}")
            fields = (*FIELDS, "kernel_fb_bytes") if "kernel_fb_bytes" in budget else FIELDS
            for field in fields:
                actual, limit = int(values[field]), budget[field]
                if min(actual, limit) <= 0:
                    raise ValueError(f"invalid {field}")
                message = f"{arch} {field}: {actual} bytes (budget {limit})"
                if actual * 100 > limit * 105:
                    print(f"::error::{message}")
                    ok = False
                elif actual * 100 < limit * 95:
                    print(f"::notice::{message}; consider lowering the budget")
        except (OSError, KeyError, ValueError) as exc:
            print(f"::error::{sizes}: {exc}")
            ok = False
    return ok


if __name__ == "__main__":
    raise SystemExit(not check(HERE / "out", json.loads((HERE / "size-budget.json").read_text())))
