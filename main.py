import pandas as pd
from jinja2 import Template
import os
from dotenv import load_dotenv
from fifa_api import get_match, show_all


def main():
    load_dotenv()
    URL = os.environ["SHEET_URL"]

    print("=== Partidos en FIFA API ===")
    show_all()

    df = pd.read_csv(URL, dtype=str)
    participants = list(df.columns[3:])
    print(f"\nFound {len(participants)} participants: {participants}")

    df.iloc[:, 3:] = df.iloc[:, 3:].apply(lambda col: col.str.lower())

    fifa_results = {}
    for _, row in df.iterrows():
        m = get_match(row.iloc[1], row.iloc[2])
        if m and m["result"]:
            fifa_results[(row.iloc[1], row.iloc[2])] = m["result"]

    print(f"FIFA results available: {len(fifa_results)} matches\n")

    ranking = {p: 0 for p in participants}
    for _, row in df.iterrows():
        result = fifa_results.get((row.iloc[1], row.iloc[2]))
        if result:
            for p in participants:
                if row[p] == result:
                    ranking[p] += 1

    ranking = dict(sorted(ranking.items(), key=lambda x: -x[1]))

    matches = []
    for _, row in df.iterrows():
        result = fifa_results.get((row.iloc[1], row.iloc[2]), "")
        is_empty = not result
        match = {
            "data": row.iloc[0],
            "local": row.iloc[1],
            "visitante": row.iloc[2],
            "resultat": result,
            "apuestas": {}
        }
        for p in participants:
            match["apuestas"][p] = {
                "bet": row[p],
                "hit": not is_empty and row[p] == result
            }
        matches.append(match)

    template = Template(open("template.html", encoding="utf-8").read())
    html = template.render(ranking=ranking, matches=matches)
    os.makedirs('dist', exist_ok=True)
    with open("dist/index.html", mode="w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
