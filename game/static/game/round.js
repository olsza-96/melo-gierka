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

  function formatCountdown(serverNow, deadlineAt) {
    if (!serverNow || !deadlineAt) {
      return "";
    }

    const remainingMs = Math.max(0, new Date(deadlineAt).getTime() - new Date(serverNow).getTime());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    if (remainingSeconds === 1) {
      return "1 second left";
    }

    return `${remainingSeconds} seconds left`;
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

    countdownNode.textContent = formatCountdown(snapshot.server_now, roundBody.deadline_at);

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

    async function runPoll() {
      const headers = {};
      if (currentEtag) {
        headers["If-None-Match"] = currentEtag;
      }

      const response = await fetch(root.dataset.stateUrl, {
        credentials: "same-origin",
        headers: headers,
      });
      if (response.status === 304 || !response.ok) {
        return;
      }

      currentEtag = response.headers.get("ETag") || currentEtag;
      renderSnapshot(root, await response.json());
    }

    await runPoll();
    window.setInterval(runPoll, 1000);
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

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-round-state-root]").forEach(function (root) {
      if (!root.dataset.stateUrl) {
        return;
      }

      bindAnswerButtons(root);
      pollSnapshot(root);
    });
  });
})();