# Research results and figures

The workspace contains one distinct X research chart, embedded in cell 7 of the historical notebook and as an image in an unpublished Word report. It compares monthly Counts API values for the exact English, non-retweet `#cancel` and `#boycott` queries from January 2015 through December 2025. The two embeddings have identical decoded pixels.

The plotting code reads the original `#hashtag_year_month` monthly tables. Those tables differ from the trend directory's daily-derived aggregates. The input versions are preserved separately, and the cause of their differences remains unresolved. The code's outer join and zero fill also require coverage review before interpreting the chart.

The portfolio includes the original notebook PNG and the two reviewed monthly tables. Both input series contain the same 132 months, so the original outer join does not create missing values for these files. [Original PNG](figures/monthly_hashtag_trends_2015_2025.png) · [Input provenance](../data/README.md) · [Analysis case study](../docs/analysis_case_study.md)

From the repository root, with the dependencies installed, regenerate the plot offline:

```bash
MPLBACKEND=Agg python -m src.visualization.monthly_trends \
  --boycott data/historical/x_boycott_monthly_counts_2015_2025.csv \
  --cancel data/historical/x_cancel_monthly_counts_2015_2025.csv \
  --output results/figures/reproduced_monthly_trends.png \
  --title "Monthly Frequency Trend: Boycott vs Cancel (2015–2025)"
```

The regenerated figure uses the same data and plotting method. Its rendering may differ with Matplotlib version and font settings. The generated filename is ignored by Git. [Plot implementation](../src/visualization/monthly_trends.py)
