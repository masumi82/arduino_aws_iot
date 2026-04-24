const commandModule = (() => {
  const STATES = { IDLE: "idle", SENDING: "sending", WAITING: "waiting" };
  let state = STATES.IDLE;
  let pendingCmd = null;  // { type, value, commandId, timer }

  function init() {
    document.getElementById("btn-led-on").addEventListener("click",  () => sendCommand("setLed", true));
    document.getElementById("btn-led-off").addEventListener("click", () => sendCommand("setLed", false));
    document.getElementById("btn-interval").addEventListener("click", () => {
      const ms = parseInt(document.getElementById("interval-slider").value, 10);
      sendCommand("setInterval", ms);
    });

    const slider = document.getElementById("interval-slider");
    slider.addEventListener("input", () => {
      document.getElementById("interval-preview").textContent = slider.value + " ms";
    });
  }

  async function sendCommand(type, value) {
    if (state !== STATES.IDLE) return;

    const commandId = crypto.randomUUID();
    const topic = `device/${CONFIG.deviceId}/cmd`;
    const payload = { commandId, type, value };

    _setState(STATES.SENDING);
    const sent = mqttClientModule.publish(topic, payload);
    if (!sent) {
      _showWarning("MQTT 未接続のため送信できませんでした");
      _setState(STATES.IDLE);
      return;
    }

    pendingCmd = { type, value, commandId };
    _setState(STATES.WAITING);

    pendingCmd.timer = setTimeout(() => {
      _showWarning("コマンドが 10 秒以内に反映されませんでした");
      pendingCmd = null;
      _setState(STATES.IDLE);
    }, 10000);
  }

  function onTelemetryUpdate(frame) {
    if (state !== STATES.WAITING || !pendingCmd) return;

    let confirmed = false;
    if (pendingCmd.type === "setLed" && frame.ledState === pendingCmd.value) {
      confirmed = true;
    } else if (pendingCmd.type === "setInterval" && frame.intervalMs === pendingCmd.value) {
      confirmed = true;
    }

    if (confirmed) {
      clearTimeout(pendingCmd.timer);
      pendingCmd = null;
      _hideWarning();
      _setState(STATES.IDLE);
    }
  }

  function _setState(newState) {
    state = newState;
    const indicator = document.getElementById("cmd-indicator");
    if (indicator) indicator.hidden = (newState === STATES.IDLE);
  }

  function _showWarning(msg) {
    const el = document.getElementById("cmd-warning");
    if (el) { el.textContent = msg; el.hidden = false; }
    setTimeout(() => { if (el) el.hidden = true; }, 5000);
  }

  function _hideWarning() {
    const el = document.getElementById("cmd-warning");
    if (el) el.hidden = true;
  }

  return { init, onTelemetryUpdate };
})();
