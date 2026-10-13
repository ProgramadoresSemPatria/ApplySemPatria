/**
 * Opt-in Firebase Analytics (loaded only when /api/meta telemetry.enabled).
 * Crashlytics is not used on web; failures are custom GA4 events + support bundle.
 */
(function () {
  const FIREBASE_VERSION = "10.14.1";
  let analytics = null;
  let enabled = false;

  async function loadFirebase() {
    const appMod = await import(
      `https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-app.js`
    );
    const analyticsMod = await import(
      `https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-analytics.js`
    );
    return { appMod, analyticsMod };
  }

  async function initFromMeta(meta) {
    const tel = meta && meta.telemetry;
    if (!tel || !tel.enabled || !tel.firebase_web) {
      enabled = false;
      return;
    }
    try {
      const { appMod, analyticsMod } = await loadFirebase();
      const app = appMod.initializeApp(tel.firebase_web);
      analytics = analyticsMod.getAnalytics(app);
      enabled = true;
      analyticsMod.logEvent(analytics, "ui_open", {
        install_id: tel.install_id || "",
      });
    } catch (err) {
      console.warn("telemetry init failed", err);
      enabled = false;
    }
  }

  async function logEvent(name, params) {
    if (!enabled || !analytics) {
      return false;
    }
    try {
      const analyticsMod = await import(
        `https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/firebase-analytics.js`
      );
      analyticsMod.logEvent(analytics, name, params || {});
      return true;
    } catch {
      return false;
    }
  }

  async function logResearchFailed(message) {
    const text = String(message || "").slice(0, 240);
    await logEvent("research_failed_ui", { message: text });
    try {
      await fetch("/api/telemetry/client-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "research_failed_ui",
          params: { message: text },
        }),
      });
    } catch {
      /* server may also receive audit events */
    }
  }

  window.jobsearchTelemetry = {
    initFromMeta,
    logEvent,
    logResearchFailed,
    isEnabled: () => enabled,
  };

  window.addEventListener("error", (ev) => {
    if (!enabled) return;
    logEvent("js_error", {
      message: String(ev.message || "").slice(0, 200),
      source: String(ev.filename || "").slice(0, 120),
    });
  });
})();
