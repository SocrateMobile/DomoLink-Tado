/**
 * DomoLink-Tado — Panneau Tactile Haute Résolution & Lovelace Card (v1.1.3)
 * 
 * Nouveautés majeures :
 * 1. Gros curseur vertical blanc tactile qui glisse de haut en bas le long de la règle de 5° à 30°C.
 * 2. Bouton AUTHENTIFICATION bien visible dans le bandeau supérieur et dans l'onglet Paramètres.
 * 3. Icônes vectorielles Tado distinctes (tête VA, thermostat RU/ST, sonde SU, relais chaudière, bridge)
 *    fiablement associées à chaque équipement et pièce.
 * 4. Dégradé dynamique thermique du bas (température mesurée) vers le haut (température consigne).
 * 5. Zéro scintillement, gestion des étiquettes (tags) et carte Lovelace standard.
 */

/* =========================================================================
 * 🎨 INTERPOLATION COULEUR & DÉGRADÉS DYNAMIQUES
 * ========================================================================= */
function interpolateColor(t) {
  const val = parseFloat(t);
  if (isNaN(val)) return { r: 100, g: 116, b: 139 };
  const stops = [
    { temp: 10.0, r: 2, g: 132, b: 199 },   // #0284c7 (Bleu froid)
    { temp: 16.0, r: 5, g: 150, b: 105 },   // #059669 (Émeraude éco)
    { temp: 18.0, r: 22, g: 163, b: 74 },   // #16a34a (Vert doux)
    { temp: 19.5, r: 217, g: 119, b: 6 },   // #d97706 (Ambre confort)
    { temp: 21.5, r: 234, g: 88, b: 12 },   // #ea580c (Orange chaud)
    { temp: 24.0, r: 220, g: 38, b: 38 },   // #dc2626 (Rouge corail)
    { temp: 28.0, r: 153, g: 27, b: 27 }    // #991b1b (Crimson)
  ];
  if (val <= stops[0].temp) return { r: stops[0].r, g: stops[0].g, b: stops[0].b };
  if (val >= stops[stops.length - 1].temp) {
    const last = stops[stops.length - 1];
    return { r: last.r, g: last.g, b: last.b };
  }
  for (let i = 0; i < stops.length - 1; i++) {
    const s1 = stops[i];
    const s2 = stops[i + 1];
    if (val >= s1.temp && val <= s2.temp) {
      const factor = (val - s1.temp) / (s2.temp - s1.temp);
      return {
        r: Math.round(s1.r + (s2.r - s1.r) * factor),
        g: Math.round(s1.g + (s2.g - s1.g) * factor),
        b: Math.round(s1.b + (s2.b - s1.b) * factor),
      };
    }
  }
  return { r: 217, g: 119, b: 6 };
}

function cleanRoomName(rawName) {
  if (!rawName) return "";
  let name = String(rawName).replace(/^Tado\s+/i, "").trim();
  const words = name.split(/\s+/);
  if (words.length >= 2 && words.length % 2 === 0) {
    const half = words.length / 2;
    const firstHalf = words.slice(0, half).join(" ");
    const secondHalf = words.slice(half).join(" ");
    if (firstHalf.toLowerCase() === secondHalf.toLowerCase()) {
      return firstHalf;
    }
  }
  return name;
}

function getCardBackgroundStyle(zone) {
  const isOff = zone.state === "off";
  if (isOff) {
    return {
      background: "#192133",
      borderColor: "rgba(255, 255, 255, 0.08)",
      boxShadow: "0 6px 20px rgba(0, 0, 0, 0.25)",
      accentColor: "#64748b",
      glow: "rgba(100, 116, 139, 0.15)",
      rgb: "100, 116, 139",
    };
  }

  // Dégradé du bas vers le haut :
  // En bas : température actuelle mesurée
  // En haut : température cible
  const curColor = interpolateColor(zone.current_temp);
  const tgtColor = interpolateColor(zone.target_num);

  const bg = `linear-gradient(to top, rgba(${curColor.r}, ${curColor.g}, ${curColor.b}, 0.50) 0%, rgba(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}, 0.60) 100%), #131928`;
  const border = `rgba(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}, 0.55)`;
  const shadow = `0 10px 28px rgba(0, 0, 0, 0.4), 0 0 20px rgba(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}, 0.22)`;
  const accent = `rgb(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b})`;
  const glow = `rgba(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}, 0.5)`;

  return {
    background: bg,
    borderColor: border,
    boxShadow: shadow,
    accentColor: accent,
    glow: glow,
    rgb: `${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}`,
  };
}

/* =========================================================================
 * ⚙️ ICÔNES VECTORIELLES STYLISÉES DOMOLINK-TADO
 * ========================================================================= */
function getDeviceTypeCategory(deviceType = "") {
  const dt = String(deviceType).toUpperCase();
  if (dt.startsWith("VA")) return "VALVE";
  if (dt.startsWith("RU") || dt.startsWith("ST") || dt.includes("THERMO")) return "THERMOSTAT";
  if (dt.startsWith("SU") || dt.includes("SENSOR")) return "SENSOR";
  if (dt.startsWith("BU") || dt.startsWith("EK") || dt.startsWith("BR") || dt.includes("BOILER")) return "BOILER";
  if (dt.startsWith("GW") || dt.startsWith("IB") || dt.includes("BRIDGE")) return "BRIDGE";
  return "VALVE";
}

function getValveSvg(size = 38, color = "currentColor") {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="tado-device-icon icon-valve">
    <!-- Tête thermostatique cylindrique Tado -->
    <rect x="14" y="11" width="27" height="26" rx="7" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>
    <path d="M7 15H14V33H7C5.89543 33 5 32.1046 5 31V17C5 15.8954 5.89543 15 7 15Z" fill="${color}" fill-opacity="0.38" stroke="${color}" stroke-width="2"/>
    <line x1="10.5" y1="17" x2="10.5" y2="31" stroke="${color}" stroke-width="1.5" stroke-dasharray="2 2"/>
    <rect x="22" y="17" width="13" height="14" rx="3" fill="#090d16" stroke="${color}" stroke-width="1.2"/>
    <circle cx="26" cy="22" r="1.2" fill="${color}"/>
    <circle cx="29" cy="22" r="1.2" fill="${color}"/>
    <circle cx="31" cy="22" r="1.2" fill="${color}"/>
    <circle cx="26" cy="26" r="1.2" fill="${color}"/>
    <circle cx="29" cy="26" r="1.2" fill="${color}"/>
    <circle cx="38" cy="24" r="2.5" fill="${color}"/>
  </svg>`;
}

function getThermostatSvg(size = 38, color = "currentColor") {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="tado-device-icon icon-thermostat">
    <!-- Thermostat d'ambiance mural Tado carré galbé -->
    <rect x="7" y="7" width="34" height="34" rx="9" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>
    <circle cx="24" cy="23" r="11" fill="#090d16" stroke="${color}" stroke-width="2"/>
    <circle cx="24" cy="23" r="13" stroke="${color}" stroke-width="1" stroke-dasharray="2 2" opacity="0.65"/>
    <text x="24" y="27" font-size="9" font-family="-apple-system, sans-serif" font-weight="900" fill="${color}" text-anchor="middle">20°</text>
    <circle cx="24" cy="36" r="2" fill="${color}"/>
  </svg>`;
}

function getSensorSvg(size = 38, color = "currentColor") {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="tado-device-icon icon-sensor">
    <!-- Sonde de température et humidité sans fil -->
    <rect x="10" y="10" width="28" height="28" rx="8" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>
    <line x1="17" y1="18" x2="31" y2="18" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
    <line x1="17" y1="23" x2="31" y2="23" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
    <line x1="17" y1="28" x2="26" y2="28" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
    <circle cx="30" cy="28" r="1.5" fill="${color}"/>
  </svg>`;
}

function getBoilerSvg(size = 38, color = "currentColor") {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="tado-device-icon icon-boiler">
    <!-- Boîtier relais chaudière / Extension Kit -->
    <rect x="8" y="8" width="32" height="32" rx="7" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>
    <path d="M24 13C24 13 28.5 18.5 28.5 22.5C28.5 25.5 26.5 28 23.5 28C20 28 17.5 25.5 17.5 22.5C17.5 18.5 22 15 22 15C22 15 21 19 23.5 20.5C26 22 24 13 24 13Z" fill="${color}" fill-opacity="0.85"/>
    <rect x="12" y="33" width="24" height="4" rx="2" fill="${color}" fill-opacity="0.4"/>
    <circle cx="16" cy="35" r="1" fill="#ffffff"/>
    <circle cx="24" cy="35" r="1" fill="#ffffff"/>
    <circle cx="32" cy="35" r="1" fill="#ffffff"/>
  </svg>`;
}

function getBridgeSvg(size = 38, color = "currentColor") {
  return `<svg width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" class="tado-device-icon icon-bridge">
    <!-- Passerelle Internet Bridge -->
    <rect x="9" y="12" width="30" height="24" rx="7" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>
    <circle cx="17" cy="24" r="2.5" fill="${color}"/>
    <circle cx="24" cy="24" r="2.5" fill="${color}"/>
    <circle cx="31" cy="24" r="2.5" fill="${color}"/>
    <path d="M19 36H29V39H19V36Z" fill="${color}" fill-opacity="0.45"/>
  </svg>`;
}

function getDeviceSvg(deviceType = "VA", size = 38, color = "currentColor") {
  const cat = getDeviceTypeCategory(deviceType);
  if (cat === "THERMOSTAT") return getThermostatSvg(size, color);
  if (cat === "SENSOR") return getSensorSvg(size, color);
  if (cat === "BOILER") return getBoilerSvg(size, color);
  if (cat === "BRIDGE") return getBridgeSvg(size, color);
  return getValveSvg(size, color);
}

/* =========================================================================
 * 📱 COMPOSANT PRINCIPAL : DOMOLINK-TADO
 * ========================================================================= */
class DomolinkTadoPanel extends HTMLElement {
  constructor() {
    super();
    this._initialized = false;
    this._activeTab = "rooms";
    this._selectedLabel = "__ALL__";
    this._activeModalZoneId = null;
    this._activeModalZone = null;
    this._cursorDragActive = false;
    this._selectedDuration = "NEXT_TIME_BLOCK";
    this._cardsMap = new Map();
    this._sliderDebounceTimer = null;
    this._allLabels = new Set();
    this._settingsDraft = {};
  }

  set panel(panel) {
    this._panel = panel;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._renderLayout();
    }
    this._updateData();
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 6;
  }

  connectedCallback() {
    if (this._hass && !this._initialized) {
      this._initialized = true;
      this._renderLayout();
      this._updateData();
    }
  }

  _extractData() {
    if (!this._hass) return { zones: [], allDevices: [], weather: {}, activeCount: 0, labels: [] };
    const states = this._hass.states;

    const climateKeys = Object.keys(states).filter((k) =>
      k.startsWith("climate.") && (k.includes("domolink_tado") || k.includes("tado"))
    );

    const zones = [];
    const allDevices = [];
    let activeCount = 0;
    const labelsSet = new Set();
    const valveModes = {};

    for (const key of climateKeys) {
      const entity = states[key];
      if (!entity) continue;

      const attrs = entity.attributes || {};
      const zoneId = attrs.zone_id || key;
      const name = cleanRoomName(attrs.friendly_name) || key;
      const currentTemp = attrs.current_temperature != null ? parseFloat(attrs.current_temperature).toFixed(1) : "--";
      const targetTemp = attrs.temperature != null ? parseFloat(attrs.temperature).toFixed(1) : (entity.state === "off" ? "Off" : "--");
      const humidity = attrs.current_humidity != null ? `${attrs.current_humidity}%` : "--%";
      const heatingPower = attrs.heating_power_percentage != null ? Math.round(attrs.heating_power_percentage) : 0;
      const isHeating = heatingPower > 0 || attrs.hvac_action === "heating";
      if (isHeating) activeCount++;

      const isOverlay = attrs.is_overlay_active || entity.state === "heat";
      const openWindow = attrs.open_window_detected || false;
      const devices = attrs.devices || [];
      const childLocked = devices.some((d) => d.child_lock === true);
      const labels = Array.isArray(attrs.labels) ? attrs.labels : [];
      labels.forEach((l) => labelsSet.add(l));

      if (attrs.valve_calibration_modes && typeof attrs.valve_calibration_modes === "object") {
        Object.assign(valveModes, attrs.valve_calibration_modes);
      }

      const primaryDevice = devices[0] || {};
      const primaryDeviceType = attrs.device_type || primaryDevice.device_type || primaryDevice.type || primaryDevice.deviceType || (name.toLowerCase().includes("thermostat") ? "RU01" : "VA01");

      for (const d of devices) {
        allDevices.push({
          serial: d.serial || d.serial_number || d.serialNo || "N/A",
          device_type: d.device_type || d.type || d.deviceType || "VA01",
          current_firmware: d.current_firmware_version || d.firmware || "v98.1",
          battery_state: d.battery_state || d.battery || "NORMAL",
          battery_percentage: d.battery_percentage != null ? `${d.battery_percentage}%` : (d.battery_state === "NORMAL" || d.battery === "NORMAL" ? "100%" : "Faible"),
          connection_state: d.connection_state || "CONNECTED",
          zone_name: name,
          zone_id: zoneId,
          offset: d.offset != null ? parseFloat(d.offset) : 0.0,
          raw_inside_temperature: attrs.raw_inside_temperature,
        });
      }

      zones.push({
        entity_id: key,
        zone_id: zoneId,
        name: name,
        state: entity.state,
        current_temp: currentTemp,
        target_temp: targetTemp,
        target_num: parseFloat(attrs.temperature) || 20.0,
        humidity: humidity,
        heating_power: heatingPower,
        is_heating: isHeating,
        is_overlay: isOverlay,
        open_window: openWindow,
        child_locked: childLocked,
        labels: labels,
        temp_sensors: Array.isArray(attrs.zone_temp_sensors)
          ? attrs.zone_temp_sensors
          : (attrs.zone_temp_sensors ? [attrs.zone_temp_sensors] : []),
        raw_inside_temp: attrs.raw_inside_temperature,
        devices: devices,
        primary_device_type: primaryDeviceType,
      });
    }

    const outdoorSensor = Object.keys(states).find(
      (k) => k.includes("domolink_tado") && k.includes("outdoor_temp")
    );
    const outdoorVal = outdoorSensor && states[outdoorSensor]?.state;
    const outdoorTemp = outdoorVal && outdoorVal !== "unavailable" ? `${parseFloat(outdoorVal).toFixed(1)}°` : "--°";

    // Extraction télémétrie Quota & Requêtes API Tado
    let rateLimit = null;
    for (const key of climateKeys) {
      const entity = states[key];
      if (entity?.attributes?.rate_limit && (entity.attributes.rate_limit.limit != null || entity.attributes.rate_limit.remaining != null || entity.attributes.rate_limit.used != null)) {
        rateLimit = entity.attributes.rate_limit;
        break;
      }
    }

    if (!rateLimit) {
      const remKey = Object.keys(states).find(
        (k) => k.startsWith("sensor.") && k.includes("tado") && (k.includes("quota_remaining") || k.includes("restant"))
      );
      const limKey = Object.keys(states).find(
        (k) => k.startsWith("sensor.") && k.includes("tado") && (k.includes("quota_limit") || k.includes("plafond"))
      );
      const usedKey = Object.keys(states).find(
        (k) => k.startsWith("sensor.") && k.includes("tado") && (k.includes("quota_used") || k.includes("utilisees"))
      );

      const remVal = remKey && !isNaN(parseInt(states[remKey]?.state, 10)) ? parseInt(states[remKey].state, 10) : null;
      const limVal = limKey && !isNaN(parseInt(states[limKey]?.state, 10)) ? parseInt(states[limKey].state, 10) : null;
      const usedVal = usedKey && !isNaN(parseInt(states[usedKey]?.state, 10)) ? parseInt(states[usedKey].state, 10) : null;

      if (remVal !== null || limVal !== null || usedVal !== null) {
        rateLimit = {
          limit: limVal,
          remaining: remVal,
          used: usedVal,
          reset_seconds: remKey ? states[remKey]?.attributes?.reset_seconds : null,
        };
      }
    }

    const limitNum = rateLimit?.limit ?? 1000;
    const remainingNum = rateLimit?.remaining != null ? Number(rateLimit.remaining) : null;
    let usedNum = rateLimit?.used != null ? Number(rateLimit.used) : null;
    if (usedNum === null && remainingNum !== null && limitNum !== null) {
      usedNum = Math.max(0, limitNum - remainingNum);
    }

    this._allLabels = labelsSet;

    return {
      zones: zones,
      allDevices: allDevices,
      outdoor_temp: outdoorTemp,
      active_count: activeCount,
      labels: Array.from(labelsSet),
      valveModes: valveModes,
      rate_limit: {
        limit: limitNum,
        remaining: remainingNum,
        used: usedNum,
        reset_seconds: rateLimit?.reset_seconds,
      },
    };
  }

  _getTempColor(targetNum, state) {
    if (state === "off" || targetNum === null || isNaN(targetNum)) {
      return {
        bg: "#1e293b",
        accent: "#64748b",
        glow: "rgba(100, 116, 139, 0.3)",
      };
    }
    const c = interpolateColor(targetNum);
    return {
      bg: `rgb(${Math.max(0, c.r - 25)}, ${Math.max(0, c.g - 25)}, ${Math.max(0, c.b - 25)})`,
      accent: `rgb(${c.r}, ${c.g}, ${c.b})`,
      glow: `rgba(${c.r}, ${c.g}, ${c.b}, 0.5)`,
    };
  }

  _renderLayout() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          width: 100%;
          background-color: #0b0f19;
          color: #ffffff;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          overflow-y: auto;
          box-sizing: border-box;
        }

        .tado-container {
          max-width: 1560px;
          margin: 0 auto;
          padding: 24px 28px 60px 28px;
        }

        /* ── Top Bar & Navigation Tabs ── */
        .tado-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 16px;
          margin-bottom: 24px;
        }

        .tado-title-group {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .tado-app-icon {
          width: 44px;
          height: 44px;
          border-radius: 12px;
          background: linear-gradient(135deg, #0284c7, #2563eb);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 22px;
          box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
        }

        .domolink-tado-title {
          font-size: 24px;
          font-weight: 800;
          letter-spacing: -0.5px;
          margin: 0;
          cursor: pointer;
          user-select: none;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .tado-badge-pill {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          background: rgba(56, 189, 248, 0.15);
          color: #38bdf8;
          padding: 4px 10px;
          border-radius: 20px;
          border: 1px solid rgba(56, 189, 248, 0.3);
          letter-spacing: 0.5px;
        }

        .tado-nav-tabs {
          display: flex;
          background: rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          padding: 4px;
          gap: 4px;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .nav-tab-btn {
          background: transparent;
          border: none;
          color: #94a3b8;
          font-size: 13px;
          font-weight: 700;
          padding: 8px 18px;
          border-radius: 10px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .nav-tab-btn:hover {
          color: #ffffff;
          background: rgba(255, 255, 255, 0.06);
        }

        .nav-tab-btn.active {
          background: #0284c7;
          color: #ffffff;
          box-shadow: 0 2px 10px rgba(2, 132, 199, 0.4);
        }

        /* Bouton Authentification Principal */
        .header-auth-btn {
          background: rgba(245, 158, 11, 0.15);
          border: 1px solid rgba(245, 158, 11, 0.4);
          color: #f59e0b;
          font-size: 12px;
          font-weight: 800;
          padding: 8px 16px;
          border-radius: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 6px;
          user-select: none;
        }

        .header-auth-btn:hover {
          background: rgba(245, 158, 11, 0.3);
          color: #fbbf24;
          box-shadow: 0 0 14px rgba(245, 158, 11, 0.4);
          transform: translateY(-1px);
        }

        .header-stats-group {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .header-stat-badge {
          background: #192038;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 6px 14px;
          font-size: 13px;
          font-weight: 700;
          color: #ffffff;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        #apiQuotaBadge {
          cursor: pointer;
          transition: all 0.2s ease;
          background: rgba(14, 165, 233, 0.12);
          border: 1px solid rgba(14, 165, 233, 0.25);
        }

        #apiQuotaBadge:hover {
          background: rgba(14, 165, 233, 0.22);
          transform: translateY(-1px);
        }

        /* ── Quota & API Telemetry Card ── */
        .quota-stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 14px;
          margin-top: 16px;
          margin-bottom: 16px;
        }

        .quota-stat-box {
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 14px 16px;
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          box-sizing: border-box;
        }

        .quota-stat-label {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          color: #94a3b8;
          margin-bottom: 4px;
        }

        .quota-stat-value {
          font-size: 26px;
          font-weight: 800;
          color: #ffffff;
          letter-spacing: -0.5px;
        }

        .quota-stat-sub {
          font-size: 11px;
          color: #64748b;
          margin-top: 2px;
        }

        .quota-progress-container {
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 14px;
          padding: 12px 16px;
        }

        .quota-progress-bar-bg {
          width: 100%;
          height: 10px;
          background: rgba(255, 255, 255, 0.08);
          border-radius: 10px;
          overflow: hidden;
          margin-bottom: 8px;
        }

        .quota-progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #10b981, #06b6d4);
          border-radius: 10px;
          transition: width 0.4s ease, background 0.4s ease;
        }

        .quota-progress-labels {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: #94a3b8;
          font-weight: 600;
        }

        /* ── Label Filters Bar ── */
        .labels-filter-bar {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 16px;
          margin-bottom: 8px;
          scrollbar-width: thin;
        }

        .label-chip {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #94a3b8;
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          transition: all 0.2s ease;
          user-select: none;
        }

        .label-chip:hover {
          background: rgba(255, 255, 255, 0.12);
          color: #ffffff;
        }

        .label-chip.active {
          background: #38bdf8;
          color: #0b0f19;
          border-color: #38bdf8;
          box-shadow: 0 2px 12px rgba(56, 189, 248, 0.4);
        }

        /* ── Views (Rooms vs Settings) ── */
        .tab-view {
          display: none;
        }
        .tab-view.active-view {
          display: block;
        }

        /* ── Main Grid ── */
        .tado-dashboard-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(285px, 1fr));
          gap: 20px;
        }

        /* ── 4-Quadrant Quick Tile ── */
        .global-control-tile {
          background: #192038;
          border-radius: 24px;
          display: grid;
          grid-template-columns: 1fr 1fr;
          grid-template-rows: 1fr 1fr;
          min-height: 220px;
          overflow: hidden;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .quadrant-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          background: transparent;
          border: none;
          color: #ffffff;
          font-size: 12px;
          font-weight: 800;
          letter-spacing: 0.5px;
          cursor: pointer;
          transition: all 0.2s ease;
          user-select: none;
        }

        .quadrant-btn:hover {
          background: rgba(255, 255, 255, 0.08);
        }

        .quadrant-btn:active {
          transform: scale(0.96);
        }

        .quadrant-btn svg, .quadrant-btn span.q-icon {
          font-size: 24px;
        }

        .quad-off { border-right: 1px solid rgba(255, 255, 255, 0.08); border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
        .quad-boost { border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
        .quad-eco { border-right: 1px solid rgba(255, 255, 255, 0.08); }

        /* ── Breathing Pulse Animation for Active Heating ── */
        @keyframes tado-breathe {
          0%, 100% {
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 0 10px var(--pulse-color);
            border-color: rgba(var(--pulse-rgb), 0.45);
          }
          50% {
            box-shadow: 0 12px 34px rgba(0, 0, 0, 0.55), 0 0 24px var(--pulse-color);
            border-color: rgba(var(--pulse-rgb), 0.95);
          }
        }

        /* ── Room Cards ── */
        .room-card {
          background: #1a2236;
          border-radius: 24px;
          padding: 18px;
          position: relative;
          min-height: 220px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          cursor: pointer;
          user-select: none;
          box-sizing: border-box;
          contain: layout style;
          will-change: transform, box-shadow, background;
          backface-visibility: hidden;
          transform: translateZ(0);
          transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease, border-color 0.25s ease, background 0.5s ease;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .room-card.heating-pulse {
          animation: tado-breathe 3.2s ease-in-out infinite;
        }

        .room-card:hover {
          transform: translateY(-4px) translateZ(0);
          box-shadow: 0 14px 34px rgba(0, 0, 0, 0.5) !important;
        }

        .room-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .current-temp-label {
          font-size: 17px;
          font-weight: 800;
          color: rgba(255, 255, 255, 0.9);
          letter-spacing: -0.3px;
        }

        .room-indicators {
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .indicator-badge {
          font-size: 11px;
          font-weight: 700;
          padding: 3px 7px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.7);
        }

        .indicator-badge.flame {
          background: rgba(239, 68, 68, 0.25);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.4);
        }

        .indicator-badge.window {
          background: rgba(56, 189, 248, 0.25);
          color: #38bdf8;
          border: 1px solid rgba(56, 189, 248, 0.4);
        }

        /* ── Center Dial with Stylized Device Icon ── */
        .room-dial-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 6px 0;
          position: relative;
        }

        .room-ring {
          width: 84px;
          height: 84px;
          border-radius: 50%;
          border: 5px solid rgba(255, 255, 255, 0.1);
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }

        .room-ring.active-heat {
          border-color: #f59e0b;
          box-shadow: 0 0 18px rgba(245, 158, 11, 0.4);
        }

        .room-name {
          font-size: 16px;
          font-weight: 800;
          margin-top: 8px;
          text-align: center;
          color: #ffffff;
        }

        .room-labels-container {
          display: flex;
          gap: 4px;
          flex-wrap: wrap;
          justify-content: center;
          margin-top: 4px;
        }

        .room-mini-label {
          font-size: 9px;
          font-weight: 700;
          background: rgba(255, 255, 255, 0.1);
          color: #cbd5e1;
          padding: 1px 6px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        .room-quick-adjust {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          margin-top: 6px;
        }

        .quick-step-btn {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.12);
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #ffffff;
          font-size: 16px;
          font-weight: 800;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .quick-step-btn:hover {
          background: #0284c7;
          border-color: #0284c7;
          transform: scale(1.12);
        }

        .quick-target-val {
          font-size: 13px;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.7);
          min-width: 50px;
          text-align: center;
        }

        .room-card-actions {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          margin-top: 8px;
        }

        .room-action-btn {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.08);
          border: none;
          color: rgba(255, 255, 255, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s ease;
          font-size: 14px;
        }

        .room-action-btn:hover {
          background: rgba(255, 255, 255, 0.2);
          color: #ffffff;
          transform: scale(1.1);
        }

        /* ── MODALE DETAIL PIÈCE ── */
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(10px);
          z-index: 10000;
          display: flex;
          align-items: center;
          justify-content: center;
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.25s ease;
        }

        .modal-overlay.open {
          opacity: 1;
          pointer-events: auto;
        }

        .modal-card {
          width: 92%;
          max-width: 460px;
          height: 94vh;
          max-height: 900px;
          border-radius: 40px;
          padding: 22px 24px 26px 24px;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: relative;
          box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6);
          transition: background-color 0.4s ease;
          overflow-y: auto;
          scrollbar-width: none;
        }

        .modal-card::-webkit-scrollbar {
          display: none;
        }

        .modal-close-btn {
          width: 40px;
          height: 40px;
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: absolute;
          top: 20px;
          left: 20px;
          z-index: 20;
        }

        .modal-close-btn:hover {
          background: rgba(255, 255, 255, 0.35);
          transform: scale(1.06);
        }

        .modal-header-text {
          text-align: center;
          margin-top: 4px;
        }

        .modal-room-title {
          font-size: 24px;
          font-weight: 800;
          color: #ffffff;
          margin: 0;
        }

        .modal-room-subtitle {
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 2px;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.75);
          margin-top: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
        }

        .modal-capsules-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-top: 14px;
        }

        .stat-capsule {
          background: rgba(0, 0, 0, 0.18);
          border-radius: 20px;
          padding: 12px 10px;
          text-align: center;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .stat-capsule-label {
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.65);
        }

        .stat-capsule-val {
          font-size: 24px;
          font-weight: 800;
          color: #ffffff;
          margin-top: 2px;
        }

        .modal-sparkline-card {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 18px;
          padding: 10px 14px;
          margin-top: 10px;
          border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .sparkline-header {
          display: flex;
          justify-content: space-between;
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 1px;
          color: rgba(255, 255, 255, 0.6);
          margin-bottom: 4px;
        }

        .sparkline-svg {
          width: 100%;
          height: 38px;
          overflow: visible;
        }

        /* ── RÉGLE ET GROS BOUTON CURSEUR VERTICAL SLIDER ── */
        .thermostat-vertical-card {
          background: rgba(0, 0, 0, 0.14);
          border-radius: 32px;
          padding: 16px 14px;
          margin: 10px 0;
          position: relative;
          border: 1px solid rgba(255, 255, 255, 0.1);
          height: 360px;
          min-height: 360px;
          box-sizing: border-box;
          overflow: hidden;
          user-select: none;
          touch-action: none;
        }

        .scale-markers {
          width: calc(100% - 32px);
          height: calc(100% - 40px);
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: absolute;
          top: 20px;
          left: 16px;
          pointer-events: auto;
          box-sizing: border-box;
          opacity: 0.35;
          z-index: 1;
        }

        .scale-line {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 11px;
          font-weight: 700;
          cursor: pointer;
          padding: 4px 0;
        }

        .scale-line:hover {
          opacity: 1;
          color: #38bdf8;
        }

        .scale-line::after {
          content: "";
          flex: 1;
          height: 1px;
          background: rgba(255, 255, 255, 0.35);
        }

        /* Le gros curseur blanc qui monte et qui descend */
        .thermostat-sliding-cursor {
          background: #ffffff;
          border-radius: 28px;
          width: calc(100% - 36px);
          height: 140px;
          position: absolute;
          left: 18px;
          top: 110px;
          padding: 12px 16px;
          box-sizing: border-box;
          text-align: center;
          box-shadow: 0 14px 35px rgba(0, 0, 0, 0.35), 0 0 25px rgba(255, 255, 255, 0.25);
          color: #000000;
          z-index: 10;
          cursor: grab;
          user-select: none;
          touch-action: none;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-between;
          transition: transform 0.15s ease, box-shadow 0.2s ease;
          will-change: top;
        }

        .thermostat-sliding-cursor:active {
          cursor: grabbing;
          transform: scale(1.02);
          box-shadow: 0 20px 45px rgba(0, 0, 0, 0.5), 0 0 30px rgba(255, 255, 255, 0.35);
        }

        .slider-pill-bar {
          width: 44px;
          height: 5px;
          background: #cbd5e1;
          border-radius: 10px;
          margin: 0 auto 4px auto;
        }

        .target-temp-big {
          font-size: 50px;
          font-weight: 900;
          color: #000000;
          letter-spacing: -2px;
          line-height: 1;
        }

        .target-consigne-label {
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 2px;
          text-transform: uppercase;
          color: #64748b;
        }

        .cursor-step-row {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 16px;
          margin-top: 2px;
        }

        .cursor-step-btn {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          background: #f1f5f9;
          border: 1px solid #cbd5e1;
          color: #0f172a;
          font-size: 16px;
          font-weight: 800;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .cursor-step-btn:hover {
          background: #0284c7;
          color: #ffffff;
          border-color: #0284c7;
        }

        /* Overlay Duration Selector Pills */
        .duration-selector-row {
          display: flex;
          gap: 6px;
          justify-content: center;
          flex-wrap: wrap;
          margin: 6px 0;
        }

        .duration-pill {
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.12);
          color: rgba(255, 255, 255, 0.7);
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 10px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .duration-pill:hover {
          background: rgba(255, 255, 255, 0.18);
          color: #ffffff;
        }

        .duration-pill.active {
          background: #0284c7;
          border-color: #0284c7;
          color: #ffffff;
          box-shadow: 0 2px 8px rgba(2, 132, 199, 0.4);
        }

        .mode-controls-capsule {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 24px;
          padding: 6px 10px;
          display: flex;
          align-items: center;
          justify-content: space-around;
          border: 1px solid rgba(255, 255, 255, 0.08);
          margin-top: 6px;
        }

        .mode-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 3px;
          background: transparent;
          border: none;
          color: rgba(255, 255, 255, 0.7);
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 1px;
          text-transform: uppercase;
          padding: 6px 14px;
          border-radius: 16px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .mode-btn.active {
          background: rgba(255, 255, 255, 0.25);
          color: #ffffff;
        }

        .modal-bottom-pills {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-top: 8px;
        }

        .footer-pill {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 20px;
          padding: 10px 14px;
          display: flex;
          align-items: center;
          gap: 10px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #ffffff;
          cursor: pointer;
          user-select: none;
          transition: all 0.2s ease;
        }

        .footer-pill:hover {
          background: rgba(255, 255, 255, 0.15);
        }

        .footer-pill.active-pill {
          background: rgba(245, 158, 11, 0.35);
          border-color: #f59e0b;
        }

        .footer-pill-icon {
          font-size: 18px;
        }

        .footer-pill-text {
          display: flex;
          flex-direction: column;
        }

        .footer-pill-label {
          font-size: 8px;
          font-weight: 800;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.65);
        }

        .footer-pill-val {
          font-size: 13px;
          font-weight: 800;
        }

        /* ── SETTINGS VIEW STYLES ── */
        .settings-view-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .settings-card {
          background: #192038;
          border-radius: 24px;
          padding: 24px 28px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }

        .settings-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 14px;
        }

        .settings-card-title {
          font-size: 18px;
          font-weight: 800;
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 0;
        }

        .settings-card-desc {
          font-size: 13px;
          color: #94a3b8;
          margin: 4px 0 0 0;
        }

        .settings-grid-form {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 20px;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .form-label {
          font-size: 13px;
          font-weight: 700;
          color: #e2e8f0;
        }

        .form-desc {
          font-size: 11px;
          color: #94a3b8;
        }

        .form-input, .form-select {
          background: #0f172a;
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 12px;
          padding: 10px 14px;
          color: #ffffff;
          font-size: 13px;
          outline: none;
        }

        .form-toggle-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 0;
        }

        .switch {
          position: relative;
          display: inline-block;
          width: 46px;
          height: 26px;
        }

        .switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }

        .slider-round {
          position: absolute;
          cursor: pointer;
          top: 0; left: 0; right: 0; bottom: 0;
          background-color: #334155;
          transition: 0.3s;
          border-radius: 34px;
        }

        .slider-round:before {
          position: absolute;
          content: "";
          height: 20px;
          width: 20px;
          left: 3px;
          bottom: 3px;
          background-color: white;
          transition: 0.3s;
          border-radius: 50%;
        }

        input:checked + .slider-round {
          background-color: #0284c7;
        }

        input:checked + .slider-round:before {
          transform: translateX(20px);
        }

        .room-labels-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .room-label-item {
          display: grid;
          grid-template-columns: 240px 1fr 1.6fr;
          align-items: start;
          background: #0f172a;
          border-radius: 14px;
          padding: 16px 20px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          gap: 24px;
          box-sizing: border-box;
        }

        @media (max-width: 1200px) {
          .room-label-item {
            grid-template-columns: 200px 1fr 1.4fr;
            gap: 16px;
          }
        }

        @media (max-width: 960px) {
          .room-label-item {
            grid-template-columns: 1fr;
            gap: 14px;
          }
        }

        .room-label-item-left {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
          padding-top: 4px;
        }

        .room-label-item-name {
          font-weight: 800;
          font-size: 15px;
          color: #ffffff;
          line-height: 1.3;
          word-break: break-word;
        }

        .room-section-block {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 0;
        }

        .room-section-title {
          font-size: 12px;
          color: #94a3b8;
          font-weight: 700;
          margin-bottom: 2px;
          letter-spacing: 0.3px;
        }

        .room-tags-editor {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 0;
        }

        .pills-container {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
          width: 100%;
        }

        .tag-pill-badge {
          background: rgba(56, 189, 248, 0.15);
          color: #38bdf8;
          border: 1px solid rgba(56, 189, 248, 0.3);
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 11px;
          font-weight: 700;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .tag-remove-btn {
          cursor: pointer;
          opacity: 0.7;
          font-size: 13px;
          transition: opacity 0.2s, color 0.2s;
        }
        .tag-remove-btn:hover {
          opacity: 1;
          color: #ef4444;
        }

        .tag-input-row {
          display: flex;
          align-items: center;
          gap: 8px;
          width: 100%;
        }

        .add-tag-input {
          height: 36px;
          box-sizing: border-box;
          background: #1e293b;
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          padding: 0 12px;
          color: #ffffff;
          font-size: 12px;
          outline: none;
          width: 140px;
          max-width: 100%;
          transition: border-color 0.2s;
        }
        .add-tag-input:focus {
          border-color: #0284c7;
        }

        .btn-add-tag {
          height: 36px;
          box-sizing: border-box;
          background: #0284c7;
          border: none;
          color: #ffffff;
          border-radius: 10px;
          padding: 0 14px;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
        }
        .btn-add-tag:hover {
          background: #0369a1;
          transform: translateY(-1px);
        }

        .room-sensors-editor {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 0;
        }

        .sensor-pill-badge {
          background: rgba(16, 185, 129, 0.15);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.3);
          padding: 4px 10px;
          border-radius: 20px;
          font-size: 11px;
          font-weight: 600;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .sensor-remove-btn {
          cursor: pointer;
          opacity: 0.7;
          font-size: 13px;
          transition: opacity 0.2s, color 0.2s;
        }
        .sensor-remove-btn:hover {
          opacity: 1;
          color: #ef4444;
        }

        .sensor-adder-controls {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
          width: 100%;
        }

        .sensor-autocomplete-input {
          height: 36px;
          box-sizing: border-box;
          background: #1e293b;
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          padding: 0 12px;
          color: #ffffff;
          font-size: 12px;
          outline: none;
          width: 260px;
          max-width: 100%;
          transition: border-color 0.2s;
        }
        .sensor-autocomplete-input:focus {
          border-color: #10b981;
        }

        .btn-add-sensor {
          height: 36px;
          box-sizing: border-box;
          background: #059669;
          border: none;
          color: #ffffff;
          border-radius: 10px;
          padding: 0 14px;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s ease;
        }
        .btn-add-sensor:hover {
          background: #10b981;
          transform: translateY(-1px);
        }

        .max-sensors-notice {
          font-size: 12px;
          color: #94a3b8;
          font-style: italic;
          line-height: 36px;
        }

        .calib-avg-badge {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          background: rgba(56, 189, 248, 0.12);
          border: 1px solid rgba(56, 189, 248, 0.3);
          color: #38bdf8;
          padding: 4px 8px;
          border-radius: 8px;
          font-weight: 700;
          font-size: 12px;
          white-space: nowrap;
        }

        .calib-mode-toggle {
          display: inline-flex;
          background: rgba(15, 23, 42, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 20px;
          padding: 2px;
          gap: 2px;
        }

        .calib-mode-btn {
          border: none;
          background: transparent;
          color: #64748b;
          font-size: 10px;
          font-weight: 700;
          padding: 4px 8px;
          border-radius: 14px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .calib-mode-btn.active-manual {
          background: #334155;
          color: #f1f5f9;
        }

        .calib-mode-btn.active-auto {
          background: linear-gradient(135deg, #0284c7, #2563eb);
          color: #ffffff;
          box-shadow: 0 0 10px rgba(2, 132, 199, 0.4);
        }

        .calibration-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }

        .calibration-table th {
          text-align: left;
          padding: 10px 14px;
          color: #94a3b8;
          font-weight: 700;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .calibration-table td {
          padding: 12px 14px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          vertical-align: middle;
        }

        .calibration-stepper {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .calib-val-badge {
          font-family: monospace;
          font-size: 13px;
          font-weight: 800;
          min-width: 52px;
          text-align: center;
          background: #0f172a;
          padding: 4px 8px;
          border-radius: 6px;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .btn-apply-offset {
          background: #10b981;
          border: none;
          color: #ffffff;
          padding: 5px 12px;
          border-radius: 8px;
          font-size: 11px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-apply-offset:hover {
          background: #059669;
          transform: scale(1.05);
        }

        .btn-save-all {
          background: linear-gradient(135deg, #0284c7, #2563eb);
          border: none;
          color: #ffffff;
          padding: 12px 28px;
          border-radius: 14px;
          font-size: 14px;
          font-weight: 800;
          cursor: pointer;
          box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
          transition: all 0.2s ease;
          align-self: flex-start;
          margin-top: 10px;
        }

        .btn-save-all:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(37, 99, 235, 0.6);
        }
      </style>

      <div class="tado-container">
        <!-- HEADER -->
        <div class="tado-header">
          <div class="tado-title-group">
            <div class="tado-app-icon">🔥</div>
            <div>
              <h1 class="domolink-tado-title">
                DomoLink-Tado
                <span class="tado-badge-pill" id="headerHomeBadge">Enghien</span>
              </h1>
            </div>
          </div>

          <!-- Navigation Tabs -->
          <div class="tado-nav-tabs">
            <button class="nav-tab-btn active" id="tabBtnRooms">
              <span>🏠</span> Domicile & Pièces
            </button>
            <button class="nav-tab-btn" id="tabBtnSettings">
              <span>⚙️</span> Paramètres & Configuration
            </button>
          </div>

          <!-- Bouton Authentification & Quick Indicators -->
          <div class="header-stats-group">
            <button class="header-auth-btn" id="btnHeaderAuth" title="Lancer une ré-authentification Tado Device Flow">
              <span>🔑</span> AUTHENTIFICATION
            </button>
            <div class="header-stat-badge" id="apiQuotaBadge" title="Requêtes API Tado : Faites / Restantes pour aujourd'hui (cliquez pour détails)">
              <span style="font-size: 14px;">⚡</span>
              <span id="api-quota-display">-- faites / -- rest.</span>
            </div>
            <div class="header-stat-badge" id="outdoorBadge">
              <span>🌡️</span>
              <span id="outdoor-temp-display">--° EXT</span>
            </div>
            <div class="header-stat-badge" id="activeHeatingBadge">
              <span>🔥</span>
              <span id="active-heating-count">0 en chauffe</span>
            </div>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════ -->
        <!-- VIEW 1 : DOMICILE & PIÈCES                      -->
        <!-- ═══════════════════════════════════════════════ -->
        <div class="tab-view active-view" id="viewRooms">
          <div class="labels-filter-bar" id="labelsFilterBar">
            <button class="label-chip active" data-label="__ALL__">Toutes les pièces</button>
          </div>

          <div class="tado-dashboard-grid" id="tado-grid">
            <div class="global-control-tile">
              <button class="quadrant-btn quad-off" id="btn-global-off">
                <span class="q-icon">⏻</span>
                <span>TOUT ÉTEINDRE</span>
              </button>
              <button class="quadrant-btn quad-boost" id="btn-global-boost">
                <span class="q-icon">🔥</span>
                <span>BOOST GÉNÉRAL</span>
              </button>
              <button class="quadrant-btn quad-eco" id="btn-global-eco">
                <span class="q-icon">🌿</span>
                <span>MODE ÉCO</span>
              </button>
              <button class="quadrant-btn quad-prog" id="btn-global-prog">
                <span class="q-icon">📅</span>
                <span>AUTO (PROG)</span>
              </button>
            </div>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════ -->
        <!-- VIEW 2 : PARAMÈTRES & CONFIGURATION             -->
        <!-- ═══════════════════════════════════════════════ -->
        <div class="tab-view" id="viewSettings">
          <div class="settings-view-container">
            <!-- Carte 0 : Authentification & Re-connexion Tado -->
            <div class="settings-card">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>🔐</span> Authentification Tado & Persistance</h2>
                  <p class="settings-card-desc">Générez un nouveau jeton officiel Tado ou rétablissez la connexion sans réinstaller l'intégration.</p>
                </div>
                <button class="btn-save-all" id="btnSettingsAuth" style="margin: 0; background: linear-gradient(135deg, #f59e0b, #ea580c); box-shadow: 0 4px 14px rgba(245, 158, 11, 0.4);">
                  🔑 Lancer une Authentification (Device Flow)
                </button>
              </div>
              <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
                En cas de perte de session ou de redémarrage Home Assistant nécessitant une validation, cliquez sur le bouton ci-dessus pour démarrer instantanément le protocole officiel Tado Device Flow.
              </div>
            </div>

            <!-- Carte 0 bis : Quota & Télémétrie API Tado -->
            <div class="settings-card" id="quotaSettingsCard">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>📊</span> Quota & Requêtes API Tado</h2>
                  <p class="settings-card-desc">Suivi en direct de la consommation de vos requêtes API Tado (plafond journalier de 1000 requêtes).</p>
                </div>
                <div id="quotaStatusPill" class="tado-badge-pill" style="background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3);">
                  Optimal
                </div>
              </div>

              <div class="quota-stats-grid">
                <div class="quota-stat-box">
                  <div class="quota-stat-label">Requêtes Faites (Jour)</div>
                  <div class="quota-stat-value" id="quotaValUsed">--</div>
                  <div class="quota-stat-sub">appels effectués</div>
                </div>
                <div class="quota-stat-box">
                  <div class="quota-stat-label">Requêtes Restantes</div>
                  <div class="quota-stat-value" id="quotaValRemaining" style="color: #38bdf8;">--</div>
                  <div class="quota-stat-sub">disponibles aujourd'hui</div>
                </div>
                <div class="quota-stat-box">
                  <div class="quota-stat-label">Plafond Journalier</div>
                  <div class="quota-stat-value" id="quotaValLimit" style="color: #94a3b8;">1000</div>
                  <div class="quota-stat-sub">politique Tado perday</div>
                </div>
              </div>

              <div class="quota-progress-container">
                <div class="quota-progress-bar-bg">
                  <div class="quota-progress-bar-fill" id="quotaProgressFill" style="width: 0%;"></div>
                </div>
                <div class="quota-progress-labels">
                  <span id="quotaPercentLabel">0% utilisé</span>
                  <span id="quotaResetLabel">Plafond journalier Tado réinitialisé toutes les 24h</span>
                </div>
              </div>
            </div>

            <!-- Carte 1 : Automatisations -->
            <div class="settings-card">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>⚡</span> Automatisations & Dérogations</h2>
                  <p class="settings-card-desc">Comportements automatiques, coupure fenêtre ouverte et température éco.</p>
                </div>
              </div>

              <div class="settings-grid-form">
                <div class="form-group">
                  <label class="form-label">Règle de fin de consigne manuelle</label>
                  <select class="form-select" id="optOverlayMode">
                    <option value="NEXT_TIME_BLOCK">Jusqu'au prochain changement de programmation (Auto)</option>
                    <option value="MANUAL">Permanent (jusqu'à annulation manuelle)</option>
                    <option value="TIMER">Minuterie personnalisée</option>
                  </select>
                </div>

                <div class="form-group">
                  <label class="form-label">Durée minuterie par défaut (minutes)</label>
                  <input type="number" class="form-input" id="optOverlayDuration" min="5" max="1440" step="5" value="60">
                </div>

                <div class="form-group">
                  <div class="form-toggle-row">
                    <div>
                      <div class="form-label">Coupure Fenêtre Ouverte (Auto-Assist Gratuit)</div>
                      <div class="form-desc">Coupe la chauffe sur détection de fenêtre sans abonnement Tado.</div>
                    </div>
                    <label class="switch">
                      <input type="checkbox" id="optAutoWindow" checked>
                      <span class="slider-round"></span>
                    </label>
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label">Durée de coupure fenêtre ouverte (minutes)</label>
                  <input type="number" class="form-input" id="optAutoWindowDuration" min="5" max="60" step="5" value="15">
                </div>

                <div class="form-group">
                  <label class="form-label">Température Mode Éco (°C)</label>
                  <input type="number" class="form-input" id="optEcoTemp" min="10" max="22" step="0.5" value="17.0">
                </div>

                <div class="form-group">
                  <div class="form-toggle-row">
                    <div>
                      <div class="form-label">Polling Adaptatif Intelligent</div>
                      <div class="form-desc">15s en chauffe, 60s en veille (protège contre le rate limit 429).</div>
                    </div>
                    <label class="switch">
                      <input type="checkbox" id="optAdaptivePolling" checked>
                      <span class="slider-round"></span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <!-- Carte 2 : Étiquettes & Capteurs de Température -->
            <div class="settings-card">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>🏷️</span> Étiquettes & Capteurs de Température</h2>
                  <p class="settings-card-desc">Attribuez des étiquettes et associez jusqu'à 4 capteurs de température externes par pièce pour calibrer vos vannes.</p>
                </div>
                <button class="btn-save-all" id="btnSaveLabels">💾 Sauvegarder les paramètres</button>
              </div>

              <div class="room-labels-list" id="roomLabelsList"></div>
            </div>

            <!-- Carte 3 : Calibration & Offset des Sondes -->
            <div class="settings-card">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>🌡️</span> Calibration & Offset des Sondes</h2>
                  <p class="settings-card-desc">Corrigez les écarts de température mesurés par le matériel (-5.0°C à +5.0°C) en mode Manuel ou Auto.</p>
                </div>
              </div>

              <div style="overflow-x: auto;">
                <table class="calibration-table">
                  <thead>
                    <tr>
                      <th>Équipement</th>
                      <th>Pièce</th>
                      <th>Numéro de Série</th>
                      <th>Ajustement Offset (-5.0°C à +5.0°C)</th>
                      <th>Mode</th>
                      <th>T° Moyenne Capteurs</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody id="calibrationTableBody"></tbody>
                </table>
              </div>
            </div>

            <!-- Carte 4 : Diagnostic Matériel -->
            <div class="settings-card">
              <div class="settings-card-header">
                <div>
                  <h2 class="settings-card-title"><span>📡</span> Diagnostic Matériel & État des Piles</h2>
                  <p class="settings-card-desc">Surveillance de l'état des piles et de la liaison radio.</p>
                </div>
              </div>

              <div style="overflow-x: auto;">
                <table class="calibration-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Numéro de Série</th>
                      <th>Pièce assignée</th>
                      <th>Niveau Piles</th>
                      <th>Liaison Radio</th>
                      <th>Firmware</th>
                    </tr>
                  </thead>
                  <tbody id="hardwareTableBody"></tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- MODALE DETAIL PIECE AVEC CURSEUR VERTICAL SLIDER -->
      <div class="modal-overlay" id="roomModalOverlay">
        <div class="modal-card" id="roomModalCard">
          <button class="modal-close-btn" id="modalCloseBtn">✕</button>

          <div class="modal-header-text">
            <h2 class="modal-room-title" id="modalRoomTitle">Pièce</h2>
            <div class="modal-room-subtitle">
              <span id="modalDeviceIconPlaceholder"></span>
              <span>CONTRÔLE CLIMAT TADO</span>
            </div>
          </div>

          <div class="modal-capsules-grid">
            <div class="stat-capsule">
              <div class="stat-capsule-label">ACTUEL</div>
              <div class="stat-capsule-val" id="modalActuelVal">--°</div>
            </div>
            <div class="stat-capsule">
              <div class="stat-capsule-label">HUMIDITÉ</div>
              <div class="stat-capsule-val" id="modalHumiditeVal">--%</div>
            </div>
          </div>

          <div class="modal-sparkline-card">
            <div class="sparkline-header">
              <span>ÉVOLUTION RÉCENTE</span>
              <span id="modalSparklineCurrent">--°C</span>
            </div>
            <svg class="sparkline-svg" id="modalSparklineSvg" viewBox="0 0 320 38">
              <defs>
                <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.5"/>
                  <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
                </linearGradient>
              </defs>
              <path id="sparklineArea" d="" fill="url(#sparkGrad)"/>
              <path id="sparklineLine" d="" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
          </div>

          <!-- CARTE THERMOSTAT AVEC CURSEUR QUI MONTE ET QUI DESCEND -->
          <div class="thermostat-vertical-card" id="modalThermostatCard">
            <!-- Règle graduée en arrière-plan -->
            <div class="scale-markers">
              <div class="scale-line" data-temp="30"><span>30°</span></div>
              <div class="scale-line" data-temp="25"><span>25°</span></div>
              <div class="scale-line" data-temp="20"><span>20°</span></div>
              <div class="scale-line" data-temp="15"><span>15°</span></div>
              <div class="scale-line" data-temp="10"><span>10°</span></div>
              <div class="scale-line" data-temp="5"><span>5°</span></div>
            </div>

            <!-- GROS BOUTON CURSEUR BLANC QUI GLISSE VERTICALEMENT -->
            <div class="thermostat-sliding-cursor" id="thermostatSlidingCursor">
              <div class="slider-pill-bar"></div>
              <div class="target-temp-big" id="modalTargetBig">20.0</div>
              <div class="target-consigne-label">CONSIGNE •</div>
              <div class="cursor-step-row">
                <button class="cursor-step-btn" id="btnCursorMinus" title="-0.5°C">−</button>
                <button class="cursor-step-btn" id="btnCursorPlus" title="+0.5°C">+</button>
              </div>
            </div>
          </div>

          <!-- Durée de dérogation selector -->
          <div class="duration-selector-row" id="durationPillsRow">
            <button class="duration-pill active" data-duration="NEXT_TIME_BLOCK">⏰ Auto</button>
            <button class="duration-pill" data-duration="1800">⏳ 30m</button>
            <button class="duration-pill" data-duration="3600">⏳ 1h</button>
            <button class="duration-pill" data-duration="7200">⏳ 2h</button>
            <button class="duration-pill" data-duration="14400">⏳ 4h</button>
            <button class="duration-pill" data-duration="MANUAL">♾️ Permanent</button>
          </div>

          <!-- Contrôles OFF / AUTO / ON -->
          <div class="mode-controls-capsule">
            <button class="mode-btn" id="modalModeOff">
              <span>⏻</span>
              <span>OFF</span>
            </button>
            <button class="mode-btn active" id="modalModeAuto">
              <span>📅</span>
              <span>AUTO</span>
            </button>
            <button class="mode-btn" id="modalModeHeat">
              <span>🔥</span>
              <span>ON</span>
            </button>
          </div>

          <!-- Pied de page: Puissance & Sécurité -->
          <div class="modal-bottom-pills">
            <div class="footer-pill" id="modalPillPuissance">
              <span class="footer-pill-icon">🔥</span>
              <div class="footer-pill-text">
                <span class="footer-pill-label">PUISSANCE</span>
                <span class="footer-pill-val" id="modalValPuissance">0%</span>
              </div>
            </div>
            <div class="footer-pill" id="modalPillSecurite">
              <span class="footer-pill-icon">🔒</span>
              <div class="footer-pill-text">
                <span class="footer-pill-label">SÉCURITÉ</span>
                <span class="footer-pill-val" id="modalValSecurite">ENFANT</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- MODALE DIALOGUE D'AUTHENTIFICATION RAPIDE -->
      <div class="modal-overlay" id="authModalOverlay">
        <div class="modal-card" style="max-width: 480px; height: auto; padding: 28px; background: #131928;">
          <button class="modal-close-btn" id="authModalCloseBtn">✕</button>
          <div style="text-align: center; margin-bottom: 20px;">
            <div style="font-size: 42px; margin-bottom: 8px;">🔑</div>
            <h2 style="font-size: 22px; font-weight: 800; margin: 0; color: #ffffff;">Authentification DomoLink-Tado</h2>
            <p style="font-size: 13px; color: #94a3b8; margin: 6px 0 0 0;">Protocole sécurisé officiel Tado Device Flow</p>
          </div>

          <div style="background: rgba(0, 0, 0, 0.28); border-radius: 20px; padding: 20px; text-align: center; margin-bottom: 20px; border: 1px solid rgba(255, 255, 255, 0.08);">
            <div style="font-size: 12px; color: #94a3b8; font-weight: 700; text-transform: uppercase;">1. Ouvrez le lien Tado officiel</div>
            <a id="authLinkBtn" href="https://login.tado.com/oauth2/device" target="_blank" style="display: inline-block; margin: 12px 0; background: #0284c7; color: #ffffff; padding: 10px 20px; border-radius: 12px; text-decoration: none; font-weight: 800; font-size: 14px; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);">
              ↗ Se connecter sur login.tado.com
            </a>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 10px;">2. Autorisez l'accès à votre domicile</div>
          </div>

          <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5; margin-bottom: 24px;">
            Une fois validé sur votre compte Tado, cliquez sur le bouton ci-dessous pour finaliser l'enregistrement immédiat du nouveau jeton dans Home Assistant.
          </div>

          <button class="btn-save-all" id="btnLaunchReauthFlow" style="width: 100%; text-align: center; justify-content: center; font-size: 15px; padding: 14px;">
            ✓ Lancer le renouvellement du jeton
          </button>
          <div id="authDialogStatus" style="margin-top: 14px; text-align: center; font-size: 13px; font-weight: 700; color: #38bdf8;"></div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const title = this.querySelector(".domolink-tado-title");
    if (title) {
      let clicks = [];
      title.addEventListener("click", () => {
        const now = Date.now();
        clicks = clicks.filter((t) => now - t < 2000);
        clicks.push(now);
        if (clicks.length >= 3) {
          clicks = [];
          launchSocrateRulesEasterEgg(this);
        }
      });
    }

    // Tabs Navigation
    const tabRooms = this.querySelector("#tabBtnRooms");
    const tabSettings = this.querySelector("#tabBtnSettings");
    const viewRooms = this.querySelector("#viewRooms");
    const viewSettings = this.querySelector("#viewSettings");

    tabRooms?.addEventListener("click", () => {
      this._activeTab = "rooms";
      tabRooms.classList.add("active");
      tabSettings?.classList.remove("active");
      viewRooms?.classList.add("active-view");
      viewSettings?.classList.remove("active-view");
    });

    tabSettings?.addEventListener("click", () => {
      this._activeTab = "settings";
      tabSettings.classList.add("active");
      tabRooms?.classList.remove("active");
      viewSettings?.classList.add("active-view");
      viewRooms?.classList.remove("active-view");
      this._renderSettingsView();
    });

    this.querySelector("#apiQuotaBadge")?.addEventListener("click", () => {
      tabSettings?.click();
      setTimeout(() => {
        this.querySelector("#quotaSettingsCard")?.scrollIntoView({ behavior: "smooth" });
      }, 50);
    });

    // Bouton Authentification (Header & Settings)
    const authOverlay = this.querySelector("#authModalOverlay");
    const openAuthModal = () => {
      if (authOverlay) authOverlay.classList.add("open");
    };
    const closeAuthModal = () => {
      if (authOverlay) authOverlay.classList.remove("open");
    };

    this.querySelector("#btnHeaderAuth")?.addEventListener("click", openAuthModal);
    this.querySelector("#btnSettingsAuth")?.addEventListener("click", openAuthModal);
    this.querySelector("#authModalCloseBtn")?.addEventListener("click", closeAuthModal);
    authOverlay?.addEventListener("click", (e) => {
      if (e.target === authOverlay) closeAuthModal();
    });

    this.querySelector("#btnLaunchReauthFlow")?.addEventListener("click", () => {
      const statusEl = this.querySelector("#authDialogStatus");
      if (statusEl) statusEl.textContent = "Lancement de la procédure d'authentification...";
      this._callService("domolink_tado", "reauthenticate", {});
      setTimeout(() => {
        if (statusEl) statusEl.textContent = "✓ Procédure initiée ! Redirection vers Home Assistant...";
        setTimeout(() => {
          closeAuthModal();
          // Rediriger vers la page des intégrations HA
          window.location.href = "/config/integrations";
        }, 1500);
      }, 1000);
    });

    // Boutons de la tuile globale 4 quadrants
    this.querySelector("#btn-global-off")?.addEventListener("click", () => {
      this._callService("domolink_tado", "set_all_off", {});
    });

    this.querySelector("#btn-global-boost")?.addEventListener("click", () => {
      this._callService("domolink_tado", "set_boost", { temperature: 25.0, duration: 1800 });
    });

    this.querySelector("#btn-global-eco")?.addEventListener("click", () => {
      const ecoVal = parseFloat(this.querySelector("#optEcoTemp")?.value) || 17.0;
      this._callService("domolink_tado", "set_eco_all", { temperature: ecoVal });
    });

    this.querySelector("#btn-global-prog")?.addEventListener("click", () => {
      this._callService("domolink_tado", "resume_all_schedules", {});
    });

    // Modale fermer
    const overlay = this.querySelector("#roomModalOverlay");
    this.querySelector("#modalCloseBtn")?.addEventListener("click", () => {
      this._closeModal();
    });

    overlay?.addEventListener("click", (e) => {
      if (e.target === overlay) {
        this._closeModal();
      }
    });

    // ── LE GROS CURSEUR BLANC COULISSANT DE HAUT EN BAS ──
    this._bindVerticalCursor();

    // Pilules de durée de dérogation
    const durationPills = this.querySelectorAll(".duration-pill");
    durationPills.forEach((pill) => {
      pill.addEventListener("click", () => {
        durationPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        this._selectedDuration = pill.dataset.duration;
        if (this._activeModalZone) {
          this._applyTargetTemperature(this._activeModalZone, this._activeModalZone.target_num);
        }
      });
    });

    // Modes dans la modale
    this.querySelector("#modalModeOff")?.addEventListener("click", () => {
      if (!this._activeModalZone) return;
      this._callService("climate", "set_hvac_mode", {
        entity_id: this._activeModalZone.entity_id,
        hvac_mode: "off",
      });
    });

    this.querySelector("#modalModeAuto")?.addEventListener("click", () => {
      if (!this._activeModalZone) return;
      this._callService("climate", "set_hvac_mode", {
        entity_id: this._activeModalZone.entity_id,
        hvac_mode: "auto",
      });
    });

    this.querySelector("#modalModeHeat")?.addEventListener("click", () => {
      if (!this._activeModalZone) return;
      this._callService("climate", "set_hvac_mode", {
        entity_id: this._activeModalZone.entity_id,
        hvac_mode: "heat",
      });
    });

    // Sécurité enfant
    this.querySelector("#modalPillSecurite")?.addEventListener("click", () => {
      if (!this._activeModalZone) return;
      const z = this._activeModalZone;
      const serial = z.devices && z.devices[0] && (z.devices[0].serial || z.devices[0].serial_number);
      if (serial) {
        this._callService("domolink_tado", "set_child_lock", {
          device_serial: serial,
          locked: !z.child_locked,
        });
      }
    });

    // Sauvegarde des étiquettes depuis le draft
    this.querySelector("#btnSaveLabels")?.addEventListener("click", () => {
      this._saveAllLabelsFromDraft();
    });
  }

  _bindVerticalCursor() {
    const card = this.querySelector("#modalThermostatCard");
    const cursor = this.querySelector("#thermostatSlidingCursor");
    if (!card || !cursor) return;

    let isDragging = false;
    const minTemp = 5.0;
    const maxTemp = 30.0;
    const span = maxTemp - minTemp;

    const handleMove = (clientY) => {
      const rect = card.getBoundingClientRect();
      const cursorHeight = cursor.offsetHeight || 140;
      const paddingTop = 16;
      const travel = rect.height - cursorHeight - 32;
      if (travel <= 0) return;

      const currentY = clientY - rect.top - cursorHeight / 2;
      const clampedY = Math.max(paddingTop, Math.min(paddingTop + travel, currentY));
      const ratio = 1.0 - (clampedY - paddingTop) / travel;
      const rawTemp = minTemp + ratio * span;
      const stepped = Math.max(minTemp, Math.min(maxTemp, Math.round(rawTemp * 2) / 2));

      cursor.style.transition = "none";
      cursor.style.top = `${clampedY}px`;

      const targetBig = this.querySelector("#modalTargetBig");
      if (targetBig) targetBig.textContent = stepped.toFixed(1);

      if (this._activeModalZone) {
        this._activeModalZone.target_num = stepped;
        this._activeModalZone.target_temp = stepped.toFixed(1);
        this._updateModalBackgroundOnly(stepped);
      }
    };

    const stopDrag = () => {
      if (!isDragging) return;
      isDragging = false;
      this._cursorDragActive = false;
      if (this._activeModalZone) {
        this._setCursorPosition(this._activeModalZone.target_num, true);
        this._applyTargetTemperature(this._activeModalZone, this._activeModalZone.target_num, 400);
      }
    };

    cursor.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".cursor-step-btn")) return;
      isDragging = true;
      this._cursorDragActive = true;
      try { cursor.setPointerCapture(e.pointerId); } catch (_) {}
      handleMove(e.clientY);
    });

    card.addEventListener("pointerdown", (e) => {
      if (e.target.closest("#thermostatSlidingCursor")) return;
      isDragging = true;
      this._cursorDragActive = true;
      try { card.setPointerCapture(e.pointerId); } catch (_) {}
      handleMove(e.clientY);
    });

    window.addEventListener("pointermove", (e) => {
      if (!isDragging) return;
      handleMove(e.clientY);
    });

    window.addEventListener("pointerup", stopDrag);
    window.addEventListener("pointercancel", stopDrag);

    // Clic sur les graduations
    const lines = this.querySelectorAll(".scale-line");
    lines.forEach((line) => {
      line.addEventListener("click", (e) => {
        e.stopPropagation();
        const t = parseFloat(line.dataset.temp);
        if (!isNaN(t) && this._activeModalZone) {
          this._activeModalZone.target_num = t;
          this._activeModalZone.target_temp = t.toFixed(1);
          this._setCursorPosition(t, true);
          this._updateModalBackgroundOnly(t);
          this._applyTargetTemperature(this._activeModalZone, t, 600);
        }
      });
    });

    // Boutons − et + sur le curseur
    this.querySelector("#btnCursorMinus")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._adjustCursorTemp(-0.5);
    });

    this.querySelector("#btnCursorPlus")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._adjustCursorTemp(0.5);
    });
  }

  _adjustCursorTemp(delta) {
    if (!this._activeModalZone) return;
    let t = (this._activeModalZone.target_num || 20.0) + delta;
    t = Math.max(5.0, Math.min(30.0, Math.round(t * 2) / 2));
    this._activeModalZone.target_num = t;
    this._activeModalZone.target_temp = t.toFixed(1);
    this._setCursorPosition(t, true);
    this._updateModalBackgroundOnly(t);
    this._applyTargetTemperature(this._activeModalZone, t, 650);
  }

  _setCursorPosition(temp, animate = true) {
    const card = this.querySelector("#modalThermostatCard");
    const cursor = this.querySelector("#thermostatSlidingCursor");
    if (!card || !cursor) return;

    const t = Math.max(5.0, Math.min(30.0, parseFloat(temp) || 20.0));
    const cursorHeight = cursor.offsetHeight || 140;
    const cardHeight = card.clientHeight || 420;
    const paddingTop = 30;
    const paddingBottom = 30;
    const travel = cardHeight - paddingTop - paddingBottom - cursorHeight;
    if (travel <= 0) return;

    const ratio = (t - 5.0) / 25.0;
    const topPos = paddingTop + (1.0 - ratio) * travel;

    cursor.style.transition = animate ? "top 0.26s cubic-bezier(0.16, 1, 0.3, 1)" : "none";
    cursor.style.top = `${topPos}px`;

    const targetBig = this.querySelector("#modalTargetBig");
    if (targetBig) {
      targetBig.textContent = this._activeModalZone && this._activeModalZone.state === "off" ? "OFF" : t.toFixed(1);
    }
    this._updateModalBackgroundOnly(t);
  }

  _updateModalBackgroundOnly(temp) {
    const card = this.querySelector("#roomModalCard");
    if (card && this._activeModalZone) {
      const curTemp = parseFloat(this._activeModalZone.current_temp) || temp;
      const curColor = interpolateColor(curTemp);
      const tgtColor = interpolateColor(temp);
      card.style.background = `linear-gradient(to top, rgba(${curColor.r}, ${curColor.g}, ${curColor.b}, 0.55) 0%, rgba(${tgtColor.r}, ${tgtColor.g}, ${tgtColor.b}, 0.65) 100%), #131928`;
    }
  }

  _applyTargetTemperature(zone, temp, debounceMs = 650) {
    if (!zone || !zone.entity_id) return;
    if (!this._tempDebounceTimers) {
      this._tempDebounceTimers = {};
    }
    const entityId = zone.entity_id;
    if (this._tempDebounceTimers[entityId]) {
      clearTimeout(this._tempDebounceTimers[entityId]);
    }

    if (debounceMs <= 0) {
      this._callService("climate", "set_temperature", {
        entity_id: zone.entity_id,
        temperature: temp,
      });
      return;
    }

    this._tempDebounceTimers[entityId] = setTimeout(() => {
      this._callService("climate", "set_temperature", {
        entity_id: zone.entity_id,
        temperature: temp,
      });
      delete this._tempDebounceTimers[entityId];
    }, debounceMs);
  }

  _openModal(zone) {
    this._activeModalZone = zone;
    this._activeModalZoneId = zone.zone_id;
    this._updateModalView(zone, true);
    const overlay = this.querySelector("#roomModalOverlay");
    if (overlay) overlay.classList.add("open");

    // Positionner le curseur une fois la modale visible
    setTimeout(() => {
      this._setCursorPosition(zone.target_num, false);
    }, 50);
  }

  _closeModal() {
    this._activeModalZone = null;
    this._activeModalZoneId = null;
    const overlay = this.querySelector("#roomModalOverlay");
    if (overlay) overlay.classList.remove("open");
  }

  _updateModalView(z, syncPosition = true) {
    if (!z) return;
    const card = this.querySelector("#roomModalCard");
    const colors = this._getTempColor(z.target_num, z.state);

    if (card) {
      card.style.backgroundColor = colors.bg;
    }

    const titleEl = this.querySelector("#modalRoomTitle");
    if (titleEl) titleEl.textContent = z.name;

    const iconPlaceholder = this.querySelector("#modalDeviceIconPlaceholder");
    if (iconPlaceholder) {
      iconPlaceholder.innerHTML = getDeviceSvg(z.primary_device_type, 22, colors.accent);
    }

    const actuelEl = this.querySelector("#modalActuelVal");
    if (actuelEl) actuelEl.textContent = `${z.current_temp}°`;

    const humiditeEl = this.querySelector("#modalHumiditeVal");
    if (humiditeEl) humiditeEl.textContent = z.humidity;

    const targetBigEl = this.querySelector("#modalTargetBig");
    if (targetBigEl) targetBigEl.textContent = z.state === "off" ? "OFF" : z.target_num.toFixed(1);

    if (syncPosition && !this._cursorDragActive) {
      this._setCursorPosition(z.target_num, false);
    }

    const btnOff = this.querySelector("#modalModeOff");
    const btnAuto = this.querySelector("#modalModeAuto");
    const btnHeat = this.querySelector("#modalModeHeat");

    btnOff?.classList.toggle("active", z.state === "off");
    btnAuto?.classList.toggle("active", z.state === "auto" && !z.is_overlay);
    btnHeat?.classList.toggle("active", z.state === "heat" || z.is_overlay);

    const valPuissance = this.querySelector("#modalValPuissance");
    if (valPuissance) valPuissance.textContent = `${z.heating_power}%`;

    const pillSecurite = this.querySelector("#modalPillSecurite");
    const valSecurite = this.querySelector("#modalValSecurite");
    if (pillSecurite && valSecurite) {
      pillSecurite.classList.toggle("active-pill", z.child_locked);
      valSecurite.textContent = z.child_locked ? "VERROUILLÉ" : "DÉVERROUILLÉ";
    }

    this._renderSparkline(z);
  }

  _renderSparkline(z) {
    const sparkCurrent = this.querySelector("#modalSparklineCurrent");
    if (sparkCurrent) sparkCurrent.textContent = `${z.current_temp}°C`;

    const linePath = this.querySelector("#sparklineLine");
    const areaPath = this.querySelector("#sparklineArea");
    if (!linePath || !areaPath) return;

    const cur = parseFloat(z.current_temp) || 20.0;
    const tgt = z.target_num || 20.0;
    const pts = [
      cur - 0.5,
      cur - 0.3,
      cur - 0.6,
      cur - 0.2,
      cur + 0.2,
      cur,
      tgt > cur ? cur + (tgt - cur) * 0.4 : cur,
      cur
    ];

    const min = Math.min(...pts) - 0.5;
    const max = Math.max(...pts) + 0.5;
    const range = (max - min) || 1;

    const width = 320;
    const height = 34;
    const coords = pts.map((p, i) => {
      const x = (i / (pts.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 8) - 4;
      return { x, y };
    });

    let dLine = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
      const prev = coords[i - 1];
      const curr = coords[i];
      const cx = (prev.x + curr.x) / 2;
      dLine += ` C ${cx} ${prev.y}, ${cx} ${curr.y}, ${curr.x} ${curr.y}`;
    }

    const dArea = `${dLine} L ${width} 38 L 0 38 Z`;
    linePath.setAttribute("d", dLine);
    areaPath.setAttribute("d", dArea);
  }

  _callService(domain, service, data) {
    if (this._hass) {
      this._hass.callService(domain, service, data);
    }
  }

  _updateData() {
    const data = this._extractData();

    const outdoorEl = this.querySelector("#outdoor-temp-display");
    if (outdoorEl) outdoorEl.textContent = `${data.outdoor_temp} EXT`;

    const activeBadge = this.querySelector("#active-heating-count");
    if (activeBadge) activeBadge.textContent = `${data.active_count} en chauffe`;

    // Mise à jour Quota API Tado (Header et Carte Dédiée)
    if (data.rate_limit) {
      const rl = data.rate_limit;
      const limit = rl.limit ?? 1000;
      const remaining = rl.remaining;
      const used = rl.used;

      // 1. Header Badge
      const quotaBadge = this.querySelector("#apiQuotaBadge");
      const quotaDisplay = this.querySelector("#api-quota-display");
      if (quotaDisplay) {
        const usedTxt = used != null ? `${used}` : "--";
        const remTxt = remaining != null ? `${remaining}` : (used != null && limit != null ? `${Math.max(0, limit - used)}` : "--");
        quotaDisplay.textContent = `${usedTxt} faites / ${remTxt} rest.`;

        if (quotaBadge) {
          if (remaining != null && remaining <= 50) {
            quotaBadge.style.borderColor = "rgba(239, 68, 68, 0.6)";
            quotaBadge.style.color = "#f87171";
            quotaBadge.title = `ALERTE QUOTA CRITIQUE : Plus que ${remaining} requêtes restantes aujourd'hui !`;
          } else if (remaining != null && remaining <= 200) {
            quotaBadge.style.borderColor = "rgba(245, 158, 11, 0.6)";
            quotaBadge.style.color = "#fbbf24";
            quotaBadge.title = `Attention : ${remaining} requêtes restantes aujourd'hui.`;
          } else {
            quotaBadge.style.borderColor = "";
            quotaBadge.style.color = "";
            quotaBadge.title = `Requêtes API Tado : ${usedTxt} faites / ${remTxt} restantes pour aujourd'hui (cliquez pour détails)`;
          }
        }
      }

      // 2. Settings Card
      const quotaValUsed = this.querySelector("#quotaValUsed");
      const quotaValRemaining = this.querySelector("#quotaValRemaining");
      const quotaValLimit = this.querySelector("#quotaValLimit");
      const quotaProgressFill = this.querySelector("#quotaProgressFill");
      const quotaPercentLabel = this.querySelector("#quotaPercentLabel");
      const quotaResetLabel = this.querySelector("#quotaResetLabel");
      const quotaStatusPill = this.querySelector("#quotaStatusPill");

      if (quotaValUsed) {
        quotaValUsed.textContent = used != null ? `${used}` : "--";
      }
      if (quotaValRemaining) {
        const remVal = remaining != null ? remaining : (used != null && limit != null ? Math.max(0, limit - used) : null);
        quotaValRemaining.textContent = remVal != null ? `${remVal}` : "--";
        if (remVal != null && remVal <= 50) {
          quotaValRemaining.style.color = "#f87171";
        } else if (remVal != null && remVal <= 200) {
          quotaValRemaining.style.color = "#fbbf24";
        } else {
          quotaValRemaining.style.color = "#38bdf8";
        }
      }
      if (quotaValLimit) {
        quotaValLimit.textContent = `${limit}`;
      }

      if (quotaProgressFill && quotaPercentLabel) {
        let percent = 0;
        if (used != null && limit > 0) {
          percent = Math.min(100, Math.max(0, Math.round((used / limit) * 100)));
        } else if (remaining != null && limit > 0) {
          percent = Math.min(100, Math.max(0, Math.round(((limit - remaining) / limit) * 100)));
        }
        quotaProgressFill.style.width = `${percent}%`;
        quotaPercentLabel.textContent = `${percent}% consommé (${used ?? "--"} / ${limit})`;

        if (percent >= 90) {
          quotaProgressFill.style.background = "linear-gradient(90deg, #f59e0b, #ef4444)";
          if (quotaStatusPill) {
            quotaStatusPill.textContent = "Saturé (Critique)";
            quotaStatusPill.style.background = "rgba(239, 68, 68, 0.15)";
            quotaStatusPill.style.color = "#f87171";
            quotaStatusPill.style.borderColor = "rgba(239, 68, 68, 0.3)";
          }
        } else if (percent >= 70) {
          quotaProgressFill.style.background = "linear-gradient(90deg, #10b981, #f59e0b)";
          if (quotaStatusPill) {
            quotaStatusPill.textContent = "Élevé (Attention)";
            quotaStatusPill.style.background = "rgba(245, 158, 11, 0.15)";
            quotaStatusPill.style.color = "#fbbf24";
            quotaStatusPill.style.borderColor = "rgba(245, 158, 11, 0.3)";
          }
        } else {
          quotaProgressFill.style.background = "linear-gradient(90deg, #10b981, #06b6d4)";
          if (quotaStatusPill) {
            quotaStatusPill.textContent = "Optimal";
            quotaStatusPill.style.background = "rgba(34, 197, 94, 0.15)";
            quotaStatusPill.style.color = "#4ade80";
            quotaStatusPill.style.borderColor = "rgba(34, 197, 94, 0.3)";
          }
        }
      }

      if (quotaResetLabel) {
        if (rl.reset_seconds != null && rl.reset_seconds > 0) {
          const hrs = Math.floor(rl.reset_seconds / 3600);
          const mins = Math.floor((rl.reset_seconds % 3600) / 60);
          quotaResetLabel.textContent = `Réinitialisation du quota dans ${hrs > 0 ? `${hrs}h ` : ""}${mins}min`;
        } else {
          quotaResetLabel.textContent = "Plafond journalier Tado réinitialisé toutes les 24h";
        }
      }
    }

    this._renderFilterChips(data.labels);

    const grid = this.querySelector("#tado-grid");
    if (!grid) return;

    if (!this._cardsMap) {
      this._cardsMap = new Map();
    }

    const currentZoneIds = new Set(data.zones.map((z) => String(z.zone_id)));

    for (const [zid, cardEl] of this._cardsMap.entries()) {
      if (!currentZoneIds.has(zid)) {
        cardEl.remove();
        this._cardsMap.delete(zid);
      }
    }

    for (const z of data.zones) {
      const zid = String(z.zone_id);
      let card = this._cardsMap.get(zid);
      const style = getCardBackgroundStyle(z);

      if (!card) {
        card = document.createElement("div");
        card.className = "room-card";
        card.dataset.zoneId = zid;
        grid.appendChild(card);
        this._cardsMap.set(zid, card);
      }

      card.style.background = style.background;
      card.style.borderColor = style.borderColor;
      card.style.boxShadow = style.boxShadow;
      card.style.setProperty("--pulse-color", style.glow);
      card.style.setProperty("--pulse-rgb", style.rgb);

      card.classList.toggle("heating-pulse", z.is_heating);

      const isVisible = this._selectedLabel === "__ALL__" || z.labels.includes(this._selectedLabel);
      card.style.display = isVisible ? "flex" : "none";

      const sig = `${z.name}|${z.current_temp}|${z.target_temp}|${z.state}|${z.heating_power}|${z.open_window}|${z.child_locked}|${z.labels.join(",")}|${z.primary_device_type}`;
      if (card._sig !== sig) {
        card._sig = sig;

        const deviceSvg = getDeviceSvg(z.primary_device_type, 38, style.accentColor);
        const labelsHtml = z.labels.map((lbl) => `<span class="room-mini-label">${lbl}</span>`).join("");

        card.innerHTML = `
          <div class="room-card-header">
            <span class="current-temp-label">${z.current_temp}°C</span>
            <div class="room-indicators">
              ${z.open_window ? `<span class="indicator-badge window">🪟 Ouverte</span>` : ""}
              ${z.is_heating ? `<span class="indicator-badge flame">🔥 ${z.heating_power}%</span>` : ""}
              ${z.child_locked ? `<span class="indicator-badge">🔒</span>` : ""}
            </div>
          </div>

          <div class="room-dial-wrapper">
            <div class="room-ring ${z.is_heating ? "active-heat" : ""}" style="border-color: ${style.accentColor}; box-shadow: 0 0 14px ${style.glow};">
              ${deviceSvg}
            </div>
            <div class="room-name">${z.name}</div>
            <div class="room-labels-container">${labelsHtml}</div>
            <div class="room-quick-adjust">
              <button class="quick-step-btn btn-quick-minus" title="Baisser de 0.5°C">−</button>
              <span class="quick-target-val">${z.state === "off" ? "Éteinte" : `${z.target_temp}°`}</span>
              <button class="quick-step-btn btn-quick-plus" title="Monter de 0.5°C">+</button>
            </div>
          </div>

          <div class="room-card-actions">
            <button class="room-action-btn btn-room-off" title="Éteindre">⏻</button>
            <button class="room-action-btn btn-room-auto" title="Planning automatique">📅</button>
            <button class="room-action-btn btn-room-heat" title="Chauffe">🔥</button>
          </div>
        `;

        card.querySelector(".btn-quick-minus")?.addEventListener("click", (e) => {
          e.stopPropagation();
          let t = (z.target_num || 20.0) - 0.5;
          t = Math.max(5.0, Math.min(30.0, Math.round(t * 2) / 2));
          z.target_num = t;
          z.target_temp = t.toFixed(1);
          const valSpan = card.querySelector(".quick-target-val");
          if (valSpan) valSpan.textContent = `${t.toFixed(1)}°`;
          const style = getTileBackgroundGradient(z);
          card.style.background = style.background;
          card.style.borderColor = style.borderColor;
          this._applyTargetTemperature(z, t, 700);
        });

        card.querySelector(".btn-quick-plus")?.addEventListener("click", (e) => {
          e.stopPropagation();
          let t = (z.target_num || 20.0) + 0.5;
          t = Math.max(5.0, Math.min(30.0, Math.round(t * 2) / 2));
          z.target_num = t;
          z.target_temp = t.toFixed(1);
          const valSpan = card.querySelector(".quick-target-val");
          if (valSpan) valSpan.textContent = `${t.toFixed(1)}°`;
          const style = getTileBackgroundGradient(z);
          card.style.background = style.background;
          card.style.borderColor = style.borderColor;
          this._applyTargetTemperature(z, t, 700);
        });

        card.querySelector(".btn-room-off")?.addEventListener("click", (e) => {
          e.stopPropagation();
          this._callService("climate", "set_hvac_mode", { entity_id: z.entity_id, hvac_mode: "off" });
        });

        card.querySelector(".btn-room-auto")?.addEventListener("click", (e) => {
          e.stopPropagation();
          this._callService("climate", "set_hvac_mode", { entity_id: z.entity_id, hvac_mode: "auto" });
        });

        card.querySelector(".btn-room-heat")?.addEventListener("click", (e) => {
          e.stopPropagation();
          this._callService("climate", "set_hvac_mode", { entity_id: z.entity_id, hvac_mode: "heat" });
        });
      }

      card.onclick = () => this._openModal(z);
    }

    if (this._activeModalZoneId && !this._cursorDragActive) {
      const refreshedZone = data.zones.find((z) => String(z.zone_id) === String(this._activeModalZoneId));
      if (refreshedZone) {
        this._activeModalZone = refreshedZone;
        this._updateModalView(refreshedZone, false);
      }
    }
  }

  _renderFilterChips(labelsList) {
    const bar = this.querySelector("#labelsFilterBar");
    if (!bar) return;

    const currentSig = labelsList.sort().join(",");
    if (bar._sig === currentSig) return;
    bar._sig = currentSig;

    bar.innerHTML = `
      <button class="label-chip ${this._selectedLabel === "__ALL__" ? "active" : ""}" data-label="__ALL__">
        Toutes les pièces
      </button>
      ${labelsList
        .map(
          (lbl) => `
        <button class="label-chip ${this._selectedLabel === lbl ? "active" : ""}" data-label="${lbl}">
          ${lbl}
        </button>
      `
        )
        .join("")}
    `;

    bar.querySelectorAll(".label-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        bar.querySelectorAll(".label-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        this._selectedLabel = chip.dataset.label;
        this._applyLabelFilter();
      });
    });
  }

  _applyLabelFilter() {
    for (const [zid, card] of this._cardsMap.entries()) {
      if (this._selectedLabel === "__ALL__") {
        card.style.display = "flex";
      } else {
        const data = this._extractData();
        const z = data.zones.find((item) => String(item.zone_id) === zid);
        card.style.display = z && z.labels.includes(this._selectedLabel) ? "flex" : "none";
      }
    }
  }

  _renderSettingsView() {
    const data = this._extractData();

    if (Object.keys(this._settingsDraft).length === 0) {
      for (const z of data.zones) {
        this._settingsDraft[String(z.zone_id)] = [...z.labels];
      }
    }

    if (!this._sensorDraft || Object.keys(this._sensorDraft).length === 0) {
      this._sensorDraft = {};
      for (const z of data.zones) {
        this._sensorDraft[String(z.zone_id)] = Array.isArray(z.temp_sensors)
          ? [...z.temp_sensors]
          : (z.temp_sensors ? [z.temp_sensors] : []);
      }
    }

    if (!this._valveModesDraft) {
      this._valveModesDraft = { ...(data.valveModes || {}) };
    }

    // Découverte de tous les capteurs de température disponibles dans Home Assistant
    const allTempSensors = [];
    if (this._hass && this._hass.states) {
      for (const entityId of Object.keys(this._hass.states)) {
        if (!entityId.startsWith("sensor.")) continue;
        const st = this._hass.states[entityId];
        if (!st) continue;
        const dc = st.attributes?.device_class;
        const uom = st.attributes?.unit_of_measurement;
        if (dc === "temperature" || uom === "°C" || uom === "°F" || entityId.includes("temperature")) {
          const friendly = st.attributes?.friendly_name || entityId;
          const currentVal = st.state !== "unavailable" && st.state !== "unknown" ? `${parseFloat(st.state).toFixed(1)}°C` : "--";
          allTempSensors.push({
            id: entityId,
            name: friendly,
            temp: currentVal,
          });
        }
      }
      allTempSensors.sort((a, b) => a.name.localeCompare(b.name));
    }

    const listEl = this.querySelector("#roomLabelsList");
    if (listEl) {
      const datalistHtml = `
        <datalist id="allTempSensorsDatalist">
          ${allTempSensors.map((s) => `<option value="${s.id}">${s.name} (${s.temp})</option>`).join("")}
        </datalist>
      `;

      listEl.innerHTML = datalistHtml + data.zones
        .map((z) => {
          const zid = String(z.zone_id);
          const currentTags = this._settingsDraft[zid] || [];
          const currentSensors = this._sensorDraft[zid] || [];
          const availableForRoom = allTempSensors.filter((s) => !currentSensors.includes(s.id));

          const tagsHtml = currentTags
            .map(
              (tag, idx) => `
            <span class="tag-pill-badge">
              ${tag}
              <span class="tag-remove-btn" data-zid="${zid}" data-idx="${idx}">✕</span>
            </span>
          `
            )
            .join("");

          const sensorsHtml = currentSensors
            .map((sId, sIdx) => {
              const entState = this._hass?.states?.[sId];
              const sName = entState?.attributes?.friendly_name || sId;
              const sVal = entState && entState.state !== "unavailable" && entState.state !== "unknown" ? `${parseFloat(entState.state).toFixed(1)}°C` : "--";
              return `
                <span class="sensor-pill-badge" title="${sId}">
                  🌡️ ${sName} (${sVal})
                  <span class="sensor-remove-btn" data-zid="${zid}" data-idx="${sIdx}">✕</span>
                </span>
              `;
            })
            .join("");

          const sensorAdderHtml = currentSensors.length < 4
            ? `
              <div class="sensor-adder-controls">
                <input type="text" class="sensor-autocomplete-input" id="inputSensor_${zid}" list="allTempSensorsDatalist" placeholder="🔍 Taper pour chercher (${availableForRoom.length} dispo)..." autocomplete="off" />
                <button class="btn-add-sensor" data-zid="${zid}">+ Associer</button>
              </div>
            `
            : `<span class="max-sensors-notice">✓ Limite de 4 capteurs atteinte</span>`;

          const tagsPillsHtml = tagsHtml ? `<div class="pills-container">${tagsHtml}</div>` : "";
          const sensorsPillsHtml = sensorsHtml ? `<div class="pills-container">${sensorsHtml}</div>` : "";

          return `
          <div class="room-label-item">
            <div class="room-label-item-left">
              ${getDeviceSvg(z.primary_device_type, 26, "#38bdf8")}
              <span class="room-label-item-name">${z.name}</span>
            </div>

            <div class="room-section-block">
              <div class="room-section-title">🏷️ Étiquettes (Filtres) :</div>
              <div class="room-tags-editor">
                ${tagsPillsHtml}
                <div class="tag-input-row">
                  <input type="text" class="add-tag-input" id="inputTag_${zid}" placeholder="Ajouter un tag..." />
                  <button class="btn-add-tag" data-zid="${zid}">+ Ajouter</button>
                </div>
              </div>
            </div>

            <div class="room-section-block">
              <div class="room-section-title">🌡️ Capteurs de Température (${currentSensors.length}/4 max) :</div>
              <div class="room-sensors-editor">
                ${sensorsPillsHtml}
                ${sensorAdderHtml}
              </div>
            </div>
          </div>
        `;
        })
        .join("");

      listEl.querySelectorAll(".tag-remove-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const zid = btn.dataset.zid;
          const idx = parseInt(btn.dataset.idx, 10);
          if (this._settingsDraft[zid]) {
            this._settingsDraft[zid].splice(idx, 1);
            this._renderSettingsView();
          }
        });
      });

      listEl.querySelectorAll(".btn-add-tag").forEach((btn) => {
        btn.addEventListener("click", () => {
          const zid = btn.dataset.zid;
          const input = listEl.querySelector(`#inputTag_${zid}`);
          const val = input ? input.value.trim() : "";
          if (val) {
            if (!this._settingsDraft[zid]) this._settingsDraft[zid] = [];
            if (!this._settingsDraft[zid].includes(val)) {
              this._settingsDraft[zid].push(val);
            }
            input.value = "";
            this._renderSettingsView();
          }
        });
      });

      listEl.querySelectorAll(".add-tag-input").forEach((input) => {
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            const zid = input.id.replace("inputTag_", "");
            const btn = listEl.querySelector(`.btn-add-tag[data-zid="${zid}"]`);
            btn?.click();
          }
        });
      });

      listEl.querySelectorAll(".sensor-remove-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const zid = btn.dataset.zid;
          const idx = parseInt(btn.dataset.idx, 10);
          if (this._sensorDraft[zid]) {
            this._sensorDraft[zid].splice(idx, 1);
            this._renderSettingsView();
          }
        });
      });

      listEl.querySelectorAll(".btn-add-sensor").forEach((btn) => {
        btn.addEventListener("click", () => {
          const zid = btn.dataset.zid;
          const input = listEl.querySelector(`#inputSensor_${zid}`);
          let val = input ? input.value.trim() : "";
          // Vérification si la valeur entrée correspond à un friendly_name ou un entity_id
          const found = allTempSensors.find(
            (s) => s.id.toLowerCase() === val.toLowerCase() || s.name.toLowerCase() === val.toLowerCase()
          );
          if (found) val = found.id;

          if (val) {
            if (!this._sensorDraft[zid]) this._sensorDraft[zid] = [];
            if (!this._sensorDraft[zid].includes(val) && this._sensorDraft[zid].length < 4) {
              this._sensorDraft[zid].push(val);
            }
            this._renderSettingsView();
          }
        });
      });

      listEl.querySelectorAll(".sensor-autocomplete-input").forEach((input) => {
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            const zid = input.id.replace("inputSensor_", "");
            const btn = listEl.querySelector(`.btn-add-sensor[data-zid="${zid}"]`);
            btn?.click();
          }
        });
      });
    }

    const calibBody = this.querySelector("#calibrationTableBody");
    if (calibBody) {
      calibBody.innerHTML = data.allDevices
        .filter((d) => getDeviceTypeCategory(d.device_type) === "VALVE" || getDeviceTypeCategory(d.device_type) === "THERMOSTAT" || getDeviceTypeCategory(d.device_type) === "SENSOR")
        .map((d) => {
          const zone = data.zones.find(
            (z) => String(z.zone_id) === String(d.zone_id) || z.name === d.zone_name
          );
          const zid = zone ? String(zone.zone_id) : String(d.zone_id || "");
          const roomSensors = (this._sensorDraft && this._sensorDraft[zid]) || zone?.temp_sensors || [];

          // Calcul de la température moyenne des capteurs externes de la pièce
          let validTemps = [];
          let sensorDetails = [];
          if (roomSensors.length > 0 && this._hass?.states) {
            for (const sId of roomSensors) {
              const st = this._hass.states[sId];
              if (st && st.state !== "unavailable" && st.state !== "unknown") {
                const num = parseFloat(st.state);
                if (!isNaN(num)) {
                  validTemps.push(num);
                  sensorDetails.push(`${st.attributes?.friendly_name || sId}: ${num.toFixed(1)}°C`);
                }
              }
            }
          }

          const hasSensors = roomSensors.length > 0 && validTemps.length > 0;
          const avgTemp = hasSensors
            ? (validTemps.reduce((acc, v) => acc + v, 0) / validTemps.length).toFixed(1)
            : null;

          // Mode actuel : AUTO vs MANUEL
          const currentMode = this._valveModesDraft?.[d.serial] || data.valveModes?.[d.serial] || "MANUAL";
          const isAuto = hasSensors && currentMode === "AUTO";

          // Calcul de l'offset cible
          const currOffset = d.offset != null ? parseFloat(d.offset) : 0.0;
          const rawTemp = parseFloat(d.raw_inside_temperature ?? zone?.raw_inside_temp ?? zone?.current_temp);
          let targetOffset = currOffset;
          if (hasSensors && !isNaN(rawTemp)) {
            const diff = parseFloat(avgTemp) - rawTemp;
            targetOffset = Math.round(Math.max(-5.0, Math.min(5.0, currOffset + diff)) * 10) / 10;
          }

          const displayedOffset = isAuto ? targetOffset : currOffset;

          const modeHtml = hasSensors
            ? `
              <td>
                <div class="calib-mode-toggle" data-serial="${d.serial}">
                  <button class="calib-mode-btn ${!isAuto ? 'active-manual' : ''}" data-serial="${d.serial}" data-mode="MANUAL">MANUEL</button>
                  <button class="calib-mode-btn ${isAuto ? 'active-auto' : ''}" data-serial="${d.serial}" data-mode="AUTO">AUTO</button>
                </div>
              </td>
            `
            : `<td><span style="color: #64748b; font-size: 11px;">—</span></td>`;

          const avgBadgeHtml = hasSensors
            ? `
              <td>
                <span class="calib-avg-badge" title="${sensorDetails.join('\n')}">
                  🌡️ ${avgTemp}°C <small>(${validTemps.length})</small>
                </span>
              </td>
            `
            : `<td><span style="color: #64748b; font-size: 11px;">—</span></td>`;

          return `
          <tr>
            <td>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${getDeviceSvg(d.device_type, 24, "#38bdf8")}
                <strong>${d.device_type}</strong>
              </div>
            </td>
            <td>${d.zone_name}</td>
            <td><code>${d.serial}</code></td>
            <td>
              <div class="calibration-stepper">
                <input type="range" min="-5.0" max="5.0" step="0.1" value="${displayedOffset.toFixed(1)}" id="sliderCalib_${d.serial}" style="width: 120px; ${isAuto ? 'opacity: 0.6; cursor: not-allowed;' : ''}" ${isAuto ? 'disabled' : ''} />
                <span class="calib-val-badge" id="badgeCalib_${d.serial}">${displayedOffset > 0 ? '+' : ''}${displayedOffset.toFixed(1)}°C</span>
              </div>
            </td>
            ${modeHtml}
            ${avgBadgeHtml}
            <td>
              <button class="btn-apply-offset" data-serial="${d.serial}" ${isAuto ? 'disabled style="opacity: 0.4; cursor: not-allowed;"' : ''}>${isAuto ? 'Auto-calibré' : 'Appliquer'}</button>
            </td>
          </tr>
        `;
        })
        .join("");

      calibBody.querySelectorAll(".calib-mode-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const serial = btn.dataset.serial;
          const mode = btn.dataset.mode;
          if (!this._valveModesDraft) this._valveModesDraft = {};
          this._valveModesDraft[serial] = mode;

          this._callService("domolink_tado", "set_valve_calibration_mode", {
            device_serial: serial,
            mode: mode,
          });

          this._renderSettingsView();
        });
      });

      calibBody.querySelectorAll("input[type='range']").forEach((slider) => {
        const serial = (slider.id || "").replace("sliderCalib_", "");
        const badge = calibBody.querySelector(`#badgeCalib_${serial}`);
        slider.addEventListener("input", () => {
          const val = parseFloat(slider.value).toFixed(1);
          if (badge) badge.textContent = `${val > 0 ? "+" : ""}${val}°C`;
        });
      });

      calibBody.querySelectorAll(".btn-apply-offset").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (btn.disabled) return;
          const serial = btn.dataset.serial;
          const slider = calibBody.querySelector(`#sliderCalib_${serial}`);
          const offset = slider ? parseFloat(slider.value) : 0.0;
          this._callService("domolink_tado", "set_temperature_offset", {
            device_serial: serial,
            offset: offset,
          });
          btn.textContent = "✓ Appliqué";
          setTimeout(() => { btn.textContent = "Appliquer"; }, 2000);
        });
      });
    }

    const hwBody = this.querySelector("#hardwareTableBody");
    if (hwBody) {
      hwBody.innerHTML = data.allDevices
        .map(
          (d) => `
          <tr>
            <td>
              <div style="display: flex; align-items: center; gap: 8px;">
                ${getDeviceSvg(d.device_type, 22, "#94a3b8")}
                <span>${d.device_type}</span>
              </div>
            </td>
            <td><code>${d.serial}</code></td>
            <td>${d.zone_name}</td>
            <td>
              <span style="color: ${d.battery_state === 'NORMAL' ? '#10b981' : '#ef4444'}; font-weight: 700;">
                ${d.battery_percentage}
              </span>
            </td>
            <td>
              <span style="color: #38bdf8; font-weight: 700;">● En ligne</span>
            </td>
            <td><code>${d.current_firmware}</code></td>
          </tr>
        `
        )
        .join("");
    }
  }

  _saveAllLabelsFromDraft() {
    this._callService("domolink_tado", "save_room_labels", {
      labels: this._settingsDraft,
    });
    if (this._sensorDraft) {
      this._callService("domolink_tado", "save_room_sensors", {
        sensors: this._sensorDraft,
      });
    }
    const saveBtn = this.querySelector("#btnSaveLabels");
    if (saveBtn) {
      saveBtn.textContent = "✓ Paramètres enregistrés !";
      setTimeout(() => {
        saveBtn.textContent = "💾 Sauvegarder les paramètres";
      }, 2500);
    }
  }
}

/* =========================================================================
 * 🎆 SOCRATE RULES - EASTER EGG MODULE
 * ========================================================================= */
function launchSocrateRulesEasterEgg(targetRoot) {
  if (targetRoot.getElementById?.("socrate-rules-overlay") || targetRoot.querySelector?.("#socrate-rules-overlay")) return;

  if (!document.getElementById("socrate-rules-fonts")) {
    const fontLink = document.createElement("link");
    fontLink.id = "socrate-rules-fonts";
    fontLink.rel = "stylesheet";
    fontLink.href = "https://fonts.googleapis.com/css2?family=Orbitron:wght@500;900&family=Poppins:wght@300;600&display=swap";
    document.head.appendChild(fontLink);
  }

  const overlay = document.createElement("div");
  overlay.id = "socrate-rules-overlay";
  overlay.innerHTML = `
    <style>
      #socrate-rules-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: 999999;
        background-color: #030008;
        font-family: 'Poppins', sans-serif;
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
        user-select: none;
        -webkit-user-select: none;
        opacity: 0;
        transition: opacity 0.35s ease, transform 0.35s ease;
      }
      #socrate-rules-overlay * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }
      #socrate-rules-overlay canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 1;
        pointer-events: none;
      }
      #socrate-rules-overlay .socrate-container {
        position: relative;
        z-index: 10;
        text-align: center;
        pointer-events: auto;
      }
      #socrate-rules-overlay h1.socrate-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 6.5rem;
        font-weight: 900;
        letter-spacing: 12px;
        text-transform: uppercase;
        display: inline-block;
        line-height: 1.1;
        filter: 
          drop-shadow(0px 1px 0px #990066)
          drop-shadow(0px 2px 0px #660066)
          drop-shadow(0px 3px 0px #330066)
          drop-shadow(0px 4px 0px #1a0033)
          drop-shadow(0px 12px 15px rgba(0,0,0,0.9))
          drop-shadow(0 0 25px rgba(127, 0, 255, 0.6));
        transition: transform 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275), filter 0.5s;
        cursor: pointer;
      }
      #socrate-rules-overlay h1.socrate-title:hover {
        transform: scale(1.05);
        filter: 
          drop-shadow(0px 1px 0px #ff007f)
          drop-shadow(0px 2px 0px #990066)
          drop-shadow(0px 3px 0px #660066)
          drop-shadow(0px 4px 0px #330066)
          drop-shadow(0px 5px 0px #1a0033)
          drop-shadow(0px 15px 20px rgba(0,0,0,0.9))
          drop-shadow(0 0 40px rgba(0, 240, 255, 0.9));
      }
      #socrate-rules-overlay .socrate-letter {
        display: inline-block;
        background: linear-gradient(
          to bottom,
          #ff66b3 0%,
          #ff007f 35%,
          #7f00ff 65%,
          #00f0ff 100%
        );
        background-size: 100% 100%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: socrate-wave 1.6s ease-in-out infinite;
      }
      #socrate-rules-overlay p.socrate-sub {
        font-size: 1.1rem;
        color: rgba(255, 255, 255, 0.6);
        margin-top: 30px;
        letter-spacing: 4px;
        text-transform: uppercase;
        font-weight: 300;
        opacity: 0;
        animation: socrate-fadeIn 2s ease forwards 0.8s;
      }
      #socrate-rules-overlay p.socrate-sub strong {
        color: #00f0ff;
        font-weight: 600;
        text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);
      }
      #socrate-rules-overlay p.socrate-exit-hint {
        font-size: 0.95rem;
        color: rgba(255, 255, 255, 0.6);
        margin-top: 16px;
        letter-spacing: 2px;
        text-transform: uppercase;
        font-weight: 300;
        opacity: 0;
        animation: socrate-fadeIn 2s ease forwards 1.1s;
        cursor: pointer;
      }
      #socrate-rules-overlay p.socrate-exit-hint strong {
        color: #ff007f;
        font-weight: 700;
        text-shadow: 0 0 10px rgba(255, 0, 127, 0.6);
      }
      #socrate-rules-overlay .socrate-instructions {
        position: absolute;
        bottom: 40px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 10;
        color: rgba(255, 255, 255, 0.4);
        font-size: 0.8rem;
        letter-spacing: 2px;
        text-transform: uppercase;
        pointer-events: none;
        animation: socrate-pulse 2s infinite;
        text-align: center;
        white-space: nowrap;
      }
      @keyframes socrate-wave {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-25px); }
      }
      @keyframes socrate-fadeIn {
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes socrate-pulse {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.8; }
      }
      @media (max-width: 768px) {
        #socrate-rules-overlay h1.socrate-title {
          font-size: 3rem;
          letter-spacing: 6px;
        }
      }
    </style>
    <canvas id="socrateParticleCanvas"></canvas>
    <div class="socrate-container">
      <h1 class="socrate-title" id="socrateTitle">Socrate Rules</h1>
      <p class="socrate-sub" id="socrateSub">Une expérience visuelle <strong>hautement philosophique</strong>.</p>
      <p class="socrate-exit-hint" id="socrateExitHint">Cliquez 3 fois sur <strong>SOCRATE RULES</strong> pour quitter</p>
    </div>
    <div class="socrate-instructions" id="socrateInstructions">Bougez votre souris & cliquez n'importe où</div>
  `;

  targetRoot.appendChild(overlay);

  requestAnimationFrame(() => {
    overlay.style.opacity = "1";
  });

  const canvas = overlay.querySelector("#socrateParticleCanvas");
  const ctx = canvas.getContext("2d");
  const title = overlay.querySelector("#socrateTitle");

  title.innerHTML = title.textContent
    .split("")
    .map((char, index) => {
      if (char === " ") return "&nbsp;";
      return `<span class="socrate-letter" style="animation-delay: ${index * 0.08}s">${char}</span>`;
    })
    .join("");

  let width, height;
  function resizeCanvas() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  resizeCanvas();

  const mouse = { x: width / 2, y: height / 2, radius: 180, isDown: false };
  const sparksArray = [];
  const sparksLimit = 400;

  class Spark {
    constructor(x, y) {
      this.x = x !== undefined ? x : Math.random() * width;
      this.y = y !== undefined ? y : Math.random() * height;
      this.vx = (Math.random() - 0.5) * 6;
      this.vy = (Math.random() - 0.5) * 6;
      this.size = Math.random() * 2.5 + 1;
      this.life = 0;
      this.maxLife = Math.random() * 80 + 40;
      const hues = [320, 280, 190, 45];
      this.hue = hues[Math.floor(Math.random() * hues.length)];
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.vx *= 0.96;
      this.vy *= 0.96;
      this.life++;
      if (this.size > 0.1) this.size -= 0.015;
    }
    draw() {
      const progress = this.life / this.maxLife;
      const alpha = Math.max(0, 1 - progress);
      ctx.save();
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${this.hue}, 100%, 65%, ${alpha})`;
      ctx.shadowBlur = 12;
      ctx.shadowColor = `hsla(${this.hue}, 100%, 50%, 0.8)`;
      ctx.fill();
      ctx.restore();
    }
  }

  const particlesArray = [];
  const numberOfParticles = Math.min(120, Math.floor((width * height) / 12000));

  class BackgroundParticle {
    constructor() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.size = Math.random() * 2 + 1;
      this.baseX = this.x;
      this.baseY = this.y;
      this.density = Math.random() * 20 + 1;
      this.vx = (Math.random() - 0.5) * 0.8;
      this.vy = (Math.random() - 0.5) * 0.8;
      this.color = Math.random() > 0.5 ? "rgba(0, 240, 255," : "rgba(255, 0, 127,";
    }
    update() {
      this.baseX += this.vx;
      this.baseY += this.vy;
      if (this.baseX < 0 || this.baseX > width) this.vx = -this.vx;
      if (this.baseY < 0 || this.baseY > height) this.vy = -this.vy;

      const dx = mouse.x - this.x;
      const dy = mouse.y - this.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (distance < mouse.radius) {
        const force = (mouse.radius - distance) / mouse.radius;
        const directionX = (dx / distance) * force * this.density;
        const directionY = (dy / distance) * force * this.density;
        this.x -= directionX * 3;
        this.y -= directionY * 3;
      } else {
        if (this.x !== this.baseX) {
          const dxBase = this.x - this.baseX;
          this.x -= dxBase * 0.05;
        }
        if (this.y !== this.baseY) {
          const dyBase = this.y - this.baseY;
          this.y -= dyBase * 0.05;
        }
      }
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `${this.color} 0.55)`;
      ctx.fill();
    }
  }

  function initParticles() {
    for (let i = 0; i < numberOfParticles; i++) {
      particlesArray.push(new BackgroundParticle());
    }
  }

  let animId = null;
  let isClosing = false;

  function animate() {
    ctx.fillStyle = "rgba(3, 0, 8, 0.25)";
    ctx.fillRect(0, 0, width, height);

    for (let i = 0; i < particlesArray.length; i++) {
      particlesArray[i].update();
      particlesArray[i].draw();
      for (let j = i + 1; j < particlesArray.length; j++) {
        const dx = particlesArray[i].x - particlesArray[j].x;
        const dy = particlesArray[i].y - particlesArray[j].y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 110) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(127, 0, 255, ${0.35 - distance / 320})`;
          ctx.lineWidth = 0.7;
          ctx.moveTo(particlesArray[i].x, particlesArray[i].y);
          ctx.lineTo(particlesArray[j].x, particlesArray[j].y);
          ctx.stroke();
        }
      }
    }

    for (let i = 0; i < sparksArray.length; i++) {
      sparksArray[i].update();
      sparksArray[i].draw();
      if (sparksArray[i].life >= sparksArray[i].maxLife || sparksArray[i].size <= 0.1) {
        sparksArray.splice(i, 1);
        i--;
      }
    }

    animId = requestAnimationFrame(animate);
  }

  function onMouseMove(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    if (sparksArray.length < sparksLimit) {
      for (let i = 0; i < 2; i++) {
        sparksArray.push(new Spark(mouse.x, mouse.y));
      }
    }
  }
  function onTouchMove(e) {
    if (e.touches.length > 0) {
      mouse.x = e.touches[0].clientX;
      mouse.y = e.touches[0].clientY;
      for (let i = 0; i < 3; i++) {
        sparksArray.push(new Spark(mouse.x, mouse.y));
      }
    }
  }
  function onOverlayClick(e) {
    const x = e.clientX || window.innerWidth / 2;
    const y = e.clientY || window.innerHeight / 2;
    for (let i = 0; i < 30; i++) {
      sparksArray.push(new Spark(x, y));
    }
  }

  window.addEventListener("resize", resizeCanvas);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("touchmove", onTouchMove, { passive: true });
  overlay.addEventListener("click", onOverlayClick);

  let exitClicks = [];
  function handleExitClick(clientX, clientY) {
    if (isClosing) return;
    const now = Date.now();
    exitClicks = exitClicks.filter((t) => now - t < 2000);
    exitClicks.push(now);

    const x = clientX || window.innerWidth / 2;
    const y = clientY || window.innerHeight / 2;
    for (let i = 0; i < 60; i++) {
      sparksArray.push(new Spark(x, y));
    }

    if (exitClicks.length >= 3) {
      isClosing = true;
      exitClicks = [];
      for (let i = 0; i < 120; i++) {
        sparksArray.push(new Spark(window.innerWidth / 2, window.innerHeight / 2));
      }
      overlay.style.transition = "opacity 0.38s ease, transform 0.38s ease";
      overlay.style.opacity = "0";
      overlay.style.transform = "scale(1.05)";
      setTimeout(() => {
        cleanup();
      }, 360);
    }
  }

  title.addEventListener("click", (e) => {
    e.stopPropagation();
    handleExitClick(e.clientX, e.clientY);
  });

  const exitHint = overlay.querySelector("#socrateExitHint");
  if (exitHint) {
    exitHint.addEventListener("click", (e) => {
      e.stopPropagation();
      handleExitClick(e.clientX, e.clientY);
    });
  }

  function cleanup() {
    if (animId) {
      cancelAnimationFrame(animId);
      animId = null;
    }
    window.removeEventListener("resize", resizeCanvas);
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("touchmove", onTouchMove);
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }

  initParticles();
  animate();
}

/* =========================================================================
 * 🔌 CUSTOM ELEMENT & LOVELACE CARD REGISTRATION
 * ========================================================================= */
class DomolinkTadoCard extends DomolinkTadoPanel {
  setConfig(config) {
    super.setConfig(config);
  }
}

if (!customElements.get("domolink-tado-panel")) {
  customElements.define("domolink-tado-panel", DomolinkTadoPanel);
}
if (!customElements.get("domolink_tado-panel")) {
  customElements.define("domolink_tado-panel", DomolinkTadoPanel);
}
if (!customElements.get("domolink-tado-card")) {
  customElements.define("domolink-tado-card", DomolinkTadoCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "domolink-tado-card")) {
  window.customCards.push({
    type: "domolink-tado-card",
    name: "DomoLink-Tado Card",
    description: "Panneau de pilotage complet haute résolution pour radiateurs et thermostats Tado",
    preview: true,
  });
}
