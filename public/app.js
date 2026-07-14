(() => {
  const SESSION_KEY = "imposter-session";
  let session = null;
  try { session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); } catch { session = null; }

  let pollTimer = null;
  let lastPhase = null;
  let lastRound = null;
  let settingsSynced = false;
  let selectedVoteTarget = null;

  const $ = (id) => document.getElementById(id);
  const views = ["home", "lobby", "game", "gameover"];

  function showView(name) {
    for (const v of views) $(`view-${v}`).classList.toggle("hidden", v !== name);
  }

  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.add("hidden"), 2200);
  }

  async function apiGet(url) {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }

  async function apiPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    return data;
  }

  function saveSession(s) {
    session = s;
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  }

  function clearSession() {
    session = null;
    localStorage.removeItem(SESSION_KEY);
    stopPolling();
  }

  function authed(path) {
    return `/api/rooms/${session.roomCode}/${path}`;
  }

  // ---------------------------------------------------------------------
  // Home view
  // ---------------------------------------------------------------------

  $("btn-create").addEventListener("click", async () => {
    const name = $("create-name").value.trim();
    $("home-error").textContent = "";
    if (!name) { $("home-error").textContent = "Enter your name."; return; }
    try {
      const data = await apiPost("/api/rooms", { name });
      saveSession({ roomCode: data.roomCode, playerId: data.playerId, token: data.token });
      settingsSynced = false;
      enterRoom();
    } catch (e) {
      $("home-error").textContent = e.message;
    }
  });

  $("btn-join").addEventListener("click", async () => {
    const code = $("join-code").value.trim().toUpperCase();
    const name = $("join-name").value.trim();
    $("home-error").textContent = "";
    if (!code || !name) { $("home-error").textContent = "Enter a room code and your name."; return; }
    try {
      const data = await apiPost(`/api/rooms/${code}/join`, { name });
      saveSession({ roomCode: data.roomCode, playerId: data.playerId, token: data.token });
      settingsSynced = false;
      enterRoom();
    } catch (e) {
      $("home-error").textContent = e.message;
    }
  });

  // ---------------------------------------------------------------------
  // Lobby view
  // ---------------------------------------------------------------------

  $("btn-copy-code").addEventListener("click", () => {
    navigator.clipboard?.writeText(session.roomCode).then(() => toast("Room code copied!"));
  });

  $("btn-leave-lobby").addEventListener("click", leaveRoom);
  $("btn-leave-gameover").addEventListener("click", leaveRoom);

  async function leaveRoom() {
    try { await apiPost(authed("leave"), { playerId: session.playerId, token: session.token }); } catch {}
    clearSession();
    showView("home");
  }

  $("btn-save-settings").addEventListener("click", async () => {
    $("lobby-error").textContent = "";
    const categories = [...document.querySelectorAll("#category-checks input:checked")].map((el) => el.value);
    const customLines = $("custom-categories").value.split("\n").map((l) => l.trim()).filter(Boolean);
    const customCategories = {};
    for (const line of customLines) {
      const idx = line.indexOf(":");
      if (idx === -1) continue;
      const name = line.slice(0, idx).trim();
      const words = line.slice(idx + 1).trim();
      if (name && words) customCategories[name] = words;
    }
    try {
      await apiPost(authed("settings"), {
        playerId: session.playerId,
        token: session.token,
        categories,
        customCategories,
        numImposters: parseInt($("num-imposters").value, 10),
        clueRounds: parseInt($("clue-rounds").value, 10),
      });
      toast("Settings saved.");
    } catch (e) {
      $("lobby-error").textContent = e.message;
    }
  });

  $("btn-start-game").addEventListener("click", async () => {
    $("lobby-error").textContent = "";
    try {
      await apiPost(authed("start"), { playerId: session.playerId, token: session.token });
    } catch (e) {
      $("lobby-error").textContent = e.message;
    }
  });

  function renderCategoryChecks(state) {
    const container = $("category-checks");
    if (container.dataset.built === "1") return;
    container.dataset.built = "1";
    container.innerHTML = "";
    const cats = state.settings.availableCategories;
    for (const name of Object.keys(cats)) {
      const label = document.createElement("label");
      const checked = state.settings.categories.includes(name) ? "checked" : "";
      label.innerHTML = `<input type="checkbox" value="${name}" ${checked}> ${name}`;
      container.appendChild(label);
    }
  }

  function renderLobby(state) {
    $("lobby-code").textContent = state.code;
    $("lobby-count").textContent = `(${state.players.length}/20)`;

    const isHost = state.hostId === state.you;
    $("lobby-players").innerHTML = state.players.map((p) => playerLi(p, { showKick: isHost && !p.isYou })).join("");
    document.querySelectorAll("#lobby-players .kick-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const targetId = e.target.dataset.id;
        try { await apiPost(authed("kick"), { playerId: session.playerId, token: session.token, targetId }); }
        catch (err) { toast(err.message); }
      });
    });

    renderCategoryChecks(state);
    $("host-settings").classList.toggle("hidden", !isHost);
    $("guest-settings").classList.toggle("hidden", isHost);

    if (!settingsSynced) {
      settingsSynced = true;
      $("num-imposters").value = state.settings.numImposters;
      $("clue-rounds").value = state.settings.clueRounds;
      const customLines = Object.entries(state.settings.customCategories)
        .map(([name, words]) => `${name}: ${words.join(", ")}`);
      $("custom-categories").value = customLines.join("\n");
    }

    if (!isHost) {
      const catList = state.settings.categories.join(", ") || "(none selected)";
      $("guest-settings-summary").textContent =
        `Categories: ${catList} • Imposters: ${state.settings.numImposters} • Clue rounds: ${state.settings.clueRounds}`;
    }
  }

  // ---------------------------------------------------------------------
  // Game view
  // ---------------------------------------------------------------------

  function playerLi(p, opts = {}) {
    const dot = `<span class="dot ${p.online ? "" : "off"}"></span>`;
    const crown = p.isHost ? '<span class="crown">👑</span>' : "";
    const you = p.isYou ? '<span class="you-tag">YOU</span>' : "";
    const kick = opts.showKick ? `<button class="ghost small danger kick-btn" data-id="${p.id}" style="margin-left:auto">Remove</button>` : "";
    const elim = p.eliminated ? " eliminated" : "";
    return `<li class="${elim}">${dot}${crown} ${escapeHtml(p.name)} ${you}${kick}</li>`;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  $("clue-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const clue = $("clue-input").value.trim();
    $("clue-error").textContent = "";
    if (!clue) return;
    try {
      await apiPost(authed("clue"), { playerId: session.playerId, token: session.token, clue });
      $("clue-input").value = "";
    } catch (err) {
      $("clue-error").textContent = err.message;
    }
  });

  $("guess-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const guess = $("guess-input").value.trim();
    if (!guess) return;
    const fb = $("guess-feedback");
    try {
      const res = await apiPost(authed("guess"), { playerId: session.playerId, token: session.token, guess });
      if (res.correct) {
        fb.textContent = "Correct! You win! 🎉";
        fb.className = "ok";
      } else {
        fb.textContent = "Not quite. Keep blending in.";
        fb.className = "bad";
      }
      $("guess-input").value = "";
    } catch (err) {
      fb.textContent = err.message;
      fb.className = "bad";
    }
  });

  $("btn-advance").addEventListener("click", async () => {
    try { await apiPost(authed("advance"), { playerId: session.playerId, token: session.token }); }
    catch (err) { toast(err.message); }
  });

  $("btn-toggle-hints").addEventListener("click", async () => {
    try { await apiPost(authed("toggle-hints"), { playerId: session.playerId, token: session.token }); }
    catch (err) { toast(err.message); }
  });

  $("btn-play-again").addEventListener("click", async () => {
    try { await apiPost(authed("play-again"), { playerId: session.playerId, token: session.token }); }
    catch (err) { toast(err.message); }
  });

  function renderGame(state) {
    const g = state.game;
    $("game-code").textContent = state.code;
    const isHost = state.hostId === state.you;

    const phaseLabels = { clue: "Clue Round", voting: "Voting", reveal: "Reveal" };
    $("phase-badge").textContent = phaseLabels[state.phase] || state.phase;
    $("round-indicator").textContent = state.phase === "clue" ? ` • Round ${g.round}/${g.maxRounds}` : "";

    const roleCard = $("role-card");
    if (g.youAreImposter) {
      roleCard.className = "role-card imposter";
      roleCard.innerHTML = `<div class="category-line">Category: ${escapeHtml(g.category)}</div>
        <div class="word-line">🎭 You are the IMPOSTER</div>
        <div class="muted">Blend in — or guess the word below.</div>`;
    } else {
      roleCard.className = "role-card crew";
      roleCard.innerHTML = `<div class="category-line">Category: ${escapeHtml(g.category)}</div>
        <div class="word-line">${escapeHtml(g.yourWord)}</div>`;
    }
    if (g.youAreEliminated) {
      roleCard.innerHTML += `<div class="muted" style="margin-top:8px">You've been eliminated — you can spectate but not act.</div>`;
    }

    // Clue phase
    const inClue = state.phase === "clue";
    $("clue-phase").classList.toggle("hidden", !inClue);
    if (inClue) {
      let lastRoundSeen = null;
      let html = "";
      for (const c of g.clues) {
        if (c.round !== lastRoundSeen) {
          lastRoundSeen = c.round;
          html += `<li class="round-divider">Round ${c.round}</li>`;
        }
        html += `<li><span class="clue-name">${escapeHtml(c.name)}:</span> ${escapeHtml(c.clue)}</li>`;
      }
      $("clue-list").innerHTML = html || '<li class="muted" style="border:none;background:none">No clues yet this round.</li>';
      $("clue-progress").textContent = `${g.cluesSubmittedCount}/${g.activeCount} submitted this round`;
      const submitted = g.youSubmittedClue || g.youAreEliminated;
      $("clue-input").disabled = submitted;
      $("clue-form").querySelector("button").disabled = submitted;
      $("clue-input").placeholder = submitted ? "Waiting for others…" : "Type a one-word clue…";

      const timerEl = $("clue-timer");
      timerEl.textContent = `⏱ ${g.clueSecondsLeft}s`;
      timerEl.classList.toggle("urgent", g.clueSecondsLeft <= 5);
    }

    // Imposter guess panel
    const showImposterPanel = g.youAreImposter && !g.youAreEliminated && (state.phase === "clue" || state.phase === "voting") && !g.winner;
    $("imposter-panel").classList.toggle("hidden", !showImposterPanel);
    $("imposter-hint").classList.toggle("hidden", !g.imposterHint);
    $("imposter-hint").textContent = g.imposterHint ? `💡 Hint: ${g.imposterHint}` : "";

    $("last-guess-note").textContent = g.lastGuess || "";

    if (isHost) {
      $("btn-toggle-hints").textContent = `🔎 Imposter Hints: ${g.hintsEnabled ? "On" : "Off"}`;
    }

    // Voting phase
    const inVoting = state.phase === "voting";
    $("voting-phase").classList.toggle("hidden", !inVoting);
    if (inVoting) {
      $("vote-progress").textContent = `${g.votesCount}/${g.activeCount} voted`;
      const votables = state.players.filter((p) => !p.eliminated && !p.isYou);
      $("vote-list").innerHTML = votables.map((p) => {
        const sel = g.yourVoteTargetId === p.id ? " selected" : "";
        return `<li class="${sel}" data-id="${p.id}">${escapeHtml(p.name)}</li>`;
      }).join("");
      const disabled = g.youVoted || g.youAreEliminated;
      document.querySelectorAll("#vote-list li").forEach((li) => {
        if (disabled) { li.style.opacity = "0.6"; li.style.cursor = "default"; return; }
        li.addEventListener("click", async () => {
          $("vote-error").textContent = "";
          try {
            await apiPost(authed("vote"), { playerId: session.playerId, token: session.token, targetId: li.dataset.id });
          } catch (err) {
            $("vote-error").textContent = err.message;
          }
        });
      });
    }

    // Reveal phase
    const inReveal = state.phase === "reveal";
    $("reveal-phase").classList.toggle("hidden", !inReveal);
    if (inReveal && g.reveal) {
      const r = g.reveal;
      if (r.eliminatedId) {
        $("reveal-title").textContent = `${r.eliminatedName} was voted out!`;
        $("reveal-body").textContent = r.eliminatedWasImposter
          ? `${r.eliminatedName} WAS an imposter!`
          : `${r.eliminatedName} was NOT an imposter.`;
      } else {
        $("reveal-title").textContent = "No one was eliminated";
        $("reveal-body").textContent = r.reason && r.winner ? "" : "The vote was tied.";
      }
      if (r.winner) {
        $("reveal-body").textContent += ` ${r.reason}`;
      }
    }

    // Players panel
    $("game-players").innerHTML = state.players.map((p) => playerLi(p)).join("");

    $("host-controls").classList.toggle("hidden", !isHost || state.phase === "gameover");
  }

  function renderGameOver(state) {
    const g = state.game;
    const isHost = state.hostId === state.you;
    const won = g.winner === "imposters" ? "🎭 Imposters Win!" : "🕵️ Crew Wins!";
    $("gameover-title").textContent = won;
    $("gameover-reason").textContent = g.winReason || "";
    $("gameover-word").textContent = `The secret word was: ${g.secretWord}`;
    $("gameover-roles").innerHTML = (g.roles || []).map((r) => {
      const tag = r.isImposter ? "🎭 Imposter" : "🕵️ Crew";
      return `<li>${escapeHtml(r.name)} <span class="muted" style="margin-left:auto">${tag}</span></li>`;
    }).join("");
    $("btn-play-again").classList.toggle("hidden", !isHost);
    $("gameover-wait").classList.toggle("hidden", isHost);
  }

  // ---------------------------------------------------------------------
  // Polling
  // ---------------------------------------------------------------------

  function enterRoom() {
    showView("lobby");
    startPolling();
  }

  function startPolling() {
    stopPolling();
    poll();
    pollTimer = setInterval(poll, 1000);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  async function poll() {
    if (!session) return;
    try {
      const url = `/api/rooms/state?code=${session.roomCode}&playerId=${session.playerId}&token=${session.token}`;
      const state = await apiGet(url);
      render(state);
    } catch (e) {
      clearSession();
      showView("home");
      toast(e.message || "Disconnected from room.");
    }
  }

  function render(state) {
    if (state.phase !== lastPhase) {
      if (state.phase === "lobby") { settingsSynced = false; $("category-checks").dataset.built = ""; }
      lastPhase = state.phase;
    }
    if (state.phase === "lobby") {
      showView("lobby");
      renderLobby(state);
    } else if (state.phase === "gameover") {
      showView("gameover");
      renderGameOver(state);
    } else {
      showView("game");
      renderGame(state);
    }
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------

  if (session) {
    enterRoom();
  } else {
    showView("home");
  }
})();
