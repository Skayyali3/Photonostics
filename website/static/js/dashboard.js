document.addEventListener('DOMContentLoaded', () => {
  const devicePanels = document.querySelectorAll('.device-panel[data-device-id]');

  if (devicePanels.length > 0) {
    const POLL_INTERVAL = 10000;

    function fmt(val, decimals = 1) {
      if (val === null || val === undefined) return '--';
      return Number(val).toFixed(decimals);
    }

    function updatePanel(panel, data) {
      const dot = panel.querySelector('.live-dot');

      if (!data) {
        dot.classList.remove('live');
        return;
      }

      dot.classList.add('live');

      const fields = ['power', 'voltage', 'temp', 'light', 'efficiency', 'health'];
      fields.forEach(field => {
        const el = panel.querySelector(`[data-field="${field}"]`);
        if (!el) return;
        el.textContent = fmt(data[field]);
      });

      const fill = panel.querySelector('.health-bar-fill');
      if (fill) fill.style.width = Math.min(parseFloat(data.health) || 0, 100) + '%';

      const ts = panel.querySelector('.last-seen-time');
      if (ts && data.recorded_at) {
        const d = new Date(data.recorded_at);
        const pad = n => String(n).padStart(2, '0');
        ts.textContent =
          `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ` +
          `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
      }
    }

    function pollDevice(panel) {
      const deviceId = panel.dataset.deviceId;
      fetch(`/api/latest/${encodeURIComponent(deviceId)}`)
        .then(r => r.json())
        .then(json => { if (json.success) updatePanel(panel, json.data); })
        .catch(() => { });
    }

    devicePanels.forEach(panel => {
      pollDevice(panel);
      setInterval(() => pollDevice(panel), POLL_INTERVAL);
    });
  }

  document.querySelectorAll('.renew-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const deviceId = btn.dataset.id;
      btn.disabled = true;
      btn.textContent = 'Sending...';

      fetch(`/devices/${encodeURIComponent(deviceId)}/renew`, {
        method: 'POST',
        headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
      })
        .then(r => r.json())
        .then(json => {
          if (json.success) {
            btn.textContent = 'Requested!';
            setTimeout(() => { btn.disabled = false; btn.textContent = 'Renew Baseline'; }, 3000);
          } else {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.disabled = false; btn.textContent = 'Renew Baseline'; }, 2000);
          }
        })
        .catch(() => {
          btn.textContent = 'Error';
          setTimeout(() => { btn.disabled = false; btn.textContent = 'Renew Baseline'; }, 2000);
        });
    });
  });

  // Push notifications
  const pushBtn = document.getElementById('push-toggle-btn');
  if (!pushBtn) return;

  const pushStatus = document.getElementById('push-status-text');

  function setPushUI(subscribed) {
    if (subscribed) {
      pushBtn.textContent = 'Disable Alerts';
      pushBtn.dataset.active = 'true';
      pushBtn.classList.remove('btn-push-off');
      pushBtn.classList.add('btn-push-on');
      if (pushStatus) pushStatus.textContent = 'Push alerts are enabled for this browser.';
    } else {
      pushBtn.textContent = 'Enable Alerts';
      pushBtn.dataset.active = 'false';
      pushBtn.classList.remove('btn-push-on');
      pushBtn.classList.add('btn-push-off');
      if (pushStatus) pushStatus.textContent = 'You will not receive push alerts.';
    }
    pushBtn.disabled = false;
  }

  function setPushUIError(msg) {
    pushBtn.disabled = false;
    if (pushStatus) pushStatus.textContent = msg;
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  }

  async function initPush() {
    const registrations = await navigator.serviceWorker.getRegistrations();
    for (const r of registrations) {
      if (r.scope && !r.scope.endsWith('/')) await r.unregister();
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      pushBtn.disabled = true;
      if (pushStatus) pushStatus.textContent = 'Push notifications are not supported in this browser.';
      return;
    }

    let reg;
    try {
      reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      await navigator.serviceWorker.ready;
    } catch (err) {
      setPushUIError('Service worker registration failed.');
      console.error('SW Registration Error:', err);
      return;
    }

    let vapidKey;
    try {
      const keyRes = await fetch('/api/push/vapid-public-key');
      const keyJson = await keyRes.json();
      if (!keyJson.success) {
        setPushUIError('Push notifications not configured.');
        return;
      }
      vapidKey = keyJson.key;
    } catch (err) {
      setPushUIError('Could not verify push configuration.');
      console.error('VAPID key fetch error:', err);
      return;
    }

    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      try {
        const res = await fetch(`/api/push/status?endpoint=${encodeURIComponent(existing.endpoint)}`);
        const json = await res.json();
        setPushUI(json.subscribed === true);
      } catch {
        setPushUI(true);
      }
    } else {
      setPushUI(false);
    }

    pushBtn.addEventListener('click', async () => {
      pushBtn.disabled = true;
      const isActive = pushBtn.dataset.active === 'true';

      if (isActive) {
        try {
          const sub = await reg.pushManager.getSubscription();
          if (sub) {
            await fetch('/api/push/subscribe', {
              method: 'DELETE',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ endpoint: sub.endpoint }),
            });
            await sub.unsubscribe();
          }
          setPushUI(false);
        } catch (err) {
          setPushUIError('Could not unsubscribe. Please try again.');
          console.error(err);
          pushBtn.disabled = false;
        }
      } else {
        if (Notification.permission === 'denied') {
          setPushUIError('Notifications blocked. Please allow them in your browser settings.');
          pushBtn.disabled = false;
          return;
        }

        if (Notification.permission !== 'granted') {
          const perm = await Notification.requestPermission();
          if (perm !== 'granted') {
            setPushUIError('Notification permission not granted.');
            pushBtn.disabled = false;
            return;
          }
        }

        let subscription;
        try {
          subscription = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey),
          });
        } catch (err) {
          setPushUIError('Subscription failed. Please try again.');
          pushBtn.disabled = false;
          console.error(err);
          return;
        }

        try {
          const saveRes = await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription.toJSON()),
          });
          const saveJson = await saveRes.json();
          if (!saveJson.success) throw new Error(saveJson.error);
          setPushUI(true);
        } catch (err) {
          setPushUIError('Could not save subscription. Please try again.');
          await subscription.unsubscribe();
          console.error(err);
          pushBtn.disabled = false;
        }
      }
    });
  }

  initPush();
});