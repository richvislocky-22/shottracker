const teamButtons = [...document.querySelectorAll(".side-button")];
const gameInput = document.querySelector("#game-name");
const resultInputs = [...document.querySelectorAll('input[name="result"]')];
const bounceInput = document.querySelector("#bounce-shot");
const postHitInput = document.querySelector("#post-hit");
const playerNumberInput = document.querySelector("#player-number");
const quarterSelect = document.querySelector("#quarter-select");
const goalieSelect = document.querySelector("#goalie-select");
const recordButton = document.querySelector("#record-shot");
const message = document.querySelector("#message");
const fieldMap = document.querySelector("#field-map");
const goalMap = document.querySelector("#goal-map");

const zones = [
  ["left-close", "Left · close"],
  ["center-close", "Center · close"],
  ["right-close", "Right · close"],
  ["left-far", "Left · far"],
  ["center-far", "Center · far"],
  ["right-far", "Right · far"],
];

const state = {
  team: "our",
  field: null,
  target: null,
  shots: [],
  goalies: [],
};

const ADD_NEW_GOALIE_VALUE = "__add_new__";

gameInput.value = localStorage.getItem("shotTrackerGame") || "";

function populateGoalieSelect(selectEl, goalies, selectedName) {
  const previous = selectedName !== undefined ? selectedName : selectEl.value;
  selectEl.innerHTML =
    `<option value="">No goalie set</option>` +
    goalies.map((goalie) => `<option value="${goalie.name}">${goalie.name}</option>`).join("") +
    `<option value="${ADD_NEW_GOALIE_VALUE}">+ Add new goalie…</option>`;
  if (previous && goalies.some((goalie) => goalie.name === previous)) {
    selectEl.value = previous;
  } else {
    selectEl.value = "";
  }
}

async function refreshGoalies() {
  const response = await fetch(`/api/goalies?team=${state.team}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Could not load goalies.");
  state.goalies = payload;
  populateGoalieSelect(goalieSelect, state.goalies);
  populateGoalieSelect(document.querySelector("#edit-goalie-select"), state.goalies);
}

async function handleGoalieSelectChange(selectEl) {
  if (selectEl.value !== ADD_NEW_GOALIE_VALUE) return;
  const isEdit = selectEl.id === "edit-goalie-select";
  const fieldEl = document.querySelector(isEdit ? "#edit-goalie-new-field" : "#goalie-new-field");
  const nameInput = document.querySelector(isEdit ? "#edit-goalie-new-name" : "#goalie-new-name");
  selectEl.value = "";
  fieldEl.hidden = false;
  nameInput.value = "";
  nameInput.focus();
}

async function addNewGoalie(selectEl, nameInput, fieldEl) {
  const trimmed = nameInput.value.trim();
  if (!trimmed) {
    nameInput.focus();
    return;
  }
  const response = await fetch("/api/goalies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ team: state.team, name: trimmed }),
  });
  const payload = await response.json();
  if (!response.ok) {
    message.textContent = payload.error || "Could not add goalie.";
    return;
  }
  await refreshGoalies();
  selectEl.value = trimmed;
  fieldEl.hidden = true;
  message.textContent = "";
}

goalieSelect.addEventListener("change", () => handleGoalieSelectChange(goalieSelect));
document.querySelector("#edit-goalie-select").addEventListener("change", (event) =>
  handleGoalieSelectChange(event.target),
);

document.querySelector("#goalie-new-add").addEventListener("click", () =>
  addNewGoalie(goalieSelect, document.querySelector("#goalie-new-name"), document.querySelector("#goalie-new-field")),
);
document.querySelector("#goalie-new-cancel").addEventListener("click", () => {
  document.querySelector("#goalie-new-field").hidden = true;
  goalieSelect.value = "";
});
document.querySelector("#goalie-new-name").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    document.querySelector("#goalie-new-add").click();
  }
});

document.querySelector("#edit-goalie-new-add").addEventListener("click", () =>
  addNewGoalie(
    document.querySelector("#edit-goalie-select"),
    document.querySelector("#edit-goalie-new-name"),
    document.querySelector("#edit-goalie-new-field"),
  ),
);
document.querySelector("#edit-goalie-new-cancel").addEventListener("click", () => {
  document.querySelector("#edit-goalie-new-field").hidden = true;
  document.querySelector("#edit-goalie-select").value = "";
});
document.querySelector("#edit-goalie-new-name").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    document.querySelector("#edit-goalie-new-add").click();
  }
});

function coordinates(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const local = point.matrixTransform(svg.getScreenCTM().inverse());
  const viewBox = svg.viewBox.baseVal;
  return {
    x: Math.min(1, Math.max(0, (local.x - viewBox.x) / viewBox.width)),
    y: Math.min(1, Math.max(0, (local.y - viewBox.y) / viewBox.height)),
    localX: local.x,
    localY: local.y,
  };
}

function zoneFor(x, y) {
  const dx = x * 600 - 300;
  const dy = y * 420 - 300;
  const angle = (Math.atan2(dx, -dy) * 180) / Math.PI;
  const column = angle < -30 ? 0 : angle < 30 ? 1 : 2;
  const radius = Math.sqrt(dx * dx + dy * dy);
  const depth = radius < 170 ? 0 : 1;
  return zones[depth * 3 + column][0];
}

function zoneLabel(zoneId) {
  return zones.find(([id]) => id === zoneId)?.[1] || "Field";
}

function markerColor(result) {
  return result === "goal" ? "goal" : "save";
}

function markerMarkup(shot, x, y) {
  const result = markerColor(shot.result);
  const postRing = shot.post_hit
    ? `<circle class="marker-post-ring" cx="${x}" cy="${y}" r="14"></circle>`
    : "";
  const bounce = shot.bounce
    ? `<text class="marker-bounce ${result}-b" x="${x}" y="${y}">B</text>`
    : "";
  return `<g>${postRing}<circle class="marker ${result}" cx="${x}" cy="${y}" r="10"></circle>${bounce}</g>`;
}

function drawMarkers() {
  const fieldMarkers = document.querySelector("#field-markers");
  const goalMarkers = document.querySelector("#goal-markers");
  fieldMarkers.replaceChildren();
  goalMarkers.replaceChildren();
  for (const shot of state.shots) {
    const fieldGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    fieldGroup.innerHTML = markerMarkup(
      shot,
      (shot.field_x * 600).toFixed(1),
      (shot.field_y * 420).toFixed(1),
    );
    fieldMarkers.append(fieldGroup);

    const goalGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    goalGroup.innerHTML = markerMarkup(
      shot,
      (shot.target_x * 280).toFixed(1),
      (shot.target_y * 280).toFixed(1),
    );
    goalMarkers.append(goalGroup);
  }
}

function drawSelection(groupId, point, svg, mapKind) {
  const group = document.querySelector(groupId);
  group.replaceChildren();
  if (!point) return;

  const x = mapKind === "field" ? point.x * 600 : point.x * 280;
  const y = mapKind === "field" ? point.y * 420 : point.y * 280;
  const ns = "http://www.w3.org/2000/svg";
  const ring = document.createElementNS(ns, "circle");
  ring.setAttribute("cx", String(x));
  ring.setAttribute("cy", String(y));
  ring.setAttribute("r", mapKind === "field" ? "9" : "8");
  ring.setAttribute("class", "selection-ring");
  group.append(ring);
  const center = document.createElementNS(ns, "circle");
  center.setAttribute("cx", String(x));
  center.setAttribute("cy", String(y));
  center.setAttribute("r", "2.5");
  center.setAttribute("class", "selection-center");
  group.append(center);
}

function updateCaptions() {
  document.querySelector("#field-caption").textContent = state.field
    ? `Selected: ${zoneLabel(zoneFor(state.field.x, state.field.y))}`
    : "Choose a spot on the field map";
  document.querySelector("#goal-caption").textContent = state.target
    ? "Goal location selected"
    : "Choose a spot in the goal or on a post";
}

function renderZones() {
  const totals = Object.fromEntries(zones.map(([id]) => [id, { attempts: 0, goals: 0 }]));
  for (const shot of state.shots) {
    const zone = zoneFor(shot.field_x, shot.field_y);
    totals[zone].attempts += 1;
    if (shot.result === "goal") totals[zone].goals += 1;
  }
  const maxAttempts = Math.max(1, ...Object.values(totals).map((item) => item.attempts));
  document.querySelector("#zone-list").innerHTML = zones.map(([id, label]) => {
    const item = totals[id];
    const percentage = item.attempts ? Math.round((item.goals / item.attempts) * 100) : 0;
    const width = (item.attempts / maxAttempts) * 100;
    return `<div class="zone-row">
      <span class="zone-name">${label}</span>
      <span class="zone-record">${item.goals}/${item.attempts} · ${percentage}%</span>
      <span class="zone-bar"><span style="width:${width}%"></span></span>
    </div>`;
  }).join("");
}

function renderShots() {
  const goals = state.shots.filter((shot) => shot.result === "goal").length;
  const saves = state.shots.filter((shot) => shot.result === "save").length;
  const savePct = goals + saves ? Math.round((saves / (goals + saves)) * 100) : null;
  document.querySelector("#stat-shots").textContent = String(state.shots.length);
  document.querySelector("#stat-goals").textContent = String(goals);
  document.querySelector("#stat-saves").textContent = String(saves);
  document.querySelector("#stat-save-pct").textContent = savePct === null ? "—" : `${savePct}%`;
  document.querySelector("#shot-count-label").textContent =
    `${state.shots.length} ${state.shots.length === 1 ? "recorded shot" : "recorded shots"}`;
  document.querySelector("#empty-state").hidden = state.shots.length > 0;
  document.querySelector("#shot-list").innerHTML = state.shots.map((shot) => {
    const result = shot.result[0].toUpperCase() + shot.result.slice(1);
    const tags = [shot.bounce ? "Bounce" : null, shot.post_hit ? "Hit post" : null]
      .filter(Boolean)
      .join(" · ");
    const playerBadge = shot.player_number
      ? `<span class="player-badge">#${shot.player_number}</span>`
      : "";
    const quarterLabel = shot.quarter === "OT" ? "OT" : `Q${shot.quarter}`;
    const goalieLabel = shot.goalie_name ? ` · ${shot.goalie_name}` : "";
    return `<li class="shot-row">
      <span class="outcome-mark ${markerColor(shot.result)} ${shot.post_hit ? "post-hit" : ""}">${shot.bounce ? "B" : result[0]}</span>
      <span class="shot-description"><strong>${result}${tags ? " · " + tags : ""}${playerBadge}</strong>
        <small>${zoneLabel(zoneFor(shot.field_x, shot.field_y))} · ${quarterLabel}${goalieLabel} · ${shot.created_at}</small>
      </span>
      <span class="shot-actions">
        <button class="edit-shot" type="button" data-shot-id="${shot.id}" aria-label="Edit ${result.toLowerCase()} shot">✎</button>
        <button class="delete-shot" type="button" data-shot-id="${shot.id}" aria-label="Delete ${result.toLowerCase()} shot">×</button>
      </span>
    </li>`;
  }).join("");
  renderZones();
  drawMarkers();
  const exportUrl = new URL("/export.csv", window.location.origin);
  exportUrl.searchParams.set("game_name", gameInput.value.trim());
  exportUrl.searchParams.set("team", state.team);
  document.querySelector("#export-link").href = exportUrl;
}

async function refreshShots() {
  const query = new URLSearchParams({
    game_name: gameInput.value.trim(),
    team: state.team,
  });
  const response = await fetch(`/api/shots?${query}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Could not load shots.");
  state.shots = payload;
  renderShots();
}

fieldMap.addEventListener("click", (event) => {
  message.classList.remove("success");
  const point = coordinates(fieldMap, event);
  const dx = point.localX - 300;
  const dy = point.localY - 300;
  const radius = Math.sqrt(dx * dx + dy * dy);
  const angle = (Math.atan2(dx, -dy) * 180) / Math.PI;
  if (dy > 0 || radius < 50 || radius > 270 || angle < -90 || angle > 90) {
    message.textContent = "Tap inside the 8-meter arc to mark the shot origin.";
    return;
  }
  state.field = { x: point.x, y: point.y };
  drawSelection("#field-selection", state.field, fieldMap, "field");
  fieldMap.querySelectorAll(".zone-shape").forEach((shape) => {
    shape.classList.toggle("selected", shape.dataset.zone === zoneFor(point.x, point.y));
  });
  updateCaptions();
  message.textContent = "";
  message.classList.remove("success");
});

goalMap.addEventListener("click", (event) => {
  message.classList.remove("success");
  const point = coordinates(goalMap, event);
  if (point.localX < 32 || point.localX > 248 || point.localY < 14 || point.localY > 226) {
    message.textContent = "Tap inside the goal or on its frame to mark where the shot went.";
    return;
  }
  state.target = { x: point.x, y: point.y };
  drawSelection("#goal-selection", state.target, goalMap, "goal");
  updateCaptions();
  message.textContent = "";
  message.classList.remove("success");
});

teamButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    state.team = button.dataset.team;
    teamButtons.forEach((item) => item.classList.toggle("active", item === button));
    try {
      await Promise.all([refreshShots(), refreshGoalies()]);
    } catch (error) {
      message.textContent = error.message;
    }
  });
});

gameInput.addEventListener("change", async () => {
  localStorage.setItem("shotTrackerGame", gameInput.value.trim());
  try {
    await refreshShots();
  } catch (error) {
    message.textContent = error.message;
  }
});

recordButton.addEventListener("click", async () => {
  message.textContent = "";
  if (!gameInput.value.trim()) {
    message.textContent = "Add a game name before recording a shot.";
    gameInput.focus();
    return;
  }
  if (!state.field || !state.target) {
    message.textContent = "Tap a shot location on the field and a target location in the goal.";
    return;
  }
  const payload = {
    game_name: gameInput.value.trim(),
    team: state.team,
    result: resultInputs.find((input) => input.checked).value,
    bounce: bounceInput.checked,
    post_hit: postHitInput.checked,
    player_number: playerNumberInput.value.trim(),
    quarter: quarterSelect.value,
    goalie_name: goalieSelect.value === ADD_NEW_GOALIE_VALUE ? "" : goalieSelect.value,
    field_x: state.field.x,
    field_y: state.field.y,
    target_x: state.target.x,
    target_y: state.target.y,
  };
  recordButton.disabled = true;
  try {
    const response = await fetch("/api/shots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not record shot.");
    localStorage.setItem("shotTrackerGame", payload.game_name);
    state.field = null;
    state.target = null;
    bounceInput.checked = false;
    postHitInput.checked = false;
    playerNumberInput.value = "";
    drawSelection("#field-selection", null, fieldMap, "field");
    drawSelection("#goal-selection", null, goalMap, "goal");
    fieldMap.querySelectorAll(".zone-shape").forEach((shape) => shape.classList.remove("selected"));
    updateCaptions();
    await refreshShots();
    message.textContent = "Shot recorded.";
    message.classList.add("success");
  } catch (error) {
    message.textContent = error.message;
    message.classList.remove("success");
  } finally {
    recordButton.disabled = false;
  }
});

document.querySelector("#shot-list").addEventListener("click", async (event) => {
  const deleteButton = event.target.closest(".delete-shot");
  if (deleteButton) {
    deleteButton.disabled = true;
    try {
      const response = await fetch(`/api/shots/${deleteButton.dataset.shotId}`, { method: "DELETE" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Could not delete shot.");
      await refreshShots();
      message.textContent = "Shot removed.";
      message.classList.remove("success");
    } catch (error) {
      message.textContent = error.message;
      deleteButton.disabled = false;
    }
    return;
  }

  const editButton = event.target.closest(".edit-shot");
  if (editButton) {
    openEditDialog(editButton.dataset.shotId);
  }
});

const editOverlay = document.querySelector("#edit-overlay");
const editResultInputs = [...document.querySelectorAll('input[name="edit-result"]')];
const editBounceInput = document.querySelector("#edit-bounce");
const editPostHitInput = document.querySelector("#edit-post-hit");
const editPlayerNumberInput = document.querySelector("#edit-player-number");
const editQuarterSelect = document.querySelector("#edit-quarter");
const editGoalieSelect = document.querySelector("#edit-goalie-select");
const editMessage = document.querySelector("#edit-message");
const editSaveButton = document.querySelector("#edit-save");
let editingShotId = null;

function openEditDialog(shotId) {
  const shot = state.shots.find((item) => String(item.id) === String(shotId));
  if (!shot) return;
  editingShotId = shot.id;
  editResultInputs.forEach((input) => { input.checked = input.value === shot.result; });
  editBounceInput.checked = shot.bounce;
  editPostHitInput.checked = shot.post_hit;
  editPlayerNumberInput.value = shot.player_number || "";
  editQuarterSelect.value = shot.quarter || "1";
  populateGoalieSelect(editGoalieSelect, state.goalies, shot.goalie_name || "");
  editMessage.textContent = "";
  editOverlay.hidden = false;
}

function closeEditDialog() {
  editOverlay.hidden = true;
  editingShotId = null;
}

document.querySelector("#edit-cancel").addEventListener("click", closeEditDialog);
editOverlay.addEventListener("click", (event) => {
  if (event.target === editOverlay) closeEditDialog();
});

editSaveButton.addEventListener("click", async () => {
  if (editingShotId === null) return;
  const payload = {
    result: editResultInputs.find((input) => input.checked).value,
    bounce: editBounceInput.checked,
    post_hit: editPostHitInput.checked,
    player_number: editPlayerNumberInput.value.trim(),
    quarter: editQuarterSelect.value,
    goalie_name: editGoalieSelect.value === ADD_NEW_GOALIE_VALUE ? "" : editGoalieSelect.value,
  };
  editSaveButton.disabled = true;
  try {
    const response = await fetch(`/api/shots/${editingShotId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not update shot.");
    closeEditDialog();
    await refreshShots();
    message.textContent = "Shot updated.";
    message.classList.add("success");
  } catch (error) {
    editMessage.textContent = error.message;
  } finally {
    editSaveButton.disabled = false;
  }
});

updateCaptions();
refreshShots().catch((error) => {
  message.textContent = error.message;
});
refreshGoalies().catch((error) => {
  message.textContent = error.message;
});
