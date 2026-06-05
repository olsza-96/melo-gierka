(function () {
  function playerCountLabel(count) {
    return count === 1 ? "1 player" : `${count} players`;
  }

  function summaryLabel(count, currentPlayer) {
    if (count === 0) {
      return "Waiting for the first player to join.";
    }

    if (!currentPlayer) {
      return count === 1
        ? "1 player has joined the room."
        : `${count} players have joined the room.`;
    }

    if (count === 1) {
      return `You are the only player in the room so far, ${currentPlayer}.`;
    }

    return `${count} players are in the room, including ${currentPlayer}.`;
  }

  function createPlayerItem(playerName, currentPlayer) {
    const item = document.createElement("li");
    item.className = "player-roster-item";
    item.textContent = playerName;

    if (currentPlayer && playerName === currentPlayer) {
      item.classList.add("player-roster-item-current");
    }

    return item;
  }

  function shouldTransitionToRound(snapshot) {
    return snapshot && snapshot.status === "playing" && snapshot.current_round;
  }

  function transitionToRound(root) {
    const sessionPageUrl = root.dataset.sessionPageUrl || window.location.href;
    const separator = sessionPageUrl.includes("?") ? "&" : "?";
    window.location.assign(`${sessionPageUrl}${separator}round=live`);
  }

  function renderPlayers(root, snapshot) {
    const players = Array.isArray(snapshot.players) ? snapshot.players : [];
    const currentPlayer = root.dataset.currentPlayer || "";
    const playerList = root.querySelector("[data-player-list]");
    const playerCount = root.querySelector("[data-player-count]");
    const summary = root.querySelector("[data-lobby-summary]");
    const terminal = root.querySelector("[data-lobby-terminal]");
    const emptyLabel = root.dataset.emptyLabel || "No players yet.";

    if (!playerList || !playerCount || !summary || !terminal) {
      return;
    }

    terminal.hidden = true;
    terminal.textContent = "";
    playerCount.textContent = playerCountLabel(players.length);
    summary.textContent = summaryLabel(players.length, currentPlayer);
    playerList.replaceChildren();

    if (players.length === 0) {
      const emptyItem = document.createElement("li");
      emptyItem.className = "player-roster-empty";
      emptyItem.textContent = emptyLabel;
      playerList.appendChild(emptyItem);
      return;
    }

    players.forEach(function (player) {
      playerList.appendChild(createPlayerItem(player.name, currentPlayer));
    });
  }

  async function pollLobby(root) {
    let etag = "";

    async function requestSnapshot() {
      const headers = {};
      if (etag) {
        headers["If-None-Match"] = etag;
      }

      const response = await fetch(root.dataset.stateUrl, {
        headers: headers,
        credentials: "same-origin",
      });

      if (response.status === 304) {
        return;
      }

      if (response.status === 404) {
        const terminal = root.querySelector("[data-lobby-terminal]");
        if (terminal) {
          terminal.hidden = false;
          terminal.textContent = "This session is no longer available.";
        }
        return;
      }

      if (!response.ok) {
        return;
      }

      etag = response.headers.get("ETag") || etag;
      const snapshot = await response.json();

      if (shouldTransitionToRound(snapshot)) {
        transitionToRound(root);
        return;
      }

      renderPlayers(root, snapshot);
    }

    await requestSnapshot();
    window.setInterval(requestSnapshot, 1000);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-lobby-state-root]").forEach(function (root) {
      if (root.dataset.stateUrl) {
        pollLobby(root);
      }
    });
  });
})();