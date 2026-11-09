"""Monthly line comparison adapted from trend notebook cell 7.

Retains the original outer join and zero-fill behavior. Missing data can look
like zero activity; verify completeness before interpreting any figure.
"""
import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

def plot_monthly_trends(boycott_df, cancel_df, title):
    boycott_df = boycott_df.rename(columns={"monthly_count": "boycott_count"})
    cancel_df = cancel_df.rename(columns={"monthly_count": "cancel_count"})

    merged_df = pd.merge(
        boycott_df,
        cancel_df,
        on="month",
        how="outer"
    )


    merged_df["month"] = pd.to_datetime(merged_df["month"])
    merged_df = merged_df.sort_values("month")


    merged_df[["boycott_count", "cancel_count"]] = merged_df[
        ["boycott_count", "cancel_count"]
    ].fillna(0)


    plt.figure(figsize=(14, 6))

    plt.plot(
        merged_df["month"],
        merged_df["boycott_count"],
        label="Boycott",
        marker="o"
    )

    plt.plot(
        merged_df["month"],
        merged_df["cancel_count"],
        label="Cancel",
        marker="o"
    )

    plt.title(title)
    plt.xlabel("Month")
    plt.ylabel("Monthly Post Count")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    return plt.gcf()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boycott", type=Path, required=True)
    parser.add_argument("--cancel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", required=True, help="Identify dates and whether data are synthetic.")
    args = parser.parse_args()
    figure = plot_monthly_trends(pd.read_csv(args.boycott), pd.read_csv(args.cancel), args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=150)
    plt.close(figure)

if __name__ == "__main__":
    main()
