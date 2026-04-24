const telemetryModule = (() => {
  let lastSeqNo = -1;
  let chart = null;

  function init() {
    const ctx = document.getElementById("sensor-chart").getContext("2d");
    chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "温度 (°C)",
            data: [],
            borderColor: "#e74c3c",
            backgroundColor: "rgba(231,76,60,0.1)",
            tension: 0.3,
            yAxisID: "yTemp",
          },
          {
            label: "湿度 (%)",
            data: [],
            borderColor: "#3498db",
            backgroundColor: "rgba(52,152,219,0.1)",
            tension: 0.3,
            yAxisID: "yHumid",
          },
        ],
      },
      options: {
        animation: false,
        scales: {
          yTemp:  { position: "left",  min: 10, max: 40, title: { display: true, text: "°C" } },
          yHumid: { position: "right", min: 10, max: 90, title: { display: true, text: "%" } },
        },
      },
    });

    const topic = `device/${CONFIG.deviceId}/telemetry`;
    mqttClientModule.subscribe(topic, onTelemetry);
  }

  function onTelemetry(frame) {
    // Detect Arduino reboot: sequenceNo resets to 0 after a high value
    if (lastSeqNo > 100 && frame.sequenceNo < lastSeqNo - 100) {
      console.info("[telemetry] Arduino reboot detected, resetting sequenceNo");
      lastSeqNo = -1;
    }
    if (frame.sequenceNo <= lastSeqNo) return;  // duplicate suppression
    lastSeqNo = frame.sequenceNo;

    document.getElementById("temp-value").textContent =
      frame.temperatureC != null ? frame.temperatureC.toFixed(1) : "--";
    document.getElementById("humid-value").textContent =
      frame.humidityPct != null ? frame.humidityPct.toFixed(1) : "--";
    document.getElementById("led-state").textContent =
      frame.ledState ? "ON" : "OFF";
    document.getElementById("interval-value").textContent =
      frame.intervalMs != null ? frame.intervalMs : "--";
    document.getElementById("last-received-at").textContent =
      frame.timestamp ? new Date(frame.timestamp).toLocaleString() : "--";

    commandModule.onTelemetryUpdate(frame);

    const timeLabel = new Date(frame.timestamp || Date.now()).toLocaleTimeString();
    const MAX_POINTS = 30;
    chart.data.labels.push(timeLabel);
    chart.data.datasets[0].data.push(frame.temperatureC);
    chart.data.datasets[1].data.push(frame.humidityPct);
    if (chart.data.labels.length > MAX_POINTS) {
      chart.data.labels.shift();
      chart.data.datasets.forEach(ds => ds.data.shift());
    }
    chart.update("none");
  }

  return { init };
})();
