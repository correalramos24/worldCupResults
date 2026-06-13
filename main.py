import pandas as pd
from jinja2 import Template
import os
from dotenv import load_dotenv


def main():
    load_dotenv()
    URL = os.environ["SHEET_URL"]

    df = pd.read_csv(URL, dtype=str)
    participants = list(df.columns[4:])
    print(f"Found {len(participants)} participants: {participants}")

    df.iloc[:, 3:] = df.iloc[:, 3:].apply(lambda col: col.str.lower())

    hits = df[participants].eq(df["RESULTAT"], axis=0)
    results = hits.sum().sort_values(ascending=False)
    results = results.sort_values(ascending=False).to_dict()

    matches = []
    for _, row in df.iterrows():
        resultat = row.iloc[3]
        is_empty = resultat in ("nan", "", "none", None)
        match = {
            "data": row.iloc[0],
            "local": row.iloc[1],
            "visitante": row.iloc[2],
            "resultat": resultat if resultat not in ("nan", "none") else "",
            "apuestas": {}
        }
        for p in participants:
            match["apuestas"][p] = {
                "bet": row[p],
                "hit": not is_empty and row[p] == resultat
            }
        matches.append(match)

    template = Template(open("template.html", encoding="utf-8").read())
    html = template.render(ranking=results, matches=matches)
    os.makedirs('dist', exist_ok=True)
    with open("dist/index.html", mode="w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
