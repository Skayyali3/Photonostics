document.addEventListener('DOMContentLoaded', () => {
  const devicePanels = document.querySelectorAll('.device-panel[data-device-id]');

  if (devicePanels.length > 0) {
    const POLL_INTERVAL = 5000;

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

      const fields = ['power', 'temp', 'light', 'efficiency', 'health'];
      fields.forEach(field => {
        const el = panel.querySelector(`[data-field="${field}"]`);
        if (!el) return;
        el.textContent = fmt(data[field]);
      });

      const fill = panel.querySelector('.health-bar-fill');
      if (fill) fill.style.width = Math.min(parseFloat(data.health) || 0, 100) + '%';

      const ts = panel.querySelector('.last-seen-time');
      if (ts && data.recorded_at) {
        const d = new Date(data.recorded_at + 'Z');
        ts.textContent = d.toLocaleTimeString();
      }
    }

    function pollDevice(panel) {
      const deviceId = panel.dataset.deviceId;
      fetch(`/api/latest/${encodeURIComponent(deviceId)}`).then(r => r.json()).then(json => {
        if (json.success) updatePanel(panel, json.data);
      }).catch(() => { });
    }

    devicePanels.forEach(panel => {
      pollDevice(panel);
      setInterval(() => pollDevice(panel), POLL_INTERVAL);
    });
  }

  const addForm = document.getElementById('add-device-form');
  if (addForm) {
    const alertBox = document.getElementById('form-alert');
    const spinner = document.getElementById('add-spinner');
    const btnLabel = addForm.querySelector('.btn-label');
    const tbody = document.getElementById('devices-tbody');
    const emptyMsg = document.getElementById('empty-msg');

    function showAlert(msg) {
      alertBox.textContent = msg;
      alertBox.classList.remove('d-none');
    }

    function hideAlert() {
      alertBox.classList.add('d-none');
    }

    function setLoading(on) {
      spinner.classList.toggle('d-none', !on);
      btnLabel.textContent = on ? 'Adding…' : 'Add Device';
      addForm.querySelector('button[type=submit]').disabled = on;
    }

    addForm.addEventListener('submit', e => {
      e.preventDefault();
      hideAlert();

      const formData = new FormData(addForm);
      setLoading(true);

      fetch('/devices', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData,
      })
        .then(async r => {
          const json = await r.json();
          setLoading(false);

          if (!json.success) {
            showAlert(json.error || 'Something went wrong.');
            return;
          }

          const d = json.device;
          if (!tbody) {
            location.reload();
            return;
          }

          if (emptyMsg) emptyMsg.remove();

          const tr = document.createElement('tr');
          tr.dataset.id = d.device_id;
          tr.innerHTML = `
            <td class="fw-semibold">${escHtml(d.nickname)}</td>
            <td><code>${escHtml(d.device_id)}</code></td>
            <td>${d.max_power}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-outline-danger delete-btn" data-id="${escHtml(d.device_id)}">Remove</button>
            </td>`;
          tbody.appendChild(tr);
          bindDelete(tr.querySelector('.delete-btn'));

          addForm.reset();
        })
        .catch(() => {
          setLoading(false);
          showAlert('Network error — please try again.');
        });
    });

    function bindDelete(btn) {
      btn.addEventListener('click', () => {
        const deviceId = btn.dataset.id;
        if (!confirm(`Remove device "${deviceId}"?`)) return;

        fetch(`/devices/${encodeURIComponent(deviceId)}`, { method: 'DELETE' })
          .then(r => r.json())
          .then(json => {
            if (json.success) {
              const row = document.querySelector(`tr[data-id="${deviceId}"]`);
              if (row) row.remove();
              if (tbody && tbody.children.length === 0) {
                const msg = document.createElement('p');
                msg.id = 'empty-msg';
                msg.className = 'text-center text-white mt-4';
                msg.textContent = 'No devices added yet. Register your first device above.';
                tbody.closest('.devices-table-wrap').appendChild(msg);
                tbody.closest('table').remove();
              }
            }
          })
          .catch(() => alert('Could not remove device.'));
      });
    }

    document.querySelectorAll('.delete-btn').forEach(bindDelete);
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  document.querySelectorAll('.renew-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const deviceId = btn.dataset.id;

      btn.disabled = true;
      btn.textContent = 'Sending...';

      fetch(`/devices/${encodeURIComponent(deviceId)}/renew`, {
        method: 'POST'
      })
        .then(r => r.json())
        .then(json => {
          if (json.success) {
            btn.textContent = 'Requested!';
            setTimeout(() => {
              btn.disabled = false;
              btn.textContent = 'Renew Baseline';
            }, 3000);
          } else {
            btn.disabled = false;
            btn.textContent = 'Failed';
            setTimeout(() => {
              btn.disabled = false;
              btn.textContent = 'Renew Baseline';
            }, 2000);
          }
        })
        .catch(() => {
          btn.disabled = false;
          btn.textContent = 'Error';
          setTimeout(() => {
            btn.disabled = false;
            btn.textContent = 'Renew Baseline';
          }, 2000);
        });
    });
  });

});