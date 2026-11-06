"""Resumo verificável do CSV; outliers são categorias com frequência atípica."""

import json
import re

import pandas as pd


def parse_summary(text):
    """Extract the answer JSON from a stream that can include tool narration."""
    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        return json.loads(fenced[-1])
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The agent returned no JSON summary")
    return json.loads(text[start:end + 1])


def summarize(frame):
    columns = {}
    for column in frame.columns:
        counts = frame[column].value_counts()
        q1, q3 = counts.quantile([0.25, 0.75])
        lower, upper = float(q1 - 1.5 * (q3 - q1)), float(q3 + 1.5 * (q3 - q1))
        outliers = counts[(counts < lower) | (counts > upper)].sort_index()
        columns[column] = {
            "unique": int(counts.size),
            "lower_bound": lower,
            "upper_bound": upper,
            "outliers": {str(name): int(count) for name, count in outliers.items()},
        }
    return {
        "rows": int(len(frame)),
        "missing": int(frame.isna().sum().sum()),
        "outlier_unit": "category_frequency",
        "outlier_categories": sum(len(value["outliers"]) for value in columns.values()),
        "columns": columns,
    }


if __name__ == "__main__":
    print(json.dumps(summarize(pd.read_csv("data.csv")), sort_keys=True))
