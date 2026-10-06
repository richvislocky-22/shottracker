import csv
import io
import tempfile
import unittest
from pathlib import Path

from app import create_app


class ShotTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        app = create_app(Path(self.temp_dir.name) / "test-shots.sqlite3")
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def shot(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "game_name": "Falcons vs Hawks",
            "team": "our",
            "result": "goal",
            "bounce": True,
            "post_hit": False,
            "field_x": 0.4,
            "field_y": 0.6,
            "target_x": 0.5,
            "target_y": 0.3,
        }
        values.update(overrides)
        return values

    def test_records_shots_by_game_and_goalie_side(self) -> None:
        response = self.client.post("/api/shots", json=self.shot())
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["bounce"])

        other_side = self.client.post(
            "/api/shots", json=self.shot(team="opponent", result="save", bounce=False)
        )
        self.assertEqual(other_side.status_code, 201)

        ours = self.client.get("/api/shots?game_name=Falcons+vs+Hawks&team=our")
        opponents = self.client.get(
            "/api/shots?game_name=Falcons+vs+Hawks&team=opponent"
        )
        self.assertEqual(len(ours.json), 1)
        self.assertEqual(ours.json[0]["result"], "goal")
        self.assertEqual(len(opponents.json), 1)
        self.assertEqual(opponents.json[0]["result"], "save")

    def test_rejects_invalid_shot_and_invalid_team_filter(self) -> None:
        invalid_shot = self.client.post(
            "/api/shots", json=self.shot(field_x=1.5)
        )
        malformed_team = self.client.post("/api/shots", json=self.shot(team=[]))
        invalid_team = self.client.get("/api/shots?team=unknown")
        self.assertEqual(invalid_shot.status_code, 400)
        self.assertEqual(malformed_team.status_code, 400)
        self.assertEqual(invalid_team.status_code, 400)

    def test_exports_csv_and_deletes_shot(self) -> None:
        created = self.client.post("/api/shots", json=self.shot(post_hit=True))
        shot_id = created.json["id"]
        self.assertTrue(created.json["post_hit"])
        exported = self.client.get("/export.csv?game_name=Falcons+vs+Hawks&team=our")
        rows = list(csv.reader(io.StringIO(exported.get_data(as_text=True))))
        self.assertEqual(exported.mimetype, "text/csv")
        self.assertEqual(rows[1][2], "goal")
        self.assertEqual(rows[1][4], "True")

        deleted = self.client.delete(f"/api/shots/{shot_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get("/api/shots?game_name=Falcons+vs+Hawks&team=our").json,
            [],
        )

    def test_records_optional_player_number(self) -> None:
        without_number = self.client.post("/api/shots", json=self.shot())
        self.assertEqual(without_number.status_code, 201)
        self.assertIsNone(without_number.json["player_number"])

        with_number = self.client.post("/api/shots", json=self.shot(player_number="12"))
        self.assertEqual(with_number.status_code, 201)
        self.assertEqual(with_number.json["player_number"], "12")

        too_long = self.client.post(
            "/api/shots", json=self.shot(player_number="12345678901")
        )
        self.assertEqual(too_long.status_code, 400)

    def test_updates_shot_details(self) -> None:
        created = self.client.post("/api/shots", json=self.shot())
        shot_id = created.json["id"]

        updated = self.client.patch(
            f"/api/shots/{shot_id}",
            json={"result": "save", "bounce": False, "post_hit": True, "player_number": "7"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["result"], "save")
        self.assertFalse(updated.json["bounce"])
        self.assertTrue(updated.json["post_hit"])
        self.assertEqual(updated.json["player_number"], "7")

        cleared = self.client.patch(
            f"/api/shots/{shot_id}", json={"player_number": ""}
        )
        self.assertIsNone(cleared.json["player_number"])

        missing = self.client.patch("/api/shots/9999", json={"result": "goal"})
        self.assertEqual(missing.status_code, 404)

        no_changes = self.client.patch(f"/api/shots/{shot_id}", json={})
        self.assertEqual(no_changes.status_code, 400)

    def test_records_default_quarter_and_allows_valid_overrides(self) -> None:
        default_quarter = self.client.post("/api/shots", json=self.shot())
        self.assertEqual(default_quarter.json["quarter"], "1")

        ot_shot = self.client.post("/api/shots", json=self.shot(quarter="OT"))
        self.assertEqual(ot_shot.status_code, 201)
        self.assertEqual(ot_shot.json["quarter"], "OT")

        invalid_quarter = self.client.post("/api/shots", json=self.shot(quarter="5"))
        self.assertEqual(invalid_quarter.status_code, 400)

    def test_goalie_roster_crud_and_shot_association(self) -> None:
        empty = self.client.get("/api/goalies?team=our")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json, [])

        missing_team = self.client.get("/api/goalies")
        self.assertEqual(missing_team.status_code, 400)

        created = self.client.post("/api/goalies", json={"team": "our", "name": "Jamie"})
        self.assertEqual(created.status_code, 201)
        goalie_id = created.json["id"]

        duplicate = self.client.post("/api/goalies", json={"team": "our", "name": "jamie"})
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json["id"], goalie_id)

        roster = self.client.get("/api/goalies?team=our")
        self.assertEqual(len(roster.json), 1)

        opponent_roster = self.client.get("/api/goalies?team=opponent")
        self.assertEqual(opponent_roster.json, [])

        shot_with_goalie = self.client.post(
            "/api/shots", json=self.shot(goalie_name="Jamie")
        )
        self.assertEqual(shot_with_goalie.json["goalie_name"], "Jamie")

        deleted = self.client.delete(f"/api/goalies/{goalie_id}")
        self.assertEqual(deleted.status_code, 200)

        missing_delete = self.client.delete(f"/api/goalies/{goalie_id}")
        self.assertEqual(missing_delete.status_code, 404)


if __name__ == "__main__":
    unittest.main()
