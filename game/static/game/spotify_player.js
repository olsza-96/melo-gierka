(function () {
  let spotifySdkPromise;

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

  function getCsrfToken(root) {
    const inlineToken = root.querySelector("input[name='csrfmiddlewaretoken']");
    if (inlineToken && inlineToken.value) {
      return inlineToken.value;
    }

    const formToken = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (formToken && formToken.value) {
      return formToken.value;
    }

    return getCookie("csrftoken");
  }

  function ensureSpotifySdk() {
    if (spotifySdkPromise) {
      return spotifySdkPromise;
    }

    spotifySdkPromise = new Promise(function (resolve) {
      if (window.Spotify) {
        resolve();
        return;
      }

      if (!document.querySelector("script[data-spotify-sdk]")) {
        const script = document.createElement("script");
        script.src = "https://sdk.scdn.co/spotify-player.js";
        script.async = true;
        script.dataset.spotifySdk = "true";
        document.head.appendChild(script);
      }

      window.onSpotifyWebPlaybackSDKReady = function () {
        resolve();
      };
    });

    return spotifySdkPromise;
  }

  async function postJson(url, payload) {
    const csrfToken = getCsrfToken(document);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
        "X-CSRFToken": csrfToken,
      },
      credentials: "same-origin",
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

  function setStatus(root, message, isError) {
    const status = root.querySelector("[data-playback-status]");
    if (!status) {
      return;
    }

    status.textContent = message;
    status.dataset.error = isError ? "true" : "false";
  }

  function setDiagnostics(root, payload) {
    const output = root.querySelector("[data-playback-diagnostics-output]");
    if (!output) {
      return;
    }

    output.hidden = false;
    output.textContent = JSON.stringify(payload, null, 2);
  }

  async function initializePlayer(root) {
    const blockedReason = root.dataset.blockedReason;
    const token = root.dataset.accessToken;
    if (blockedReason) {
      setStatus(root, blockedReason, true);
      return;
    }

    if (!token) {
      setStatus(root, "Reconnect Spotify before preparing browser playback.", true);
      return;
    }

    await ensureSpotifySdk();

    const prepareButton = root.querySelector("[data-playback-prepare]");
    const diagnosticsButton = root.querySelector("[data-playback-diagnostics]");
    const startButton = root.querySelector("[data-start-round]");
    const diagnosticsUrl = root.dataset.diagnosticsUrl;
    const readyUrl = root.dataset.readyUrl;
    const startUrl = root.dataset.startUrl;

    const player = new window.Spotify.Player({
      name: "melo-gierka Host Player",
      getOAuthToken: function (callback) {
        callback(token);
      },
      volume: 0.8,
    });

    player.addListener("ready", async function (_payload) {
      const deviceId = _payload.device_id;
      if (!readyUrl) {
        return;
      }

      const result = await postJson(readyUrl, { device_id: deviceId });
      if (!result.response.ok) {
        setStatus(root, result.body.error?.message || "Spotify readiness could not be saved.", true);
        return;
      }

      setStatus(root, "Spotify browser player is ready. You can start the round.", false);
    });

    player.addListener("not_ready", function () {
      setStatus(root, "Spotify browser player is not ready yet.", true);
    });

    ["initialization_error", "account_error", "playback_error"].forEach(function (eventName) {
      player.addListener(eventName, function (event) {
        setStatus(root, event.message || "Spotify playback failed.", true);
      });
    });

    player.addListener("authentication_error", function () {
      setStatus(root, "Spotify login expired or is missing playback permissions. Reconnect Spotify and reload the host lobby.", true);
    });

    player.addListener("autoplay_failed", function () {
      setStatus(root, "Spotify playback needs browser activation before it can start.", true);
    });

    const connectPlayer = async function () {
      await player.activateElement();
      setStatus(root, "Connecting Spotify browser player…", false);
      await player.connect();
    };

    if (prepareButton) {
      prepareButton.addEventListener("click", async function () {
        try {
          await connectPlayer();
        } catch (_error) {
          setStatus(root, "Spotify browser playback could not be activated in this tab.", true);
        }
      });
    } else if (root.dataset.autoConnect === "true") {
      try {
        await player.connect();
      } catch (_error) {
        setStatus(root, "Spotify browser playback could not reconnect automatically.", true);
      }
    }

    if (startButton && startUrl) {
      startButton.addEventListener("click", async function () {
        setStatus(root, "Starting round 1…", false);
        const result = await postJson(startUrl, {});
        if (!result.response.ok) {
          setStatus(root, result.body.error?.message || "Round start failed.", true);
          return;
        }
        window.location.href = result.body.redirect_url || window.location.href;
      });
    }

    if (diagnosticsButton && diagnosticsUrl) {
      diagnosticsButton.addEventListener("click", async function () {
        setStatus(root, "Running Spotify diagnostics…", false);
        const response = await fetch(diagnosticsUrl, { credentials: "same-origin" });
        let body = {};
        try {
          body = await response.json();
        } catch (_error) {
          body = { error: { message: "Diagnostics response was not valid JSON." } };
        }

        setDiagnostics(root, body);
        if (!response.ok) {
          setStatus(root, body.error?.message || "Spotify diagnostics failed.", true);
          return;
        }

        setStatus(root, "Spotify diagnostics loaded below.", false);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-spotify-player-root]").forEach(function (root) {
      initializePlayer(root);
    });
  });
})();