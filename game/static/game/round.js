(function () {
  function getCookie(name) {
    const cookieValue = document.cookie
      .split(";")
      .map(function (part) {
        return part.trim();
      })
      .find(function (part) {
        return part.startsWith(name + "=");
      });

    if (!cookieValue) {
      return "";
    }

    return decodeURIComponent(cookieValue.slice(name.length + 1));
  }

  function csrfToken(root) {
    const inlineToken = root.querySelector("input[name='csrfmiddlewaretoken']");
    if (inlineToken && inlineToken.value) {
      return inlineToken.value;
    }

    return getCookie("csrftoken");
  }

  async function postJson(root, url, payload) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(root),
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify(payload),
    });

    let body = {};
    try {
      body = await response.json();
    } catch (_error) {
      body = {};
    }

    return { response: response, body: body };
  }

  function estimateServerNow(snapshot) {
    if (!snapshot || !snapshot.server_now) {
      return null;
    }

    const baselineServerMs = new Date(snapshot.server_now).getTime();
    const baselineClientMs = snapshot._receivedAtMs || Date.now();
    return baselineServerMs + (Date.now() - baselineClientMs);
  }

  function formatCountdown(snapshot, deadlineAt) {
    const estimatedNowMs = estimateServerNow(snapshot);
    if (!estimatedNowMs || !deadlineAt) {
      return "";
    }

    const remainingMs = Math.max(0, new Date(deadlineAt).getTime() - estimatedNowMs);
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    if (remainingSeconds === 1) {
      return "1 second left";
    }

    return `${remainingSeconds} seconds left`;
  }

  function renderScores(root, snapshot) {
    const resultsRoot = root.querySelector("[data-round-results]");
    const scoreList = root.querySelector("[data-score-list]");
    if (!resultsRoot || !scoreList) {
      return;
    }

    const roundBody = snapshot.current_round || {};
    if (roundBody.phase !== "locked") {
      resultsRoot.hidden = true;
      scoreList.replaceChildren();
      return;
    }

    const players = Array.isArray(snapshot.players) ? snapshot.players : [];
    resultsRoot.hidden = false;
    scoreList.replaceChildren();
    players.forEach(function (player) {
      const item = document.createElement("li");
      item.className = "player-roster-item";
      item.textContent = `${player.name}: ${player.score} pts`;
      scoreList.appendChild(item);
    });
  }

  function renderControls(root, snapshot) {
    const controlsRoot = root.querySelector("[data-round-controls]");
    if (!controlsRoot) {
      return;
    }

    const roundBody = snapshot.current_round || {};
    const pauseButton = controlsRoot.querySelector('[data-round-control="pause"]');
    const resumeButton = controlsRoot.querySelector('[data-round-control="resume"]');
    const skipButton = controlsRoot.querySelector('[data-round-control="skip"]');
    const restartButton = controlsRoot.querySelector('[data-round-control="restart"]');
    const isPaused = roundBody.phase === "paused";
    const isLocked = roundBody.phase === "locked";

    if (pauseButton) {
      pauseButton.hidden = isPaused || isLocked;
      pauseButton.disabled = isPaused || isLocked;
    }
    if (resumeButton) {
      resumeButton.hidden = !isPaused || isLocked;
      resumeButton.disabled = !isPaused || isLocked;
    }
    if (skipButton) {
      skipButton.hidden = isLocked;
      skipButton.disabled = isLocked;
    }
    if (restartButton) {
      restartButton.hidden = false;
      restartButton.disabled = false;
    }
  }

  function renderSnapshot(root, snapshot) {
    const roundBody = snapshot.current_round || {};
    const statusNode = root.querySelector("[data-round-status]");
    const countdownNode = root.querySelector("[data-round-countdown]");
    const answerStateNode = root.querySelector("[data-viewer-answer]");
    const optionsRoot = root.querySelector("[data-answer-options]");
    const viewerAnswer = roundBody.viewer_answer;

    if (!statusNode || !countdownNode || !answerStateNode || !optionsRoot) {
      return;
    }

    renderScores(root, snapshot);
    renderControls(root, snapshot);

    if (roundBody.phase === "paused") {
      countdownNode.textContent = "Paused";
      statusNode.textContent = "Round paused.";
      if (viewerAnswer) {
        optionsRoot.hidden = true;
        answerStateNode.hidden = false;
        answerStateNode.textContent = `Answer locked: ${viewerAnswer.selected_artist}. Waiting for the round to resume or finish.`;
      } else {
        optionsRoot.hidden = false;
        answerStateNode.hidden = true;
      }
      root.querySelectorAll("[data-answer-option]").forEach(function (button) {
        button.disabled = true;
      });
      return;
    }

    countdownNode.textContent = formatCountdown(snapshot, roundBody.deadline_at);

    if (roundBody.phase === "locked") {
      optionsRoot.hidden = true;
      answerStateNode.hidden = false;
      statusNode.textContent = "Round locked.";
      if (viewerAnswer && roundBody.track) {
        answerStateNode.textContent = `Your answer: ${viewerAnswer.selected_artist}. Correct artist: ${roundBody.track.artist}.`;
      } else if (roundBody.track) {
        answerStateNode.textContent = `Correct artist: ${roundBody.track.artist}.`;
      }
      return;
    }

    root.querySelectorAll("[data-answer-option]").forEach(function (button) {
      button.disabled = false;
    });

    if (viewerAnswer) {
      optionsRoot.hidden = true;
      answerStateNode.hidden = false;
      statusNode.textContent = "Your answer is locked.";
      answerStateNode.textContent = `Answer locked: ${viewerAnswer.selected_artist}. Waiting for the round to close.`;
      return;
    }

    optionsRoot.hidden = false;
    answerStateNode.hidden = true;
    statusNode.textContent = `Round ${roundBody.index} is live. Pick once.`;
  }

  async function pollSnapshot(root) {
    let currentEtag = "";
    let latestSnapshot = null;
    let latestPollRequestId = 0;

    function setLatestSnapshot(snapshot) {
      if (!snapshot) {
        return;
      }

      latestSnapshot = snapshot;
      root._latestRoundSnapshot = snapshot;
    }

    async function runPoll(forceFresh) {
      const requestId = ++latestPollRequestId;
      const requestStartedAtMs = Date.now();
      const headers = {};
      if (currentEtag && !forceFresh) {
        headers["If-None-Match"] = currentEtag;
      }

      const url = new URL(root.dataset.stateUrl, window.location.origin);
      if (forceFresh) {
        url.searchParams.set("refresh", String(Date.now()));
      }

      const response = await fetch(url.toString(), {
        credentials: "same-origin",
        headers: headers,
        cache: "no-store",
      });

      if (requestId !== latestPollRequestId) {
        return;
      }

      if (root._roundControlMutationAtMs && requestStartedAtMs < root._roundControlMutationAtMs && !forceFresh) {
        return;
      }

      if (response.status === 304) {
        const snapshot = root._latestRoundSnapshot || latestSnapshot;
        if (snapshot) {
          renderSnapshot(root, snapshot);
        }
        return;
      }

      if (!response.ok) {
        return;
      }

      currentEtag = response.headers.get("ETag") || currentEtag;
      const snapshot = await response.json();
      snapshot._receivedAtMs = Date.now();
      setLatestSnapshot(snapshot);
      renderSnapshot(root, snapshot);
    }

    await runPoll();
    window.setInterval(runPoll, 1000);
    root._refreshRoundSnapshot = function () {
      return runPoll(true);
    };
  }

  function bindAnswerButtons(root) {
    if (!root.dataset.answerUrl) {
      return;
    }

    root.querySelectorAll("[data-answer-option]").forEach(function (button) {
      button.addEventListener("click", async function () {
        const statusNode = root.querySelector("[data-round-status]");
        const result = await postJson(root, root.dataset.answerUrl, { artist: button.value });
        if (!statusNode) {
          return;
        }

        if (!result.response.ok) {
          statusNode.textContent = result.body.error?.message || "Answer submission failed.";
          return;
        }

        statusNode.textContent = "Your answer is locked.";
      });
    });
  }

  function bindControlButtons(root) {
    const controls = {
      pause: root.dataset.pauseUrl,
      resume: root.dataset.resumeUrl,
      skip: root.dataset.skipUrl,
      restart: root.dataset.restartUrl,
    };
    if (!controls.pause && !controls.resume && !controls.skip && !controls.restart) {
      return;
    }

    let controlRequestInFlight = false;

    function reloadRoundPage() {
      const url = new URL(window.location.href);
      url.searchParams.set("sync", String(Date.now()));
      window.location.assign(url.toString());
    }

    function applyControlSnapshot(snapshot) {
      if (!snapshot || !snapshot.current_round) {
        return false;
      }

      root._roundControlMutationAtMs = Date.now();
      root._latestRoundSnapshot = {
        ...snapshot,
        _receivedAtMs: root._roundControlMutationAtMs,
      };
      renderSnapshot(root, root._latestRoundSnapshot);
      return true;
    }

    function setControlButtonsDisabled(disabled) {
      root.querySelectorAll("[data-round-control]").forEach(function (controlButton) {
        if (disabled) {
          controlButton.dataset.pendingDisabled = "true";
          controlButton.disabled = true;
          return;
        }

        if (controlButton.dataset.pendingDisabled === "true") {
          delete controlButton.dataset.pendingDisabled;
          controlButton.disabled = false;
        }
      });
    }

    root.querySelectorAll("[data-round-control]").forEach(function (button) {
      if (button.form) {
        return;
      }

      button.addEventListener("click", async function () {
        if (controlRequestInFlight) {
          return;
        }

        const action = button.dataset.roundControl;
        const url = controls[action];
        const statusNode = root.querySelector("[data-round-status]");
        if (!url || !statusNode) {
          return;
        }

        controlRequestInFlight = true;
        setControlButtonsDisabled(true);

        try {
          const result = await postJson(root, url, {});
          if (!result.response.ok) {
            statusNode.textContent = result.body.error?.message || "Round control failed.";
            return;
          }

          const appliedServerSnapshot = applyControlSnapshot(result.body.snapshot);

          if (action === "pause") {
            statusNode.textContent = "Round paused.";
            if (!appliedServerSnapshot && root._latestRoundSnapshot && root._latestRoundSnapshot.current_round) {
              const pausedAt = new Date().toISOString();
              root._roundControlMutationAtMs = Date.now();
              root._latestRoundSnapshot.current_round.phase = "paused";
              root._latestRoundSnapshot.current_round.paused_at = pausedAt;
              root._latestRoundSnapshot.server_now = pausedAt;
              root._latestRoundSnapshot._receivedAtMs = root._roundControlMutationAtMs;
              renderSnapshot(root, root._latestRoundSnapshot);
            }
          } else if (action === "resume") {
            statusNode.textContent = "Round resumed.";
            if (!appliedServerSnapshot && root._latestRoundSnapshot && root._latestRoundSnapshot.current_round) {
              const roundBody = root._latestRoundSnapshot.current_round;
              const resumedAtMs = Date.now();
              root._roundControlMutationAtMs = resumedAtMs;
              const pausedAtMs = roundBody.paused_at ? new Date(roundBody.paused_at).getTime() : null;
              const deadlineAtMs = roundBody.deadline_at ? new Date(roundBody.deadline_at).getTime() : null;

              if (pausedAtMs && deadlineAtMs) {
                roundBody.deadline_at = new Date(deadlineAtMs + Math.max(0, resumedAtMs - pausedAtMs)).toISOString();
              }

              roundBody.phase = "active";
              roundBody.paused_at = null;
              root._latestRoundSnapshot.server_now = new Date(resumedAtMs).toISOString();
              root._latestRoundSnapshot._receivedAtMs = resumedAtMs;
              renderSnapshot(root, root._latestRoundSnapshot);
            }
          } else if (action === "skip") {
            statusNode.textContent = "Round skipped.";
          } else if (action === "restart") {
            statusNode.textContent = "Round restarted.";
          }

          reloadRoundPage();
          return;

          if (typeof root._refreshRoundSnapshot === "function") {
            await root._refreshRoundSnapshot();
          }
        } finally {
          controlRequestInFlight = false;
          setControlButtonsDisabled(false);
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-round-state-root]").forEach(function (root) {
      if (!root.dataset.stateUrl) {
        return;
      }

      bindAnswerButtons(root);
      bindControlButtons(root);
      pollSnapshot(root);
    });
  });
})();