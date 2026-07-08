const DEVICE_ID = "NESTR-HIVE-001";
const API_BASE = "http://localhost:5000"; // Change to Raspberry Pi IP address if needed

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function updateDashboard(data) {
  const weight = Number(data.weight_kg || 0);
  const temperature = Number(data.temperature_c || 0);
  const humidity = Number(data.humidity_percent || 0);
  const condition = data.condition || {
    status: "No Data",
    alerts: [],
    harvest_ready: false,
    readiness_percent: 0
  };

  setText("weight", `${weight.toFixed(2)} kg`);
  setText("temperature", `${temperature.toFixed(1)} °C`);
  setText("humidity", `${humidity.toFixed(1)} %`);
  setText("status", condition.status || "Unknown");
  setText("timestamp", data.timestamp || "No timestamp received yet.");

  const alertsEl = document.getElementById("alerts");
  alertsEl.innerHTML = "";

  const alerts = condition.alerts || [];
  if (alerts.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No active alerts. Hive condition is within prototype threshold.";
    alertsEl.appendChild(li);
  } else {
    alerts.forEach(alert => {
      const li = document.createElement("li");
      li.textContent = alert;
      alertsEl.appendChild(li);
    });
  }

  const readiness = Number(condition.readiness_percent || Math.min((weight / 8) * 100, 100));
  document.getElementById("harvestBar").style.width = `${readiness}%`;
  setText(
    "harvestText",
    condition.harvest_ready
      ? "Harvest potential detected. Manual validation is required before harvesting."
      : `Estimated readiness: ${readiness.toFixed(0)}%`
  );
}

async function fetchLatest() {
  try {
    const response = await fetch(`${API_BASE}/api/hive-data/${DEVICE_ID}/latest`);
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && body.error) {
          detail = body.error;
        }
      } catch (parseError) {
        // Response body was not JSON; keep the HTTP status as the detail.
      }
      throw new Error(`Gateway returned an error: ${detail}`);
    }
    const data = await response.json();
    updateDashboard(data);
  } catch (error) {
    console.error(error);
    setText("status", "Gateway Offline");
    setText("harvestText", "Unable to connect to Raspberry Pi gateway.");
  }
}

fetchLatest();
setInterval(fetchLatest, 10000);
