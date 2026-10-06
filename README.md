# ShotTracker

A sideline-friendly web app for tracking women's lacrosse shots. It stores each shot in a local SQLite database and records the shooter location and where the ball reached the goal.

## Run locally

From this folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Then open <http://127.0.0.1:5000>. Shot data is saved in `shots.db` in this folder. The database path can be changed with the `SHOT_TRACKER_DB` environment variable.

## Use

1. Enter a game name and select whether you are tracking your goalie or the opponent's goalie.
2. Tap the shaded field area to mark where the shot was taken.
3. Tap inside the front-facing goal diagram to mark where it went.
4. Choose goal, save, or post; turn on **Bounce shot** if applicable; then record it.
5. Review the live totals and the field-zone goal/attempt report, remove a shot with **×**, or export the current game and goalie side to CSV.

Run the API tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
