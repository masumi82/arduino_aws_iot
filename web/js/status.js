const statusModule = (() => {
  const STATES = ["online", "degraded", "offline", "pending"];

  function init() {
    const topic = `device/${CONFIG.deviceId}/status`;
    mqttClientModule.subscribe(topic, onStatus);
    _setBadge("pending");
  }

  function onStatus(payload) {
    const state = payload && payload.state;
    if (STATES.includes(state)) _setBadge(state);
  }

  function setPending(yes) {
    if (yes) _setBadge("pending");
  }

  function _setBadge(state) {
    const badge = document.getElementById("status-badge");
    if (!badge) return;
    STATES.forEach(s => badge.classList.remove(`status-${s}`));
    badge.classList.add(`status-${state}`);
    badge.textContent = state.charAt(0).toUpperCase() + state.slice(1);
  }

  return { init, setPending };
})();
