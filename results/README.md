# Research results and figures

The workspace contains one distinct X research chart, embedded in cell 7 of the historical notebook and as an image in an unpublished Word report. It compares monthly Counts API values for the exact English, non-retweet `#cancel` and `#boycott` queries from January 2015 through December 2025. The two embeddings have identical decoded pixels.

The plotting code reads the original `#hashtag_year_month` monthly tables. Those tables differ from the trend directory's daily-derived aggregates. The input versions are preserved separately, and the cause of their differences remains unresolved. The code's outer join and zero fill also require coverage review before interpreting the chart.

The figure remains local because it displays a derivative of the Counts API series and the applicable X redistribution permission was not established. The verified 2022 collection file audit is available as an aggregate CSV. [Plot implementation](../src/visualization/monthly_trends.py), [collection audit](../data/summary/2022_collection_file_audit.csv), and [policy review](../docs/security_and_sharing.md).
