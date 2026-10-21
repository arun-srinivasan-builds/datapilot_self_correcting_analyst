"""Premium native charts (Plotly) drawn from the series the agents saved in results.json.

Data in, figure out. The numbers are exactly the agent's `charts[i].data`; nothing is recomputed.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

INK, MUTED, GRID = "#14202b", "#5b6773", "#e4e8ec"
TEAL, RED, AMBER, INDIGO, ROSE, SLATE = (
    "#0b7f8a",
    "#c7402f",
    "#d19a1f",
    "#4f5bd5",
    "#d4577a",
    "#6b7886",
)
PALETTE = (TEAL, AMBER, INDIGO, ROSE, SLATE, "#1f8a5b")
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"
MINUS = "−"


def compact(value: float) -> str:
    """1 234 567 -> 1.23M, -3 980 400 -> −3.98M, 950 -> 950."""
    sign = MINUS if value < 0 else ""
    v = abs(value)
    if v >= 1e9:
        text = f"{v / 1e9:.2f}B"
    elif v >= 1e6:
        text = f"{v / 1e6:.2f}M"
    elif v >= 1e4:
        text = f"{v / 1e3:.1f}K"
    elif float(v).is_integer():
        text = f"{v:,.0f}"
    else:
        text = f"{v:,.2f}"
    return sign + text


def has_data(chart: dict[str, Any]) -> bool:
    data = chart.get("data")
    return isinstance(data, dict) and bool(data.get("categories")) and bool(data.get("series"))


def takeaway(chart: dict[str, Any]) -> str:
    """One plain sentence derived only from the plotted numbers."""
    data = chart["data"]
    cats, series = data["categories"], data["series"]
    if len(series) != 1:
        return ""
    values = series[0]["values"]
    if any(v < 0 for v in values) and any(v >= 0 for v in values):
        low = min(range(len(values)), key=lambda i: values[i])
        return f"Biggest fall: {cats[low]} ({compact(values[low])})."
    top = max(range(len(values)), key=lambda i: abs(values[i]))
    return f"Largest: {cats[top]} ({compact(values[top])})."


def build_figure(chart: dict[str, Any]) -> go.Figure:
    data = chart["data"]
    cats: list[str] = [str(c) for c in data["categories"]]
    series: list[dict[str, Any]] = data["series"]
    horizontal = len(cats) > 5 or max(len(c) for c in cats) > 14
    fig = go.Figure()
    if len(series) == 1:
        values = [float(v) for v in series[0]["values"]]
        diverging = any(v < 0 for v in values) and any(v >= 0 for v in values)
        extreme = min(range(len(values)), key=lambda i: values[i]) if diverging else None
        colors = [(RED if v < 0 else TEAL) if diverging else TEAL for v in values]
        opacity = [1.0 if (extreme is None or i == extreme) else 0.55 for i in range(len(values))]
        fig.add_bar(
            x=values if horizontal else cats,
            y=cats if horizontal else values,
            orientation="h" if horizontal else "v",
            marker={"color": colors, "opacity": opacity, "cornerradius": 6},
            text=[compact(v) for v in values],
            textposition="outside",
            cliponaxis=False,
            textfont={"size": 12, "color": INK},
            customdata=[f"{v:,.2f}" for v in values],
            hovertemplate="<b>%{"
            + ("y" if horizontal else "x")
            + "}</b><br>%{customdata}<extra></extra>",
            name=series[0]["name"],
        )
        fig.update_layout(showlegend=False)
    else:
        for i, s in enumerate(series):
            values = [float(v) for v in s["values"]]
            fig.add_bar(
                x=values if horizontal else cats,
                y=cats if horizontal else values,
                orientation="h" if horizontal else "v",
                name=str(s["name"]),
                marker={"color": PALETTE[i % len(PALETTE)], "cornerradius": 6},
                customdata=[f"{v:,.2f}" for v in values],
                hovertemplate="<b>"
                + str(s["name"]).replace("<", "")
                + "</b><br>%{"
                + ("y" if horizontal else "x")
                + "}: %{customdata}<extra></extra>",
            )
        fig.update_layout(
            barmode="group",
            legend={"orientation": "h", "y": 1.12, "x": 0, "font": {"size": 13, "color": INK}},
        )
    value_axis = {
        "showgrid": True, "gridcolor": GRID, "zeroline": True, "zerolinecolor": "#9aa5b1",
        "zerolinewidth": 1.5, "tickfont": {"size": 12, "color": MUTED}, "tickformat": "~s",
        "fixedrange": True,
    }  # fmt: skip
    cat_axis = {
        "showgrid": False, "tickfont": {"size": 12, "color": INK}, "automargin": True,
        "fixedrange": True,
    }  # fmt: skip
    if horizontal:
        fig.update_xaxes(**value_axis)
        fig.update_yaxes(**cat_axis, autorange="reversed")
    else:
        fig.update_yaxes(**value_axis)
        fig.update_xaxes(**cat_axis)
    height = max(340, 30 * len(cats) + 120) if horizontal else 380
    fig.update_layout(
        height=min(height, 760),
        margin={"l": 8, "r": 56 if horizontal else 12, "t": 36, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": INK},
        bargap=0.32,
        bargroupgap=0.06,
        hoverlabel={
            "bgcolor": "#ffffff",
            "bordercolor": GRID,
            "font": {"family": FONT, "size": 13, "color": INK},
        },
    )
    return fig
