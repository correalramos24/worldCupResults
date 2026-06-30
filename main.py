from collections import OrderedDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from jinja2 import Template
import os
from dotenv import load_dotenv
from fifa_api import get_match, show_all, fetch_all, fetch_all_raw, _normalize


STAGE_NAMES = {
    "First Stage": "Fase de Grupos",
    "Round of 32": "1/16",
    "Round of 16": "1/8",
    "Quarter-final": "1/4",
    "Semi-final": "Semifinal",
    "Play-off for third place": "3er Puesto",
    "Final": "Final",
}


def _format_date(date_str: str) -> str:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        dt_es = dt.astimezone(ZoneInfo("Europe/Madrid"))
        return dt_es.strftime("%d/%m/%Y @ %H:%M")
    except Exception:
        return date_str


def _compute_jornada(fifa_matches: dict) -> dict:
    """Assign jornada (1-3) to each First Stage match based on date order within its group."""
    group_matches = {}
    for (home, away), m in fifa_matches.items():
        if m.get("stage_name") == "First Stage":
            group = m.get("group_name", "")
            if group not in group_matches:
                group_matches[group] = []
            group_matches[group].append((home, away, m.get("date", "")))

    jornada_map = {}
    for group, items in group_matches.items():
        items.sort(key=lambda x: x[2])
        for i, (home, away, _) in enumerate(items):
            jornada_map[(home, away)] = (i // 2) + 1
    return jornada_map


def main():
    load_dotenv()
    URL = os.environ["SHEET_URL"]

    print("=== Partidos en FIFA API ===")
    show_all()

    df = pd.read_csv(URL, dtype=str)
    participants = list(df.columns[3:])

    # --- Read playoff predictions from sheet 2 (optional) ---
    URL2 = os.environ.get("SHEET_2_URL", "")
    df2 = None
    if URL2:
        try:
            df2 = pd.read_csv(URL2, dtype=str)
            print(f"\nPlayoff predictions sheet found ({len(df2)} rows), columns: {list(df2.columns)}")
            for p in list(df2.columns[3:]):
                if p not in participants:
                    participants.append(p)
        except Exception as e:
            print(f"\nNo playoff predictions sheet: {e}")

    print(f"\nFound {len(participants)} participants: {participants}")

    df.iloc[:, 3:] = df.iloc[:, 3:].apply(lambda col: col.str.lower())
    if df2 is not None:
        df2.iloc[:, 3:] = df2.iloc[:, 3:].apply(lambda col: col.str.lower())

    # --- Read manual results from sheet (optional) ---
    results_lookup = {}
    results_url = URL.replace("gid=0", "gid=1")
    try:
        df_results = pd.read_csv(results_url, dtype=str)
        print(f"\nResults sheet found ({len(df_results)} rows)")
        print(f"Columns: {list(df_results.columns)}")
        for _, r in df_results.iterrows():
            key = (str(r.iloc[0]).strip(), str(r.iloc[1]).strip())
            val = str(r.iloc[2]).strip().lower()
            if val in ("1", "x", "2"):
                results_lookup[key] = val
        print(f"Manual results loaded: {len(results_lookup)} matches\n")
    except Exception as e:
        print(f"\nNo manual results sheet: {e}")
        print("Using FIFA API as only result source\n")

    # --- Build FIFA match lookup for ALL matches ---
    all_home_away = []
    for _, row in df.iterrows():
        all_home_away.append((row.iloc[1], row.iloc[2]))
    if df2 is not None:
        for _, row in df2.iterrows():
            all_home_away.append((row.iloc[1], row.iloc[2]))

    fifa_matches = {}
    for home, away in set((h.strip(), a.strip()) for h, a in all_home_away):
        m = get_match(home, away)
        if m:
            fifa_matches[(home, away)] = m

    print(f"FIFA results available: {len(fifa_matches)} matches\n")

    jornada_map = _compute_jornada(fifa_matches)

    # --- Determine result for a match: manual sheet > FIFA API ---
    def _get_result(home: str, away: str) -> str:
        key = (home.strip(), away.strip())
        if key in results_lookup:
            return results_lookup[key]
        m = fifa_matches.get(key)
        if m:
            return m.get("result", "")
        return ""

    def _get_winner_result(home: str, away: str) -> str:
        """Return '1' if home advances, '2' if away advances, '' otherwise."""
        key = (home.strip(), away.strip())
        m = fifa_matches.get(key)
        if m:
            w = m.get("winner", "")
            if w == "home":
                return "1"
            if w == "away":
                return "2"
        return ""

    ranking = {p: {"aciertos": 0, "rating": 0.0} for p in participants}

    def _score_row(row, participants, result):
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

    for _, row in df.iterrows():
        result = _get_result(row.iloc[1], row.iloc[2])
        if result:
            _score_row(row, participants, result)

    if df2 is not None:
        for _, row in df2.iterrows():
            result = _get_winner_result(row.iloc[1], row.iloc[2])
            if result:
                _score_row(row, participants, result)

    ranking = dict(
        sorted(ranking.items(), key=lambda x: (-x[1]["aciertos"], -x[1]["rating"]))
    )

    def _build_match(row, participants, result, m, jornada=0):
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

        stage_name = m["stage_name"] if m else ""
        group_name = m["group_name"] if m else ""

        match = {
            "date_raw": m["date"] if m else row.iloc[0],
            "data": _format_date(m["date"]) if m else row.iloc[0],
            "local": row.iloc[1],
            "visitante": row.iloc[2],
            "home_score": m["home_score"] if m else None,
            "away_score": m["away_score"] if m else None,
            "resultat": result,
            "rating_value": rating_value,
            "apuestas": {},
            "stage_name": stage_name,
            "group_name": group_name,
            "jornada": jornada,
            "winner": (m.get("winner", "") if stage_name != "First Stage" else "") if m else "",
        }
        for p in participants:
            match["apuestas"][p] = {
                "bet": row[p],
                "hit": not is_empty and row[p] == result
            }
        return match

    matches = []
    for _, row in df.iterrows():
        result = _get_result(row.iloc[1], row.iloc[2])
        m = fifa_matches.get((row.iloc[1].strip(), row.iloc[2].strip()))
        jornada = jornada_map.get((row.iloc[1], row.iloc[2]), 0)
        matches.append(_build_match(row, participants, result, m, jornada))

    if df2 is not None:
        for _, row in df2.iterrows():
            result = _get_winner_result(row.iloc[1], row.iloc[2])
            m = fifa_matches.get((row.iloc[1].strip(), row.iloc[2].strip()))
            matches.append(_build_match(row, participants, result, m, 0))

    stage_groups = OrderedDict()
    for match in matches:
        sn = match["stage_name"]
        j = match["jornada"]
        if sn == "First Stage" and j:
            key = f"Jornada {j}"
        elif sn in STAGE_NAMES:
            key = STAGE_NAMES[sn]
        else:
            key = sn if sn else "Otros"
        if key not in stage_groups:
            stage_groups[key] = []
        stage_groups[key].append(match)

    match_groups = list(stage_groups.items())

    sheet_pairs = set()
    if df2 is not None:
        for _, row in df2.iterrows():
            sheet_pairs.add((_normalize(str(row.iloc[1]).strip()), _normalize(str(row.iloc[2]).strip())))

    bracket_rounds = OrderedDict()
    for m in fetch_all_raw():
        stage_name = m.get("StageName", [{}])[0].get("Description", "") if m.get("StageName") else ""
        if stage_name == "First Stage":
            continue
        round_key = STAGE_NAMES.get(stage_name, stage_name)
        home_obj = m.get("Home")
        away_obj = m.get("Away")
        home = home_obj.get("TeamName", [{}])[0].get("Description", "??") if home_obj else "??"
        away = away_obj.get("TeamName", [{}])[0].get("Description", "??") if away_obj else "??"
        if (home, away) in sheet_pairs or (away, home) in sheet_pairs:
            continue
        hs = home_obj.get("Score") if home_obj else None
        aws = away_obj.get("Score") if away_obj else None
        date = m.get("Date", "")
        winner_id = m.get("Winner")
        home_id = m.get("Home", {}).get("IdTeam") if m.get("Home") else None
        away_id = m.get("Away", {}).get("IdTeam") if m.get("Away") else None
        winner = ""
        if winner_id and home_id == winner_id:
            winner = "home"
        elif winner_id and away_id == winner_id:
            winner = "away"
        result = ""
        if hs is not None and aws is not None:
            try:
                if int(hs) > int(aws):
                    result = "1"
                elif int(hs) < int(aws):
                    result = "2"
                else:
                    result = "x"
            except (ValueError, TypeError):
                pass
        if round_key not in bracket_rounds:
            bracket_rounds[round_key] = []
        bracket_rounds[round_key].append({
            "home": home,
            "away": away,
            "home_score": hs,
            "away_score": aws,
            "result": result,
            "winner": winner,
            "date": _format_date(date) if date else "",
        })
    bracket_data = list(bracket_rounds.items())

    total_games = len(matches) + sum(len(ms) for _, ms in bracket_data)
    completed_games = sum(1 for m in matches if m["resultat"]) + sum(1 for _, ms in bracket_data for m in ms if m.get("result"))

    all_rounds = []
    for name, ms in match_groups:
        all_rounds.append({"name": name, "matches": list(ms), "has_bets": True})

    bracket_lookup = {name: ms for name, ms in bracket_data}
    for r in all_rounds:
        extra = bracket_lookup.pop(r["name"], None)
        if extra is not None:
            existing = {(m.get("local", ""), m.get("visitante", "")) for m in r["matches"]}
            for bm in extra:
                pair = (bm["home"], bm["away"])
                if pair not in existing and (bm["away"], bm["home"]) not in existing:
                    r["matches"].append({
                        "local": bm["home"],
                        "visitante": bm["away"],
                        "data": bm["date"],
                        "home_score": bm["home_score"],
                        "away_score": bm["away_score"],
                        "resultat": bm["result"],
                        "winner": bm.get("winner", ""),
                        "rating_value": 0.0,
                        "apuestas": {p: {"bet": "", "hit": False} for p in participants},
                        "stage_name": "",
                        "group_name": "",
                        "jornada": 0,
                    })

    for name, ms in bracket_lookup.items():
        all_rounds.append({"name": name, "matches": ms, "has_bets": False})

    current_section = 0
    for i, section in enumerate(all_rounds):
        for match in section["matches"]:
            if not match.get("resultat") and not match.get("result"):
                current_section = i
                break
        else:
            continue
        break

    template = Template(open("template.html", encoding="utf-8").read())
    html = template.render(ranking=ranking, all_rounds=all_rounds, total_games=total_games, completed_games=completed_games, current_section=current_section)
    os.makedirs('dist', exist_ok=True)
    with open("dist/index.html", mode="w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
