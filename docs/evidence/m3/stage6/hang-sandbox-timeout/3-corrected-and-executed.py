import json, os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv(os.environ["DATA_PATH"], parse_dates=["order_date"])
df["revenue"] = df["units"] * df["unit_price"] * (1 - df["discount"])
df["month"] = df["order_date"].dt.strftime("%Y-%m")
by_cat = df.pivot_table(index="category", columns="month", values="revenue", aggfunc="sum")
change = (by_cat["2026-09"] - by_cat["2026-08"]).sort_values()
cat = change.index[0]
by_reg = df[df["category"] == cat].pivot_table(
    index="region", columns="month", values="revenue", aggfunc="sum"
)
reg = (by_reg["2026-09"] - by_reg["2026-08"]).sort_values()
print(f"biggest_drop_category={cat} change={change.iloc[0]:.2f}")
print(f"worst_region={reg.index[0]} change={reg.iloc[0]:.2f}")
fig, ax = plt.subplots()
change.plot.barh(ax=ax, title="Revenue change, Aug to Sep, by category")
ax.set_xlabel("Revenue change (INR)")
ax.set_ylabel("Category")
fig.savefig(os.environ["OUTPUT_DIR"] + "/category_change.png", metadata={"Software": None})
facts = [
    {"label": "biggest_drop_category", "value": str(cat), "unit": ""},
    {"label": "biggest_drop_amount", "value": round(float(change.iloc[0]), 2), "unit": "INR"},
    {"label": "worst_region", "value": str(reg.index[0]), "unit": ""},
    {"label": "worst_region_change", "value": round(float(reg.iloc[0]), 2), "unit": "INR"},
]
charts = [{"file": "category_change.png", "title": "Revenue change, Aug to Sep, by category",
           "x_label": "Revenue change (INR)", "y_label": "Category", "unit": "INR"}]
json.dump({"answer_facts": facts, "charts": charts}, open(os.environ["OUTPUT_DIR"] + "/results.json", "w"))

