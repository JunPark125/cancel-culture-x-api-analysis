"""Original daily-to-monthly/yearly aggregation extracted from the notebook."""
import pandas as pd

def aggregate_counts(frame):
    """Return daily, monthly, yearly tables; caller supplies Counts API rows."""
    daily_df = frame.copy()
    daily_df["start"] = pd.to_datetime(daily_df["start"], utc=True)
    daily_df["end"] = pd.to_datetime(daily_df["end"], utc=True)
    daily_df["tweet_count"] = daily_df["tweet_count"].astype(int)

    daily_df = daily_df.sort_values("start").reset_index(drop=True)

    daily_df["year"] = daily_df["start"].dt.year
    daily_df["month"] = daily_df["start"].dt.strftime("%Y-%m")

    monthly_df = (
        daily_df
        .groupby("month", as_index=False)["tweet_count"]
        .sum()
        .rename(columns={"tweet_count": "monthly_count"})
    )

    yearly_df = (
        daily_df
        .groupby("year", as_index=False)["tweet_count"]
        .sum()
        .rename(columns={"tweet_count": "yearly_count"})
    )


    return daily_df, monthly_df, yearly_df
