/**
 * DomoLink-Tado — Panneau Tactile Haute Résolution
 * Interface moderne inspirée de la suite DomoLink avec tuile globale 4 quadrants,
 * grille des pièces, et modale immersive à couleur adaptative et jauge tactile verticale.
 */

class DomolinkTadoPanel extends HTMLElement {
  constructor() {
    super();
    this._initialized = false;
    this._activeModalZoneId = null;
    this._sliderDragActive = false;
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

  connectedCallback() {
    if (this._hass && !this._initialized) {
      this._initialized = true;
      this._renderLayout();
      this._updateData();
    }
  }

  _extractData() {
    if (!this._hass) return { zones: [], weather: {}, activeCount: 0 };
    const states = this._hass.states;

    // Détecter toutes les entités climate de DomoLink-Tado ou tado
    const climateKeys = Object.keys(states).filter((k) =>
      k.startsWith("climate.") && (k.includes("domolink_tado") || k.includes("tado"))
    );

    const zones = [];
    let activeCount = 0;

    for (const key of climateKeys) {
      const entity = states[key];
      if (!entity) continue;

      const attrs = entity.attributes || {};
      const zoneId = attrs.zone_id || key;
      const name = attrs.friendly_name?.replace(/^Tado\s+/i, "") || key;
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

      zones.push({
        entity_id: key,
        zone_id: zoneId,
        name: name,
        state: entity.state, // auto, heat, off
        current_temp: currentTemp,
        target_temp: targetTemp,
        target_num: parseFloat(attrs.temperature) || 20.0,
        humidity: humidity,
        heating_power: heatingPower,
        is_heating: isHeating,
        is_overlay: isOverlay,
        open_window: openWindow,
        child_locked: childLocked,
        devices: devices,
      });
    }

    // Données météo Tado
    const outdoorSensor = Object.keys(states).find(
      (k) => k.includes("domolink_tado") && k.includes("outdoor_temp")
    );
    const outdoorVal = outdoorSensor && states[outdoorSensor]?.state;
    const outdoorTemp = outdoorVal && outdoorVal !== "unavailable" ? `${parseFloat(outdoorVal).toFixed(1)}°` : "--°";

    return {
      zones: zones,
      outdoor_temp: outdoorTemp,
      active_count: activeCount,
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
    if (targetNum < 18.0) {
      return {
        bg: "#065f46",
        accent: "#10b981",
        glow: "rgba(16, 185, 129, 0.4)",
      };
    }
    if (targetNum <= 21.5) {
      return {
        bg: "#d97706",
        accent: "#f59e0b",
        glow: "rgba(245, 158, 11, 0.45)",
      };
    }
    return {
      bg: "#b91c1c",
      accent: "#ef4444",
      glow: "rgba(239, 68, 68, 0.5)",
    };
  }

  _renderLayout() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100vh;
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

        /* ── Top Bar ── */
        .tado-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 28px;
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

        /* ── Main Grid ── */
        .tado-dashboard-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 20px;
        }

        /* ── 4-Quadrant Quick Tile ── */
        .global-control-tile {
          background: #192038;
          border-radius: 20px;
          display: grid;
          grid-template-columns: 1fr 1fr;
          grid-template-rows: 1fr 1fr;
          min-height: 200px;
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
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.2s ease;
          user-select: none;
        }

        .quadrant-btn:hover {
          background: rgba(255, 255, 255, 0.06);
        }

        .quadrant-btn:active {
          transform: scale(0.96);
        }

        .quadrant-btn svg, .quadrant-btn span.q-icon {
          font-size: 22px;
        }

        .quad-off { border-right: 1px solid rgba(255, 255, 255, 0.08); border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
        .quad-boost { border-bottom: 1px solid rgba(255, 255, 255, 0.08); }
        .quad-prog { border-right: 1px solid rgba(255, 255, 255, 0.08); }
        .quad-outdoor { pointer-events: none; }

        /* ── Room Cards ── */
        .room-card {
          background: #1a2236;
          border-radius: 20px;
          padding: 18px;
          position: relative;
          min-height: 200px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          cursor: pointer;
          transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
          border: 1px solid rgba(255, 255, 255, 0.06);
          user-select: none;
        }

        .room-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
          border-color: rgba(56, 189, 248, 0.35);
        }

        .room-card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .current-temp-label {
          font-size: 16px;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.85);
        }

        .room-indicators {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .indicator-badge {
          font-size: 11px;
          padding: 2px 6px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.7);
        }

        .indicator-badge.flame {
          background: rgba(239, 68, 68, 0.2);
          color: #ef4444;
        }

        .indicator-badge.window {
          background: rgba(56, 189, 248, 0.2);
          color: #38bdf8;
        }

        /* ── Center Dial ── */
        .room-dial-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 10px 0;
          position: relative;
        }

        .room-ring {
          width: 82px;
          height: 82px;
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
          box-shadow: 0 0 18px rgba(245, 158, 11, 0.35);
        }

        .room-ring-inner-icon {
          font-size: 24px;
          opacity: 0.6;
        }

        .room-name {
          font-size: 16px;
          font-weight: 700;
          margin-top: 10px;
          text-align: center;
          color: #ffffff;
        }

        .target-temp-label {
          font-size: 13px;
          color: rgba(255, 255, 255, 0.55);
          margin-top: 2px;
          text-align: center;
        }

        /* ── Action Buttons on Room Card ── */
        .room-card-actions {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          margin-top: 10px;
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

        /* ── MODAL POPUP (Image 2) ── */
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          width: 100vw;
          height: 100vh;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(8px);
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
          width: 90%;
          max-width: 440px;
          height: 92vh;
          max-height: 860px;
          border-radius: 44px;
          padding: 24px 24px 30px 24px;
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: relative;
          box-shadow: 0 25px 60px rgba(0, 0, 0, 0.5);
          transition: background-color 0.4s ease;
          overflow: hidden;
        }

        .modal-close-btn {
          width: 44px;
          height: 44px;
          border-radius: 16px;
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: absolute;
          top: 24px;
          left: 24px;
          z-index: 10;
        }

        .modal-close-btn:hover {
          background: rgba(255, 255, 255, 0.35);
          transform: scale(1.06);
        }

        .modal-header-text {
          text-align: center;
          margin-top: 6px;
        }

        .modal-room-title {
          font-size: 26px;
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

        /* ── Top Stat Capsules ── */
        .modal-capsules-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
          margin-top: 18px;
        }

        .stat-capsule {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 24px;
          padding: 16px 12px;
          text-align: center;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .stat-capsule-label {
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.65);
        }

        .stat-capsule-val {
          font-size: 28px;
          font-weight: 800;
          color: #ffffff;
          margin-top: 2px;
        }

        /* ── Central Graduated Thermostat Slider ── */
        .thermostat-vertical-card {
          background: rgba(0, 0, 0, 0.14);
          border-radius: 36px;
          padding: 20px 16px;
          margin: 14px 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          position: relative;
          border: 1px solid rgba(255, 255, 255, 0.1);
          flex: 1;
          justify-content: space-between;
          overflow: hidden;
        }

        .scale-markers {
          width: 100%;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: absolute;
          top: 24px;
          bottom: 120px;
          left: 20px;
          right: 20px;
          pointer-events: none;
          box-sizing: border-box;
          opacity: 0.35;
        }

        .scale-line {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 11px;
          font-weight: 700;
        }

        .scale-line::after {
          content: "";
          flex: 1;
          height: 1px;
          background: rgba(255, 255, 255, 0.35);
        }

        /* White inner box with big readout */
        .thermostat-white-box {
          background: #ffffff;
          border-radius: 30px;
          width: 88%;
          padding: 24px 20px;
          text-align: center;
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25);
          position: relative;
          margin-top: auto;
          color: #000000;
          z-index: 5;
        }

        .slider-pill-bar {
          width: 44px;
          height: 5px;
          background: #d1d5db;
          border-radius: 10px;
          margin: 0 auto 12px auto;
        }

        .target-temp-big {
          font-size: 58px;
          font-weight: 900;
          color: #000000;
          letter-spacing: -2px;
          line-height: 1;
        }

        .target-consigne-label {
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 2px;
          text-transform: uppercase;
          color: #6b7280;
          margin-top: 6px;
        }

        .temp-adjust-buttons {
          display: flex;
          justify-content: center;
          gap: 20px;
          margin-top: 14px;
        }

        .temp-adjust-btn {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: #f3f4f6;
          border: 1px solid #e5e7eb;
          color: #111827;
          font-size: 22px;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .temp-adjust-btn:hover {
          background: #0284c7;
          color: white;
          border-color: #0284c7;
          transform: scale(1.08);
        }

        /* ── Controls Capsule (OFF / AUTO / ON) ── */
        .mode-controls-capsule {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 28px;
          padding: 8px 12px;
          display: flex;
          align-items: center;
          justify-content: space-around;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .mode-btn {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          background: transparent;
          border: none;
          color: rgba(255, 255, 255, 0.7);
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 1px;
          text-transform: uppercase;
          padding: 8px 16px;
          border-radius: 18px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .mode-btn.active {
          background: rgba(255, 255, 255, 0.25);
          color: #ffffff;
        }

        .mode-btn:hover {
          color: #ffffff;
          transform: scale(1.05);
        }

        /* ── Bottom Pills: Puissance & Sécurité ── */
        .modal-bottom-pills {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
          margin-top: 10px;
        }

        .footer-pill {
          background: rgba(0, 0, 0, 0.16);
          border-radius: 22px;
          padding: 12px 16px;
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
          font-size: 20px;
        }

        .footer-pill-text {
          display: flex;
          flex-direction: column;
        }

        .footer-pill-label {
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.65);
        }

        .footer-pill-val {
          font-size: 14px;
          font-weight: 800;
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
                <span class="tado-badge-pill">Enghien</span>
              </h1>
            </div>
          </div>
          <div class="tado-indicators" id="tado-summary-text" style="font-size: 13px; color: #94a3b8; font-weight: 600;">
            Synchronisation en direct
          </div>
        </div>

        <!-- MAIN DASHBOARD GRID -->
        <div class="tado-dashboard-grid" id="tado-grid">
          <!-- Carte 4 quadrants globale -->
          <div class="global-control-tile">
            <button class="quadrant-btn quad-off" id="btn-global-off">
              <span class="q-icon">⏻</span>
              <span>OFF</span>
            </button>
            <button class="quadrant-btn quad-boost" id="btn-global-boost">
              <span class="q-icon">🔥</span>
              <span>BOOST</span>
            </button>
            <button class="quadrant-btn quad-prog" id="btn-global-prog">
              <span class="q-icon">📅</span>
              <span>PROG</span>
            </button>
            <div class="quadrant-btn quad-outdoor">
              <span class="q-icon">🌡️</span>
              <span id="outdoor-temp-display">--° EXTÉRIEUR</span>
            </div>
          </div>

          <!-- Les cartes de pièces seront injectées ici dynamiquement -->
        </div>
      </div>

      <!-- MODALE DETAIL PIECE (Image 2) -->
      <div class="modal-overlay" id="roomModalOverlay">
        <div class="modal-card" id="roomModalCard">
          <button class="modal-close-btn" id="modalCloseBtn">✕</button>

          <div class="modal-header-text">
            <h2 class="modal-room-title" id="modalRoomTitle">Pièce</h2>
            <div class="modal-room-subtitle">
              <span>🌡️</span> CONTRÔLE CLIMAT
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

          <!-- Thermostat slider central -->
          <div class="thermostat-vertical-card" id="modalThermostatCard">
            <div class="scale-markers">
              <div class="scale-line">30°</div>
              <div class="scale-line">25°</div>
              <div class="scale-line">20°</div>
              <div class="scale-line">15°</div>
              <div class="scale-line">5°</div>
            </div>

            <div class="thermostat-white-box">
              <div class="slider-pill-bar"></div>
              <div class="target-temp-big" id="modalTargetBig">19.5</div>
              <div class="target-consigne-label">CONSIGNE •</div>
              <div class="temp-adjust-buttons">
                <button class="temp-adjust-btn" id="btnTempMinus">−</button>
                <button class="temp-adjust-btn" id="btnTempPlus">+</button>
              </div>
            </div>
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
    `;

    this._bindEvents();
  }

  _bindEvents() {
    // Triple-clic sur le titre pour lancer l'Easter Egg SOCRATE RULES
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

    // Boutons de la tuile globale 4 quadrants
    this.querySelector("#btn-global-off")?.addEventListener("click", () => {
      this._callService("domolink_tado", "set_all_off", {});
    });

    this.querySelector("#btn-global-boost")?.addEventListener("click", () => {
      this._callService("domolink_tado", "set_boost", { temperature: 25.0, duration: 1800 });
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

    // Réglage température dans la modale
    this.querySelector("#btnTempMinus")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._adjustModalTemp(-0.5);
    });

    this.querySelector("#btnTempPlus")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._adjustModalTemp(0.5);
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
      const serial = z.devices && z.devices[0] && z.devices[0].serial;
      if (serial) {
        this._callService("domolink_tado", "set_child_lock", {
          device_serial: serial,
          locked: !z.child_locked,
        });
      }
    });
  }

  _adjustModalTemp(delta) {
    if (!this._activeModalZone) return;
    let target = this._activeModalZone.target_num || 20.0;
    target = Math.max(5.0, Math.min(30.0, Math.round((target + delta) * 2) / 2));
    this._activeModalZone.target_num = target;
    this._updateModalView(this._activeModalZone);

    this._callService("climate", "set_temperature", {
      entity_id: this._activeModalZone.entity_id,
      temperature: target,
    });
  }

  _openModal(zone) {
    this._activeModalZone = zone;
    this._activeModalZoneId = zone.zone_id;
    this._updateModalView(zone);
    const overlay = this.querySelector("#roomModalOverlay");
    if (overlay) overlay.classList.add("open");
  }

  _closeModal() {
    this._activeModalZone = null;
    this._activeModalZoneId = null;
    const overlay = this.querySelector("#roomModalOverlay");
    if (overlay) overlay.classList.remove("open");
  }

  _updateModalView(z) {
    if (!z) return;
    const card = this.querySelector("#roomModalCard");
    const colors = this._getTempColor(z.target_num, z.state);

    if (card) {
      card.style.backgroundColor = colors.bg;
    }

    const titleEl = this.querySelector("#modalRoomTitle");
    if (titleEl) titleEl.textContent = z.name;

    const actuelEl = this.querySelector("#modalActuelVal");
    if (actuelEl) actuelEl.textContent = `${z.current_temp}°`;

    const humiditeEl = this.querySelector("#modalHumiditeVal");
    if (humiditeEl) humiditeEl.textContent = z.humidity;

    const targetBigEl = this.querySelector("#modalTargetBig");
    if (targetBigEl) targetBigEl.textContent = z.state === "off" ? "OFF" : z.target_num.toFixed(1);

    // Modes actifs
    const btnOff = this.querySelector("#modalModeOff");
    const btnAuto = this.querySelector("#modalModeAuto");
    const btnHeat = this.querySelector("#modalModeHeat");

    btnOff?.classList.toggle("active", z.state === "off");
    btnAuto?.classList.toggle("active", z.state === "auto" && !z.is_overlay);
    btnHeat?.classList.toggle("active", z.state === "heat" || z.is_overlay);

    // Puissance
    const valPuissance = this.querySelector("#modalValPuissance");
    if (valPuissance) valPuissance.textContent = `${z.heating_power}%`;

    // Sécurité enfant
    const pillSecurite = this.querySelector("#modalPillSecurite");
    const valSecurite = this.querySelector("#modalValSecurite");
    if (pillSecurite && valSecurite) {
      pillSecurite.classList.toggle("active-pill", z.child_locked);
      valSecurite.textContent = z.child_locked ? "VERROUILLÉ" : "DÉVERROUILLÉ";
    }
  }

  _callService(domain, service, data) {
    if (this._hass) {
      this._hass.callService(domain, service, data);
    }
  }

  _updateData() {
    const data = this._extractData();

    // Mettre à jour la température extérieure sur la tuile 4 quadrants
    const outdoorEl = this.querySelector("#outdoor-temp-display");
    if (outdoorEl) outdoorEl.textContent = `${data.outdoor_temp} EXTÉRIEUR`;

    const summaryEl = this.querySelector("#tado-summary-text");
    if (summaryEl) {
      summaryEl.textContent = `${data.zones.length} pièces • ${data.active_count} en chauffe active`;
    }

    // Rafraîchir les cartes de pièces dans la grille
    const grid = this.querySelector("#tado-grid");
    if (!grid) return;

    // Conserver la première tuile globale
    const globalTile = grid.querySelector(".global-control-tile");
    grid.innerHTML = "";
    if (globalTile) grid.appendChild(globalTile);

    for (const z of data.zones) {
      const card = document.createElement("div");
      card.className = "room-card";
      card.dataset.zoneId = z.zone_id;

      const colors = this._getTempColor(z.target_num, z.state);

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
          <div class="room-ring ${z.is_heating ? "active-heat" : ""}" style="border-color: ${colors.accent}; box-shadow: 0 0 14px ${colors.glow};">
            <span class="room-ring-inner-icon">${z.is_heating ? "🔥" : "❄️"}</span>
          </div>
          <div class="room-name">${z.name}</div>
          <div class="target-temp-label">Réglée sur ${z.target_temp}°</div>
        </div>

        <div class="room-card-actions">
          <button class="room-action-btn btn-room-off" title="Éteindre">⏻</button>
          <button class="room-action-btn btn-room-auto" title="Planning automatique">📅</button>
          <button class="room-action-btn btn-room-heat" title="Chauffe manuelle">🔥</button>
        </div>
      `;

      // Clic sur la carte -> ouvrir la modale
      card.addEventListener("click", () => {
        this._openModal(z);
      });

      // Actions rapides sans ouvrir la modale
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

      grid.appendChild(card);
    }

    // Si la modale est actuellement ouverte, rafraîchir son contenu
    if (this._activeModalZoneId) {
      const refreshedZone = data.zones.find((z) => z.zone_id === this._activeModalZoneId);
      if (refreshedZone) {
        this._activeModalZone = refreshedZone;
        this._updateModalView(refreshedZone);
      }
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
        user-select: none;
        -webkit-user-select: none;
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
        #socrate-rules-overlay p.socrate-sub {
          font-size: 0.85rem;
          letter-spacing: 2px;
        }
        #socrate-rules-overlay p.socrate-exit-hint {
          font-size: 0.75rem;
          letter-spacing: 1px;
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
  const TWO_PI = Math.PI * 2;

  const lines = ["Socrate", "Rules"];
  title.innerHTML = "";
  let globalCharIndex = 0;
  lines.forEach((lineText) => {
    const lineDiv = document.createElement("div");
    lineDiv.style.display = "block";
    [...lineText].forEach((char) => {
      const span = document.createElement("span");
      if (char === " ") {
        span.innerHTML = "&nbsp;";
      } else {
        span.textContent = char;
      }
      span.classList.add("socrate-letter");
      span.style.animationDelay = `${globalCharIndex * 0.07}s`;
      lineDiv.appendChild(span);
      globalCharIndex++;
    });
    title.appendChild(lineDiv);
  });

  let particlesArray = [];
  let sparksArray = [];
  let animId = null;
  let isClosing = false;

  let mouse = {
    x: null,
    y: null,
    radius: 150,
    radiusSq: 22500,
  };

  function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resizeCanvas();

  class Particle {
    constructor(x, y, directionX, directionY, size, color) {
      this.x = x;
      this.y = y;
      this.directionX = directionX;
      this.directionY = directionY;
      this.size = size;
      this.color = color;
      this.originalSize = size;
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, TWO_PI, false);
      ctx.fillStyle = this.color;
      ctx.fill();
    }

    update() {
      if (this.x > canvas.width || this.x < 0) this.directionX = -this.directionX;
      if (this.y > canvas.height || this.y < 0) this.directionY = -this.directionY;
      this.x += this.directionX;
      this.y += this.directionY;

      if (mouse.x != null && mouse.y != null) {
        let dx = mouse.x - this.x;
        let dy = mouse.y - this.y;
        let distanceSq = dx * dx + dy * dy;
        if (distanceSq < mouse.radiusSq) {
          let distance = Math.sqrt(distanceSq);
          let forceDirectionX = dx / distance;
          let forceDirectionY = dy / distance;
          let force = (mouse.radius - distance) / mouse.radius;
          this.x -= forceDirectionX * force * 3;
          this.y -= forceDirectionY * force * 3;
          if (this.size < this.originalSize * 3.5) this.size += 0.2;
        } else if (this.size > this.originalSize) {
          this.size -= 0.1;
        }
      } else if (this.size > this.originalSize) {
        this.size -= 0.1;
      }
      this.draw();
    }
  }

  class Spark {
    constructor(x, y) {
      this.x = x;
      this.y = y;
      this.size = Math.random() * 6 + 2;
      this.speedX = (Math.random() - 0.5) * 12;
      this.speedY = (Math.random() - 0.5) * 12;
      const colors = ["#ff007f", "#7f00ff", "#00f0ff", "#ffffff"];
      this.color = colors[Math.floor(Math.random() * colors.length)];
      this.alpha = 1;
      this.decay = Math.random() * 0.015 + 0.01;
    }

    update() {
      this.x += this.speedX;
      this.y += this.speedY;
      this.speedX *= 0.98;
      this.speedY *= 0.98;
      this.alpha -= this.decay;
      if (this.alpha > 0) {
        ctx.save();
        ctx.globalAlpha = this.alpha;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, TWO_PI);
        ctx.fillStyle = this.color;
        ctx.shadowBlur = 15;
        ctx.shadowColor = this.color;
        ctx.fill();
        ctx.restore();
      }
    }
  }

  function initParticles() {
    particlesArray = [];
    let baseParticles = (canvas.width * canvas.height) / 9000;
    let numberOfParticles = Math.min(baseParticles, 250);
    for (let i = 0; i < numberOfParticles; i++) {
      let size = Math.random() * 2 + 0.5;
      let x = Math.random() * (canvas.width - size * 4) + size * 2;
      let y = Math.random() * (canvas.height - size * 4) + size * 2;
      let directionX = Math.random() * 0.4 - 0.2;
      let directionY = Math.random() * 0.4 - 0.2;
      let colorPalette = ["rgba(127, 0, 255, 0.4)", "rgba(0, 240, 255, 0.3)", "rgba(255, 0, 127, 0.3)"];
      let color = colorPalette[Math.floor(Math.random() * colorPalette.length)];
      particlesArray.push(new Particle(x, y, directionX, directionY, size, color));
    }
  }

  function connectParticles() {
    let maxDistance = 120;
    let maxDistanceSq = maxDistance * maxDistance;
    for (let a = 0; a < particlesArray.length; a++) {
      for (let b = a + 1; b < particlesArray.length; b++) {
        let dx = particlesArray[a].x - particlesArray[b].x;
        let dy = particlesArray[a].y - particlesArray[b].y;
        let distanceSq = dx * dx + dy * dy;
        if (distanceSq < maxDistanceSq) {
          let distance = Math.sqrt(distanceSq);
          let opacity = (1 - distance / maxDistance) * 0.15;
          ctx.strokeStyle = `rgba(127, 0, 255, ${opacity})`;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(particlesArray[a].x, particlesArray[a].y);
          ctx.lineTo(particlesArray[b].x, particlesArray[b].y);
          ctx.stroke();
        }
      }
    }
  }

  function animate() {
    ctx.fillStyle = "rgba(3, 0, 8, 0.15)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < particlesArray.length; i++) {
      particlesArray[i].update();
    }

    for (let i = sparksArray.length - 1; i >= 0; i--) {
      sparksArray[i].update();
      if (sparksArray[i].alpha <= 0) {
        sparksArray.splice(i, 1);
      }
    }

    connectParticles();
    animId = requestAnimationFrame(animate);
  }

  function onMouseMove(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  }
  function onMouseOut() {
    mouse.x = null;
    mouse.y = null;
  }
  function onTouchMove(e) {
    if (e.touches && e.touches.length > 0) {
      mouse.x = e.touches[0].clientX;
      mouse.y = e.touches[0].clientY;
    }
  }
  function onTouchEnd() {
    mouse.x = null;
    mouse.y = null;
  }
  function onOverlayClick(e) {
    const x = e.clientX || window.innerWidth / 2;
    const y = e.clientY || window.innerHeight / 2;
    for (let i = 0; i < 30; i++) {
      sparksArray.push(new Spark(x, y));
    }
  }
  function onKeyDown(e) {
    if (e.key === "Escape") {
      cleanup();
    }
  }

  window.addEventListener("resize", resizeCanvas);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseout", onMouseOut);
  window.addEventListener("touchmove", onTouchMove, { passive: true });
  window.addEventListener("touchend", onTouchEnd, { passive: true });
  window.addEventListener("keydown", onKeyDown);
  overlay.addEventListener("click", onOverlayClick);

  let exitClicks = [];
  function handleExitClick(clientX, clientY) {
    if (isClosing) return;
    const now = Date.now();
    exitClicks = exitClicks.filter((t) => now - t < 2000);
    exitClicks.push(now);

    const x = clientX || window.innerWidth / 2;
    const y = clientY || window.innerHeight / 2;
    for (let i = 0; i < 70; i++) {
      sparksArray.push(new Spark(x, y));
    }

    if (exitClicks.length >= 3) {
      isClosing = true;
      exitClicks = [];
      for (let i = 0; i < 150; i++) {
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
  title.addEventListener(
    "touchstart",
    (e) => {
      e.stopPropagation();
      const touch = e.touches && e.touches[0];
      handleExitClick(touch ? touch.clientX : null, touch ? touch.clientY : null);
    },
    { passive: true }
  );

  const exitHint = overlay.querySelector("#socrateExitHint");
  if (exitHint) {
    exitHint.addEventListener("click", (e) => {
      e.stopPropagation();
      handleExitClick(e.clientX, e.clientY);
    });
    exitHint.addEventListener(
      "touchstart",
      (e) => {
        e.stopPropagation();
        const touch = e.touches && e.touches[0];
        handleExitClick(touch ? touch.clientX : null, touch ? touch.clientY : null);
      },
      { passive: true }
    );
  }

  function cleanup() {
    if (animId) {
      cancelAnimationFrame(animId);
      animId = null;
    }
    window.removeEventListener("resize", resizeCanvas);
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseout", onMouseOut);
    window.removeEventListener("touchmove", onTouchMove);
    window.removeEventListener("touchend", onTouchEnd);
    window.removeEventListener("keydown", onKeyDown);
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
  }

  initParticles();
  animate();
}

if (!customElements.get("domolink-tado-panel")) {
  customElements.define("domolink-tado-panel", DomolinkTadoPanel);
}
if (!customElements.get("domolink_tado-panel")) {
  customElements.define("domolink_tado-panel", DomolinkTadoPanel);
}
