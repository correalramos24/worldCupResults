from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from jinja2 import Template
import os
from dotenv import load_dotenv
from fifa_api import get_match, show_all


def _format_date(date_str: str) -> str:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        dt_es = dt.astimezone(ZoneInfo("Europe/Madrid"))
        return dt_es.strftime("%d/%m/%Y @ %H:%M")
    except Exception:
        return date_str


def main():
    load_dotenv()
    URL = os.environ["SHEET_URL"]

    print("=== Partidos en FIFA API ===")
    show_all()

    df = pd.read_csv(URL, dtype=str)
    participants = list(df.columns[3:])
    print(f"\nFound {len(participants)} participants: {participants}")

    df.iloc[:, 3:] = df.iloc[:, 3:].apply(lambda col: col.str.lower())

    fifa_matches = {}
    for _, row in df.iterrows():
        m = get_match(row.iloc[1], row.iloc[2])
        if m:
            fifa_matches[(row.iloc[1], row.iloc[2])] = m

    print(f"FIFA results available: {len(fifa_matches)} matches\n")

    ranking = {p: {"aciertos": 0, "rating": 0.0} for p in participants}

    for _, row in df.iterrows():
        m = fifa_matches.get((row.iloc[1], row.iloc[2]))
        if m and m["result"]:
            result = m["result"]
            outcome_counts = {"1": 0, "2": 0, "x": 0}
            valid_predictions = 0
            for p in participants:
                bet = row[p]
                if bet in outcome_counts:
                    outcome_counts[bet] += 1
                    valid_predictions += 1

            for p in participants:
                if row[p] == result:
                    ranking[p]["aciertos"] += 1
                    if valid_predictions > 0 and outcome_counts[result] > 0:
                        ranking[p]["rating"] += valid_predictions / outcome_counts[result]

    ranking = dict(
        sorted(ranking.items(), key=lambda x: (-x[1]["aciertos"], -x[1]["rating"]))
    )

    matches = []
    for _, row in df.iterrows():
        m = fifa_matches.get((row.iloc[1], row.iloc[2]))
        result = m["result"] if m else ""
        is_empty = not result

        rating_value = 0.0
        if not is_empty:
            outcome_counts = {"1": 0, "2": 0, "x": 0}
            valid_predictions = 0
            for p in participants:
                bet = row[p]
                if bet in outcome_counts:
                    outcome_counts[bet] += 1
                    valid_predictions += 1
            if valid_predictions > 0 and outcome_counts[result] > 0:
                rating_value = valid_predictions / outcome_counts[result]

        match = {
            "data": _format_date(m["date"]) if m else row.iloc[0],
            "local": row.iloc[1],
            "visitante": row.iloc[2],
            "resultat": result,
            "rating_value": rating_value,
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
