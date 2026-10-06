from __future__ import annotations

import csv
import io
import math
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from flask import Flask, Response, jsonify, render_template, request


PROJECT_DIR = Path(__file__).resolve().parent
VALID_TEAMS = {"our", "opponent"}
VALID_RESULTS = {"goal", "save"}
VALID_QUARTERS = {"1", "2", "3", "4", "OT"}


def create_app(database_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    db_path = Path(
        database_path or os.environ.get("SHOT_TRACKER_DB", PROJECT_DIR / "shots.db")
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect_db() -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS shots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT NOT NULL,
                team TEXT NOT NULL CHECK (team IN ('our', 'opponent')),
                result TEXT NOT NULL CHECK (result IN ('goal', 'save')),
                bounce INTEGER NOT NULL CHECK (bounce IN (0, 1)),
                post_hit INTEGER NOT NULL DEFAULT 0 CHECK (post_hit IN (0, 1)),
                field_x REAL NOT NULL CHECK (field_x BETWEEN 0 AND 1),
                field_y REAL NOT NULL CHECK (field_y BETWEEN 0 AND 1),
                target_x REAL NOT NULL CHECK (target_x BETWEEN 0 AND 1),
                target_y REAL NOT NULL CHECK (target_y BETWEEN 0 AND 1),
                quarter TEXT NOT NULL DEFAULT '1' CHECK (quarter IN ('1', '2', '3', '4', 'OT')),
                goalie_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(shots)")
        }
        if "post_hit" not in existing_columns:
            connection.execute(
                "ALTER TABLE shots ADD COLUMN post_hit INTEGER NOT NULL DEFAULT 0"
            )
        if "result" in existing_columns:
            connection.execute(
                "UPDATE shots SET post_hit = 1, result = 'save' WHERE result = 'post'"
            )
        if "player_number" not in existing_columns:
            connection.execute(
                "ALTER TABLE shots ADD COLUMN player_number TEXT"
            )
        if "quarter" not in existing_columns:
            connection.execute(
                "ALTER TABLE shots ADD COLUMN quarter TEXT NOT NULL DEFAULT '1'"
            )
        if "goalie_name" not in existing_columns:
            connection.execute(
                "ALTER TABLE shots ADD COLUMN goalie_name TEXT"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS goalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team TEXT NOT NULL CHECK (team IN ('our', 'opponent')),
                name TEXT NOT NULL,
                UNIQUE (team, name)
            )
            """
        )

    def shot_dict(row: sqlite3.Row) -> dict[str, Any]:
        shot = dict(row)
        shot["bounce"] = bool(shot["bounce"])
        shot["post_hit"] = bool(shot["post_hit"])
        return shot

    def parse_player_number(payload: dict[str, Any]) -> tuple[str | None, str | None]:
        """Validate the optional player_number field.

        Returns (value, error). value is None when omitted/blank.
        """
        if "player_number" not in payload or payload.get("player_number") in (None, ""):
            return None, None
        player_number = payload.get("player_number")
        if not isinstance(player_number, str):
            return None, "Player number must be text."
        player_number = player_number.strip()
        if not player_number:
            return None, None
        if len(player_number) > 10:
            return None, "Player number must be 10 characters or fewer."
        return player_number, None

    def parse_goalie_name(payload: dict[str, Any]) -> tuple[str | None, str | None]:
        """Validate the optional goalie_name field. Returns (value, error)."""
        if "goalie_name" not in payload or payload.get("goalie_name") in (None, ""):
            return None, None
        goalie_name = payload.get("goalie_name")
        if not isinstance(goalie_name, str):
            return None, "Goalie name must be text."
        goalie_name = goalie_name.strip()
        if not goalie_name:
            return None, None
        if len(goalie_name) > 60:
            return None, "Goalie name must be 60 characters or fewer."
        return goalie_name, None

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/goalies")
    def list_goalies() -> tuple[Response, int] | Response:
        team = request.args.get("team", "").strip()
        if not team or team not in VALID_TEAMS:
            return jsonify(error="Choose our goalie or the opponent goalie."), 400
        with connect_db() as connection:
            rows = connection.execute(
                "SELECT * FROM goalies WHERE team = ? ORDER BY name COLLATE NOCASE",
                (team,),
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/api/goalies")
    def add_goalie() -> tuple[Response, int] | Response:
        if not request.is_json:
            return jsonify(error="Send goalie details as JSON."), 400
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="Goalie details must be a JSON object."), 400

        team = payload.get("team")
        name = payload.get("name")
        if not isinstance(team, str) or team not in VALID_TEAMS:
            return jsonify(error="Choose our goalie or the opponent goalie."), 400
        if not isinstance(name, str) or not name.strip():
            return jsonify(error="Enter a goalie name."), 400
        name = name.strip()
        if len(name) > 60:
            return jsonify(error="Goalie name must be 60 characters or fewer."), 400

        with connect_db() as connection:
            existing = connection.execute(
                "SELECT * FROM goalies WHERE team = ? AND name = ? COLLATE NOCASE",
                (team, name),
            ).fetchone()
            if existing is not None:
                return jsonify(dict(existing)), 200
            cursor = connection.execute(
                "INSERT INTO goalies (team, name) VALUES (?, ?)", (team, name)
            )
            row = connection.execute(
                "SELECT * FROM goalies WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return jsonify(dict(row)), 201

    @app.delete("/api/goalies/<int:goalie_id>")
    def delete_goalie(goalie_id: int) -> tuple[Response, int] | Response:
        with connect_db() as connection:
            cursor = connection.execute("DELETE FROM goalies WHERE id = ?", (goalie_id,))
        if cursor.rowcount == 0:
            return jsonify(error="That goalie was not found."), 404
        return jsonify(deleted=True)

    @app.get("/api/shots")
    def get_shots() -> Response:
        game_name = request.args.get("game_name", "").strip()
        team = request.args.get("team", "").strip()
        if team and team not in VALID_TEAMS:
            return jsonify(error="Unknown goalie side."), 400

        query = "SELECT * FROM shots WHERE game_name = ?"
        values: list[Any] = [game_name]
        if team:
            query += " AND team = ?"
            values.append(team)
        query += " ORDER BY id DESC"

        with connect_db() as connection:
            rows = connection.execute(query, values).fetchall()
        return jsonify([shot_dict(row) for row in rows])

    @app.post("/api/shots")
    def add_shot() -> tuple[Response, int] | Response:
        if not request.is_json:
            return jsonify(error="Send shot details as JSON."), 400
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="Shot details must be a JSON object."), 400

        game_name = payload.get("game_name")
        team = payload.get("team")
        result = payload.get("result")
        bounce = payload.get("bounce")
        post_hit = payload.get("post_hit", False)
        if not isinstance(game_name, str) or not game_name.strip():
            return jsonify(error="Enter a game name before recording a shot."), 400
        if len(game_name.strip()) > 100:
            return jsonify(error="Game names must be 100 characters or fewer."), 400
        if not isinstance(team, str) or team not in VALID_TEAMS:
            return jsonify(error="Choose our goalie or the opponent goalie."), 400
        if not isinstance(result, str) or result not in VALID_RESULTS:
            return jsonify(error="Choose goal or save."), 400
        if not isinstance(bounce, bool):
            return jsonify(error="Choose whether the shot was a bounce shot."), 400
        if not isinstance(post_hit, bool):
            return jsonify(error="Choose whether the shot hit the post."), 400
        player_number, player_error = parse_player_number(payload)
        if player_error:
            return jsonify(error=player_error), 400
        goalie_name, goalie_error = parse_goalie_name(payload)
        if goalie_error:
            return jsonify(error=goalie_error), 400
        quarter = payload.get("quarter", "1")
        if not isinstance(quarter, str) or quarter not in VALID_QUARTERS:
            return jsonify(error="Choose a valid quarter."), 400

        coordinates: dict[str, float] = {}
        for key in ("field_x", "field_y", "target_x", "target_y"):
            value = payload.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                return jsonify(error="Choose a valid location on both diagrams."), 400
            coordinates[key] = float(value)

        with connect_db() as connection:
            cursor = connection.execute(
                """
                INSERT INTO shots (
                    game_name, team, result, bounce, post_hit, player_number,
                    quarter, goalie_name,
                    field_x, field_y, target_x, target_y
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_name.strip(),
                    team,
                    result,
                    int(bounce),
                    int(post_hit),
                    player_number,
                    quarter,
                    goalie_name,
                    coordinates["field_x"],
                    coordinates["field_y"],
                    coordinates["target_x"],
                    coordinates["target_y"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM shots WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return jsonify(shot_dict(row)), 201

    @app.patch("/api/shots/<int:shot_id>")
    def update_shot(shot_id: int) -> tuple[Response, int] | Response:
        if not request.is_json:
            return jsonify(error="Send shot details as JSON."), 400
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="Shot details must be a JSON object."), 400

        with connect_db() as connection:
            existing = connection.execute(
                "SELECT * FROM shots WHERE id = ?", (shot_id,)
            ).fetchone()
            if existing is None:
                return jsonify(error="That shot was not found."), 404

            updates: dict[str, Any] = {}

            if "result" in payload:
                result = payload.get("result")
                if not isinstance(result, str) or result not in VALID_RESULTS:
                    return jsonify(error="Choose goal or save."), 400
                updates["result"] = result

            if "bounce" in payload:
                bounce = payload.get("bounce")
                if not isinstance(bounce, bool):
                    return jsonify(error="Choose whether the shot was a bounce shot."), 400
                updates["bounce"] = int(bounce)

            if "post_hit" in payload:
                post_hit = payload.get("post_hit")
                if not isinstance(post_hit, bool):
                    return jsonify(error="Choose whether the shot hit the post."), 400
                updates["post_hit"] = int(post_hit)

            if "player_number" in payload:
                player_number, player_error = parse_player_number(payload)
                if player_error:
                    return jsonify(error=player_error), 400
                updates["player_number"] = player_number

            if "goalie_name" in payload:
                goalie_name, goalie_error = parse_goalie_name(payload)
                if goalie_error:
                    return jsonify(error=goalie_error), 400
                updates["goalie_name"] = goalie_name

            if "quarter" in payload:
                quarter = payload.get("quarter")
                if not isinstance(quarter, str) or quarter not in VALID_QUARTERS:
                    return jsonify(error="Choose a valid quarter."), 400
                updates["quarter"] = quarter

            if not updates:
                return jsonify(error="No changes were provided."), 400

            set_clause = ", ".join(f"{key} = ?" for key in updates)
            connection.execute(
                f"UPDATE shots SET {set_clause} WHERE id = ?",
                (*updates.values(), shot_id),
            )
            row = connection.execute(
                "SELECT * FROM shots WHERE id = ?", (shot_id,)
            ).fetchone()
        return jsonify(shot_dict(row))

    @app.delete("/api/shots/<int:shot_id>")
    def delete_shot(shot_id: int) -> tuple[Response, int] | Response:
        with connect_db() as connection:
            cursor = connection.execute("DELETE FROM shots WHERE id = ?", (shot_id,))
        if cursor.rowcount == 0:
            return jsonify(error="That shot was not found."), 404
        return jsonify(deleted=True)

    @app.get("/export.csv")
    def export_csv() -> Response:
        game_name = request.args.get("game_name", "").strip()
        team = request.args.get("team", "").strip()
        if team and team not in VALID_TEAMS:
            return jsonify(error="Unknown goalie side."), 400

        query = "SELECT * FROM shots WHERE game_name = ?"
        values: list[Any] = [game_name]
        if team:
            query += " AND team = ?"
            values.append(team)
        query += " ORDER BY id"
        with connect_db() as connection:
            rows = connection.execute(query, values).fetchall()

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "game",
                "goalie_side",
                "result",
                "bounce_shot",
                "post_hit",
                "player_number",
                "quarter",
                "goalie_name",
                "field_x",
                "field_y",
                "goal_x",
                "goal_y",
                "recorded_at",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["game_name"],
                    row["team"],
                    row["result"],
                    bool(row["bounce"]),
                    bool(row["post_hit"]),
                    row["player_number"] or "",
                    row["quarter"],
                    row["goalie_name"] or "",
                    row["field_x"],
                    row["field_y"],
                    row["target_x"],
                    row["target_y"],
                    row["created_at"],
                ]
            )
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="shots.csv"'},
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
