"""Historical single-page recent-search pilot; no pagination or completeness claim.

Preserves the original query and February 2026 window. That fixed window is
historical and is not expected to work with a current recent-search endpoint.
"""
import argparse
from pathlib import Path
import tweepy
import csv
import re
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/experiments/balenciaga.csv"))
    parser.add_argument("--allow-live-api", action="store_true")
    args = parser.parse_args()
    if not args.allow_live_api:
        parser.error("Live API access is disabled; explicit --allow-live-api is required.")

    BEARER_TOKEN = os.environ["X_BEARER_TOKEN"]
    client = tweepy.Client(bearer_token=BEARER_TOKEN)

    def clean_text(text):
        text = text.replace('\n', ' ')
        text = re.sub(r'http\S+', '', text)
        text = re.sub(r'@\w+', '', text)
        text = text.strip()
        return text

    # 경로 설정
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file = str(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    f = open(csv_file, 'w', encoding='utf-8-sig', newline='')
    writer = csv.writer(f)
    writer.writerow(['created_at', 'cleaned_text', 'like_count', 'retweet_count'])


    query = "balenciaga (child OR kid OR minor) (BDSM OR abuse OR pedo OR sexualization) OR balenciaga (cancel OR boycott OR evil) -is:retweet lang:en"


    try:
        response = client.search_recent_tweets(
            query=query,
            start_time='2026-02-06T00:00:00Z',
            end_time='2026-02-11T00:00:00Z',
            tweet_fields=['created_at', 'text', 'public_metrics'],
            max_results=10
        )

        if response.data:
            for tweet in response.data:
                cleaned = clean_text(tweet.text)
                writer.writerow([
                    tweet.created_at,
                    cleaned,
                    tweet.public_metrics['like_count'],
                    tweet.public_metrics['retweet_count']
                ])
            print(f"file saved: {csv_file}")
        else:
            print("No posts within 7 days.")

    except Exception as e:
        print(f"error: {e}")

    f.close()

if __name__ == "__main__":
    main()
