"""Deterministic fixture generator (seeded). Ground truth is computed with pandas from the files.

    python fixtures/generate.py            # writes into fixtures/

Outputs:
    sales_sample.csv        12,480 rows, PDF-shaped schema (order_date, region, category, product,
                            units, unit_price, discount); designed so September's biggest category
                            drop and its main regional contributor are unambiguous
    sales_alt_schema.csv    3,200 rows, different column names/date format, nulls, duplicates
    multisheet.xlsx         Orders (sample schema) + Returns + Targets
    *.truth.json            ground truth for accuracy tests (never read by the application)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SAMPLE_ROWS = 12_480
ALT_ROWS = 3_200
REGIONS = ["North", "South", "East", "West"]
CATALOG: dict[str, list[tuple[str, int]]] = {
    "Electronics": [
        ("Earbuds X2", 1999),
        ("Smart Speaker", 3499),
        ("Power Bank 20k", 1599),
        ("USB-C Hub", 1299),
    ],
    "Grocery": [
        ("Millet Mix 1kg", 249),
        ("Cold Pressed Oil 1L", 399),
        ("Basmati Rice 5kg", 749),
        ("Green Tea 100g", 199),
    ],
    "Apparel": [
        ("Cotton Tee", 599),
        ("Denim Jacket", 2199),
        ("Running Shorts", 799),
        ("Wool Scarf", 899),
    ],
    "Home": [
        ("LED Lamp", 699),
        ("Steel Bottle", 449),
        ("Bed Sheet Set", 1799),
        ("Storage Box", 549),
    ],
    "Beauty": [
        ("Face Serum", 1199),
        ("Sunscreen SPF50", 549),
        ("Hair Oil", 349),
        ("Lip Balm", 149),
    ],
}
DISCOUNTS = [0.0, 0.05, 0.10, 0.15, 0.20]
FIXED_TIMESTAMP = datetime(2026, 10, 1, 0, 0, 0)  # noqa: DTZ001 - fixed for stable xlsx metadata


def _sales_frame(n: int, seed: int, start: str, end: str, *, september_shock: bool) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    cats = list(CATALOG)
    rows: list[dict[str, object]] = []
    while len(rows) < n:
        batch = n - len(rows)
        d = days[rng.integers(0, len(days), batch)]
        r = rng.choice(REGIONS, batch)
        c = rng.choice(cats, batch)
        p_idx = rng.integers(0, 4, batch)
        u = rng.integers(1, 41, batch)
        disc = rng.choice(DISCOUNTS, batch, p=[0.45, 0.2, 0.15, 0.12, 0.08])
        keep = rng.random(batch)
        for i in range(batch):
            if (
                september_shock
                and d[i].month == 9
                and c[i] == "Electronics"
                and r[i] == "South"
                and keep[i] < 0.60  # Sept Electronics/South loses 60% of its rows
            ):
                continue
            product, price = CATALOG[str(c[i])][int(p_idx[i])]
            rows.append(
                {
                    "order_date": d[i].strftime("%Y-%m-%d"),
                    "region": str(r[i]),
                    "category": str(c[i]),
                    "product": product,
                    "units": int(u[i]),
                    "unit_price": price,
                    "discount": f"{float(disc[i]):.2f}",
                }
            )
    return pd.DataFrame(rows[:n])


def make_sample() -> pd.DataFrame:
    return _sales_frame(SAMPLE_ROWS, 20260903, "2026-06-01", "2026-09-30", september_shock=True)


def make_alt() -> pd.DataFrame:
    rng = np.random.default_rng(7041)
    depts = {"Mobiles": 18000, "Laptops": 52000, "Accessories": 1500, "Appliances": 9500}
    branches = ["Chennai", "Pune", "Jaipur", "Kochi", "Indore"]
    days = pd.date_range("2026-01-01", "2026-06-30", freq="D")
    d = days[rng.integers(0, len(days), ALT_ROWS)]
    dept = rng.choice(list(depts), ALT_ROWS)
    qty = rng.integers(1, 6, ALT_ROWS)
    base = np.array([depts[x] for x in dept])
    net = np.round(base * qty * rng.uniform(0.85, 1.05, ALT_ROWS), 2)
    df = pd.DataFrame(
        {
            "txn_date": [x.strftime("%d-%b-%Y") for x in d],
            "branch": rng.choice(branches, ALT_ROWS),
            "department": dept,
            "item_name": [
                f"{x[:3].upper()}-{int(k):04d}"
                for x, k in zip(dept, rng.integers(1, 400, ALT_ROWS), strict=True)
            ],
            "quantity": qty,
            "net_amount": net,
            "customer_type": rng.choice(
                ["Retail", "Corporate", "Walk-in"], ALT_ROWS, p=[0.6, 0.25, 0.15]
            ),
        }
    )
    null_amt = rng.choice(ALT_ROWS, size=int(ALT_ROWS * 0.02), replace=False)
    null_branch = rng.choice(ALT_ROWS, size=int(ALT_ROWS * 0.01), replace=False)
    df.loc[null_amt, "net_amount"] = np.nan
    df.loc[null_branch, "branch"] = None
    dups = df.iloc[:10].copy()  # 10 exact duplicate rows appended
    return pd.concat([df, dups], ignore_index=True)


def make_multisheet() -> dict[str, pd.DataFrame]:
    orders = _sales_frame(600, 555, "2026-06-01", "2026-09-30", september_shock=False)
    rng = np.random.default_rng(99)
    ret_days = pd.date_range("2026-06-01", "2026-09-30", freq="D")
    returns = pd.DataFrame(
        {
            "return_date": [
                d.strftime("%Y-%m-%d") for d in ret_days[rng.integers(0, len(ret_days), 150)]
            ],
            "region": rng.choice(REGIONS, 150),
            "category": rng.choice(list(CATALOG), 150),
            "units_returned": rng.integers(1, 6, 150),
            "refund_amount": np.round(rng.uniform(100, 6000, 150), 2),
        }
    )
    targets = pd.DataFrame(
        [
            {"region": r, "month": m, "target_revenue": 250_000 + 15_000 * i + 5_000 * j}
            for i, r in enumerate(REGIONS)
            for j, m in enumerate(["2026-06", "2026-07", "2026-08", "2026-09"])
        ]
    )
    return {"Orders": orders, "Returns": returns, "Targets": targets}


def _revenue(df: pd.DataFrame) -> pd.Series:
    return df["units"] * df["unit_price"] * (1 - df["discount"].astype(float))


def sample_truth(df: pd.DataFrame) -> dict[str, object]:
    work = df.assign(month=df["order_date"].str[:7], revenue=_revenue(df))
    by_cat = work.pivot_table(index="category", columns="month", values="revenue", aggfunc="sum")
    drop = (by_cat["2026-09"] - by_cat["2026-08"]).sort_values()
    top_cat = str(drop.index[0])
    sub = work[(work["category"] == top_cat) & work["month"].isin(["2026-08", "2026-09"])]
    by_reg = sub.pivot_table(index="region", columns="month", values="revenue", aggfunc="sum")
    reg_drop = (by_reg["2026-09"] - by_reg["2026-08"]).sort_values()
    return {
        "rows": len(df),
        "total_revenue": round(float(work["revenue"].sum()), 2),
        "monthly_revenue": {
            k: round(float(v), 2) for k, v in work.groupby("month")["revenue"].sum().items()
        },
        "category_change_aug_to_sep": {k: round(float(v), 2) for k, v in drop.items()},
        "biggest_drop_category": top_cat,
        "biggest_drop_amount": round(float(drop.iloc[0]), 2),
        "region_change_for_that_category": {k: round(float(v), 2) for k, v in reg_drop.items()},
        "top_region_for_that_drop": str(reg_drop.index[0]),
    }


def alt_truth(df: pd.DataFrame) -> dict[str, object]:
    work = df.assign(month=pd.to_datetime(df["txn_date"], format="%d-%b-%Y").dt.strftime("%Y-%m"))
    return {
        "rows": len(df),
        "null_net_amount": int(df["net_amount"].isna().sum()),
        "null_branch": int(df["branch"].isna().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_net_amount": round(float(df["net_amount"].sum()), 2),
        "department_totals": {
            k: round(float(v), 2) for k, v in df.groupby("department")["net_amount"].sum().items()
        },
        "monthly_totals": {
            k: round(float(v), 2) for k, v in work.groupby("month")["net_amount"].sum().items()
        },
    }


def generate_all(out_dir: Path = HERE) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sample, alt, sheets = make_sample(), make_alt(), make_multisheet()
    paths = {
        "sample": out_dir / "sales_sample.csv",
        "alt": out_dir / "sales_alt_schema.csv",
        "multisheet": out_dir / "multisheet.xlsx",
        "sample_truth": out_dir / "sales_sample.truth.json",
        "alt_truth": out_dir / "sales_alt_schema.truth.json",
    }
    sample.to_csv(paths["sample"], index=False, lineterminator="\n")
    alt.to_csv(paths["alt"], index=False, lineterminator="\n")
    with pd.ExcelWriter(paths["multisheet"], engine="openpyxl") as xw:
        for name, frame in sheets.items():
            frame.to_excel(xw, sheet_name=name, index=False)
        xw.book.properties.created = FIXED_TIMESTAMP
        xw.book.properties.modified = FIXED_TIMESTAMP
    # Truth is computed from the on-disk files so it matches exactly what ingestion will read.
    s = pd.read_csv(paths["sample"], dtype={"discount": float})
    s["discount"] = s["discount"].astype(float)
    paths["sample_truth"].write_text(json.dumps(sample_truth(s), indent=2) + "\n", encoding="utf-8")
    a = pd.read_csv(paths["alt"])
    paths["alt_truth"].write_text(json.dumps(alt_truth(a), indent=2) + "\n", encoding="utf-8")
    return paths


if __name__ == "__main__":
    for key, path in generate_all().items():
        print(f"{key}: {path}")  # noqa: T201 - CLI script output
