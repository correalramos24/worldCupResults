import pandas as pd
from jinja2 import Template
import os
from dotenv import load_dotenv


def main():
    load_dotenv()
    URL = os.environ["SHEET_URL"]

    # 1. Load data & retrive participants
    df = pd.read_csv(URL, dtype=str)
    participants = list(df.columns[4:])
    print(f"Found {len(participants)} participants: {participants}")

    # 2. Clean and check results
    df.iloc[:, 3:] = df.iloc[:, 3:].apply(lambda col: col.str.lower())

    hits = df[participants].eq(df["RESULTAT"], axis=0)
    results = hits.sum().sort_values(ascending=False)
    results = results.sort_values(ascending=False).to_dict()
    print(results)

    # 3. Write results into a webpage for GH Pages:
    # 🧠 render template
    template = Template(open("template.html", encoding="utf-8").read())
    html = template.render(ranking=results)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    

    
if __name__ == "__main__":
    main()
