/* ============================================================
   Smart Health Navigator – Home Page JS
   Body map: MediFind-style (hover chip + GPS on click → hospitals page)
   ============================================================ */

let allDiseases = [];

document.addEventListener('DOMContentLoaded', () => {
  loadDiseases();
  initBodyMap();
  initIllnessCards();
  initSearchBar();
});

// ── Disease list ──────────────────────────────────────────────
async function loadDiseases() {
  try {
    const res = await fetch('/api/diseases');
    allDiseases = await res.json();
  } catch (e) { allDiseases = []; }
}

// ── Body Map (MediFind pattern) ───────────────────────────────
function initBodyMap() {
  const bodyParts  = document.querySelectorAll('.body-part');
  const hoverChip  = document.getElementById('hoverChip');

  bodyParts.forEach(part => {
    part.addEventListener('mouseenter', () => {
      if (hoverChip) hoverChip.textContent = '👆 ' + part.dataset.name;
      // Highlight all regions with same data-part
      document.querySelectorAll(`[data-part="${part.dataset.part}"]`).forEach(p => {
        p.style.fill        = 'rgba(59,130,246,0.32)';
        p.style.stroke      = '#3b82f6';
        p.style.strokeWidth = '2';
      });
    });

    part.addEventListener('mouseleave', () => {
      if (hoverChip) hoverChip.textContent = '👆 Click any body part';
      document.querySelectorAll(`[data-part="${part.dataset.part}"]`).forEach(p => {
        p.style.fill        = '';
        p.style.stroke      = '';
        p.style.strokeWidth = '';
      });
    });

    part.addEventListener('click', () => {
      if (hoverChip) hoverChip.textContent = '📍 Getting your location…';
      setBodyPartsPointerEvents('none');
      getLocationAndNavigate('body_part', part.dataset.part, part.dataset.name);
    });
  });
}

// ── Illness Cards ─────────────────────────────────────────────
function initIllnessCards() {
  document.querySelectorAll('.illness-card').forEach(card => {
    card.addEventListener('click', () => {
      card.style.transform = 'scale(0.95)';
      setTimeout(() => card.style.transform = '', 180);
      const key   = card.dataset.key;
      const label = card.querySelector('.illness-label')?.textContent || key;
      setBodyPartsPointerEvents('none');
      getLocationAndNavigate('illness', key, label);
    });
  });
}

// ── GPS → navigate ────────────────────────────────────────────
function getLocationAndNavigate(searchType, searchValue, displayName) {
  if (!navigator.geolocation) {
    showManualModal(searchType, searchValue, displayName, 'Your browser does not support GPS.');
    return;
  }

  showLocationOverlay();

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      hideLocationOverlay();
      navigateTo(searchType, searchValue, displayName, pos.coords.latitude, pos.coords.longitude);
    },
    (err) => {
      hideLocationOverlay();
      const reasons = {1:'Location permission denied.', 2:'Location unavailable.', 3:'Location request timed out.'};
      showManualModal(searchType, searchValue, displayName, reasons[err.code] || err.message);
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
  );
}

function navigateTo(searchType, searchValue, displayName, lat, lng) {
  const radius = document.getElementById('radiusSelect')?.value || 5000;
  let url = `/hospitals?lat=${lat}&lng=${lng}&name=${encodeURIComponent(displayName)}&radius=${radius}`;
  if (searchType === 'illness') {
    url += `&illness=${encodeURIComponent(searchValue)}`;
  } else {
    url += `&body_part=${encodeURIComponent(searchValue)}`;
  }
  window.location.href = url;
}

// ── Location overlay ──────────────────────────────────────────
function showLocationOverlay() {
  const el = document.getElementById('locationOverlay');
  if (el) el.style.display = 'flex';
}

function hideLocationOverlay() {
  const el = document.getElementById('locationOverlay');
  if (el) el.style.display = 'none';
  setBodyPartsPointerEvents('');
  const hoverChip = document.getElementById('hoverChip');
  if (hoverChip) hoverChip.textContent = '👆 Click any body part';
}

function setBodyPartsPointerEvents(val) {
  document.querySelectorAll('.body-part').forEach(p => p.style.pointerEvents = val);
  document.querySelectorAll('.illness-card').forEach(c => c.style.pointerEvents = val);
}

// ── Manual location modal (fallback) ─────────────────────────
function showManualModal(searchType, searchValue, displayName, reason) {
  document.getElementById('shnLocationModal')?.remove();

  const modal = document.createElement('div');
  modal.id = 'shnLocationModal';
  modal.style.cssText = `
    position:fixed;inset:0;z-index:9999;
    background:rgba(0,0,0,0.55);backdrop-filter:blur(6px);
    display:flex;align-items:center;justify-content:center;padding:1rem;
  `;

  const sv = encodeURIComponent(searchValue);
  const dn = encodeURIComponent(displayName);

  modal.innerHTML = `
    <div style="background:#fff;border-radius:20px;padding:2rem;max-width:420px;width:100%;
                box-shadow:0 24px 60px rgba(0,0,0,0.25);">
      <div style="font-size:2.2rem;text-align:center;margin-bottom:12px;">📍</div>
      <h3 style="font-size:1.1rem;font-weight:800;text-align:center;margin-bottom:6px;color:#111;">Location Access Needed</h3>
      <p style="color:#6b7280;font-size:0.85rem;text-align:center;margin-bottom:20px;">
        ${reason}<br>Enter your address or area to continue.
      </p>
      <input id="manualAddressInput" placeholder="e.g. Naroda, Ahmedabad or pincode"
        style="width:100%;padding:12px 16px;border:2px solid #e5e7eb;border-radius:12px;
               font-size:0.9rem;outline:none;margin-bottom:12px;box-sizing:border-box;"
        onkeydown="if(event.key==='Enter') shnGeocode('${searchType}','${sv}','${dn}')"/>
      <div id="manualAddrError" style="display:none;color:#ef4444;font-size:0.82rem;margin-bottom:10px;"></div>
      <div style="display:flex;gap:10px;">
        <button onclick="document.getElementById('shnLocationModal').remove();window.setBodyPartsPointerEvents?.('')"
          style="flex:1;padding:12px;background:#f1f5f9;border:none;border-radius:12px;color:#6b7280;cursor:pointer;font-size:0.875rem;font-weight:600;">
          Cancel
        </button>
        <button id="manualAddrBtn" onclick="shnGeocode('${searchType}','${sv}','${dn}')"
          style="flex:2;padding:12px;background:linear-gradient(135deg,#3b82f6,#06b6d4);
                 border:none;border-radius:12px;color:white;cursor:pointer;font-weight:700;font-size:0.875rem;">
          🔍 Find Hospitals
        </button>
      </div>
    </div>`;

  document.body.appendChild(modal);
  setTimeout(() => document.getElementById('manualAddressInput')?.focus(), 100);
}

async function shnGeocode(searchType, svEncoded, dnEncoded) {
  const address = document.getElementById('manualAddressInput')?.value?.trim();
  const errEl   = document.getElementById('manualAddrError');
  const btn     = document.getElementById('manualAddrBtn');
  if (!address) {
    document.getElementById('manualAddressInput').style.borderColor = '#ef4444';
    return;
  }
  if (btn) { btn.textContent = '🔄 Searching…'; btn.disabled = true; }
  if (errEl) errEl.style.display = 'none';

  try {
    const res  = await fetch('/api/geocode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('shnLocationModal')?.remove();
      navigateTo(searchType, decodeURIComponent(svEncoded), decodeURIComponent(dnEncoded), data.lat, data.lng);
    } else {
      throw new Error(data.error || 'Address not found');
    }
  } catch (err) {
    if (btn) { btn.textContent = '🔍 Find Hospitals'; btn.disabled = false; }
    if (errEl) { errEl.textContent = '❌ ' + err.message; errEl.style.display = 'block'; }
    const inp = document.getElementById('manualAddressInput');
    if (inp) inp.style.borderColor = '#ef4444';
  }
}

// ── Search bar ────────────────────────────────────────────────
function initSearchBar() {
  const inp  = document.getElementById('diseaseSearch');
  const sugg = document.getElementById('searchSuggestions');
  if (!inp) return;

  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    if (q.length < 2) { sugg.style.display = 'none'; return; }
    const matches = allDiseases.filter(d => d.label.toLowerCase().includes(q)).slice(0, 8);
    if (!matches.length) { sugg.style.display = 'none'; return; }
    sugg.innerHTML = matches.map(d =>
      `<div class="suggestion-item" onclick="pickSuggestion('${d.key}','${d.label.replace(/'/g,"\\'")}')">
        <span>${d.icon}</span> ${d.label}
      </div>`
    ).join('');
    sugg.style.display = 'block';
  });

  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { triggerSearch(); sugg.style.display = 'none'; }
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.search-input-wrapper')) sugg.style.display = 'none';
  });
}

function pickSuggestion(key, label) {
  document.getElementById('diseaseSearch').value = label;
  document.getElementById('searchSuggestions').style.display = 'none';
  setBodyPartsPointerEvents('none');
  getLocationAndNavigate('illness', key, label);
}

function triggerSearch() {
  const q = (document.getElementById('diseaseSearch')?.value || '').trim().toLowerCase();
  if (!q) return;
  const match   = allDiseases.find(d => d.label.toLowerCase() === q || d.key === q);
  const partial  = match || allDiseases.find(d => d.label.toLowerCase().includes(q));
  const key      = partial?.key || q;
  const label    = partial?.label || q;
  setBodyPartsPointerEvents('none');
  getLocationAndNavigate('illness', key, label);
}

function onRadiusChange() {} // placeholder
