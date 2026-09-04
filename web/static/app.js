// Aplicación web del Agente de Apuestas Deportivas
// Flujo: Inicio → Regiones/Ligas → Equipos → Recomendación → Próximos

let estado = {
  regionActual: null,
  ligaActual: null,
  ligaNombre: '',
  equipos: [],
  equipoActual: null,
};

// ---- Utilidades ----
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function hideAllViews() {
  $$('.view').forEach(v => v.classList.add('hidden'));
}

function mostrar(vistaId) {
  hideAllViews();
  $(vistaId).classList.remove('hidden');
  window.scrollTo({ top: 0 });
}

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({ detail: 'Error' }));
    throw new Error(data.detail || 'Error en la petición');
  }
  return resp.json();
}

// ---- Navegación ----
function goHome() {
  estado.regionActual = null;
  estado.ligaActual = null;
  mostrar('#view-home');
  $('#nav-inicio').classList.add('active');
  $('#nav-ligas').classList.remove('active');
  $('#nav-proximos').classList.remove('active');
}

async function goRegiones() {
  mostrar('#view-regiones');
  $('#nav-inicio').classList.remove('active');
  $('#nav-ligas').classList.add('active');
  $('#nav-proximos').classList.remove('active');
  await cargarRegiones();
}

async function goEquipos() {
  mostrar('#view-equipos');
  await cargarEquipos();
}

async function goProximos() {
  mostrar('#view-proximos');
  $('#nav-inicio').classList.remove('active');
  $('#nav-ligas').classList.remove('active');
  $('#nav-proximos').classList.add('active');
  await cargarProximosPartidos();
}

// ---- Carga de regiones/ligas ----
async function cargarRegiones() {
  const cont = $('#regions-container');
  cont.innerHTML = '<div class="empty">Cargando ligas...</div>';
  try {
    const regiones = await fetchJson('/api/regiones');
    let html = '';
    for (const region of regiones) {
      html += `<div class="region-block">
        <h3 class="region-title"><i class="fas fa-globe-americas"></i> ${region.label}</h3>
        <div class="league-grid" id="league-${region.key}">
          <div class="empty">Cargando...</div>
        </div>
      </div>`;
      cont.innerHTML = html;
      cargarLigasDeRegion(region.key, `#league-${region.key}`);
    }
    if (!html) cont.innerHTML = '<div class="empty">No hay regiones.</div>';
  } catch (e) {
    cont.innerHTML = `<div class="empty">⚠️ ${e.message}</div>`;
  }
}

async function cargarLigasDeRegion(regionKey, selector) {
  try {
    const ligas = await fetchJson(`/api/ligas/${regionKey}`);
    const grid = $(selector);
    if (grid) {
      grid.innerHTML = ligas.map(l =>
        `<div class="league-card" onclick="elegirLiga('${regionKey}','${l.code}','${l.name}')">
          <h4>${l.name}</h4>
          <span>${l.team_count} equipos</span>
        </div>`
      ).join('');
    }
  } catch (e) {
    console.error('Error ligas', e);
  }
}

function elegirLiga(regionKey, code, name) {
  estado.regionActual = regionKey;
  estado.ligaActual = code;
  estado.ligaNombre = name;
  goEquipos();
}

// ---- Carga de equipos ----
async function cargarEquipos() {
  $('#equipos-title').textContent = estado.ligaNombre;
  const cont = $('#equipos-container');
  const refresh = $('#actualizar-btn');
  refresh.onclick = () => actualizarDatos(estado.ligaActual);
  cont.innerHTML = '<div class="empty">Cargando equipos...</div>';

  try {
    const equipos = await fetchJson(`/api/equipos/${estado.ligaActual}`);
    estado.equipos = equipos;

    let html = `<table class="teams-table">
      <thead><tr>
        <th>Equipo</th><th>Pos</th><th>GF</th><th>GC</th><th>Forma</th><th>Local</th>
      </tr></thead><tbody>`;

    equipos.forEach(t => {
      const pos = t.position || '—';
      const localPct = `${Math.round((t.home_wr||0)*100)}%`;
      html += `<tr onclick="elegirEquipo('${encodeURIComponent(t.name)}')">
        <td class="team-name">${t.name}</td>
        <td>${pos}</td>
        <td>${t.goals_per_game}</td>
        <td>${t.conceded_per_game}</td>
        <td>${t.form || '—'}</td>
        <td>${localPct}</td>
      </tr>`;
    });

    html += '</tbody></table>';
    cont.innerHTML = html;
  } catch (e) {
    cont.innerHTML = `<div class="empty">⚠️ ${e.message}</div>`;
  }
}

async function elegirEquipo(encName) {
  const name = decodeURIComponent(encName);
  estado.equipoActual = name;
  mostrar('#view-recomendacion');
  $('#recom-titulo').textContent = `${name} — ${estado.ligaNombre}`;
  await cargarRecomendaciones(estado.ligaActual, name);
}

async function cargarRecomendaciones(leagueCode, teamName) {
  const statsDiv = $('#stats-detail');
  const recoDiv = $('#recommendations-list');
  const expDiv = $('#expected-detail');
  statsDiv.innerHTML = '<div class="empty">Cargando...</div>';
  recoDiv.innerHTML = '';
  expDiv.innerHTML = '';

  try {
    const data = await fetchJson(`/api/recomendaciones/${leagueCode}/${encodeURIComponent(teamName)}`);

    const fuente = data.stats && data.stats.data_source === 'real'
      ? '<i class="fas fa-check-circle"></i> Datos reales (API-Football)'
      : '<i class="fas fa-info-circle"></i> Datos preseleccionados. Usa "Actualizar" para datos reales.';
    recoDiv.innerHTML = `<div class="notice">${fuente}</div>`;

    const s = data.stats;
    const statsItems = [
      ['Rival de referencia', data.rival || '—'],
      ['Posición', s.position || '—'],
      ['Goles/partido', s.goals_per_game],
      ['Recibidos/partido', s.conceded_per_game],
      ['Éxito local', s.home_wr ? `${Math.round(s.home_wr*100)}%` : '—'],
      ['Forma', s.form || '—'],
      ['Tiros puerta', s.shots],
      ['Córners', s.corners],
      ['Posesión', `${s.possession}%`],
    ];

    statsDiv.innerHTML = statsItems.map(([l, v]) =>
      `<div class="stat-item"><div class="label">${l}</div><div class="value">${v}</div></div>`
    ).join('');

    const eg = data.expected_goals;
    expDiv.innerHTML = `
      <div class="expected-line"><i class="fas fa-futbol"></i> Goles esperados (Poisson): 
        <strong>${eg.home}</strong> - <strong>${eg.away}</strong> 
        (total <strong>${eg.total}</strong>)
      </div>
    `;

    const p = data.probabilities;
    expDiv.innerHTML += `
      <div class="expected-line" style="margin-top:8px;font-size:14px;color:var(--muted)">
        <i class="fas fa-chart-pie"></i> Local ${(p['1']*100).toFixed(0)}% | Empate ${(p['draw']*100).toFixed(0)}% | 
        Visitante ${(p['2']*100).toFixed(0)}% · Over2.5 ${(p['over_2.5']*100).toFixed(0)}% · 
        BTTS ${(p['btts_yes']*100).toFixed(0)}%
      </div>
    `;

    const recs = data.recommendations;
    if (!recs.length) {
      recoDiv.innerHTML += '<div class="empty">No hay recomendaciones suficientes.</div>';
      return;
    }

    const mejor = data.mejor_opcion ? data.mejor_opcion.pick_text : null;

    recoDiv.innerHTML += recs.map(rec => {
      const esLaMejor = mejor && rec.pick_text === mejor;
      const badge = esLaMejor
        ? 'badge-alta'
        : (rec.recommended
            ? (rec.confidence === 'ALTA' ? 'badge-alta' : rec.confidence === 'MEDIA' ? 'badge-media' : 'badge-baja')
            : 'badge-no');
      const check = esLaMejor ? '★' : (rec.recommended ? '✓' : '—');
      let meta = `Probabilidad ${(rec.probability*100).toFixed(0)}% · ${rec.confidence}`;
      if (esLaMejor) meta += ' · <strong>Opción destacada</strong>';
      if (rec.edge !== null && rec.edge !== undefined) meta += ` · Edge ${(rec.edge*100).toFixed(1)}%`;
      return `<div class="recomm-item">
        <div class="recomm-badge ${badge}">${check}</div>
        <div class="recomm-body">
          <div class="title">${rec.pick_text}</div>
          <div class="meta">${meta}</div>
        </div>
      </div>`;
    }).join('');

  } catch (e) {
    statsDiv.innerHTML = `<div class="empty">⚠️ ${e.message}</div>`;
    expDiv.innerHTML = `<div class="notice">${e.message}</div>`;
  }
}

// ---- Próximos partidos ----
async function cargarProximosPartidos() {
  const cont = $('#proximos-ligas-container');
  cont.innerHTML = '<div class="empty"><i class="fas fa-spinner fa-spin"></i> Cargando ligas...</div>';

  try {
    const regiones = await fetchJson('/api/regiones');
    let html = '';

    for (const region of regiones) {
      const ligas = await fetchJson(`/api/ligas/${region.key}`);
      for (const liga of ligas) {
        try {
          const data = await fetchJson(`/api/proximos/${liga.code}`);
          if (data.fixtures && data.fixtures.length > 0) {
            html += `<div class="card">
              <h3 class="card-title"><i class="fas fa-trophy"></i> ${data.league}</h3>
              <div class="fixtures-list">`;
            data.fixtures.forEach(f => {
              const date = new Date(f.date);
              const dateStr = date.toLocaleDateString('es', { weekday: 'short', day: 'numeric', month: 'short' });
              const timeStr = date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
              html += `<div class="fixture-card">
                <div class="fixture-teams">
                  <span>${f.home_team}</span>
                  <span class="fixture-vs">vs</span>
                  <span>${f.away_team}</span>
                </div>
                <div class="fixture-date">${dateStr} ${timeStr}</div>
              </div>`;
            });
            html += '</div></div>';
          }
        } catch (e) {
          // Ignorar errores de ligas sin API
        }
      }
    }

    cont.innerHTML = html || '<div class="empty">No hay partidos próximos disponibles.</div>';
  } catch (e) {
    cont.innerHTML = `<div class="empty">⚠️ ${e.message}</div>`;
  }
}

// ---- Actualizar ----
async function actualizarDatos(leagueCode) {
  const refresh = $('#actualizar-btn');
  refresh.disabled = true;
  refresh.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Actualizando...';
  const statusDiv = $('#actualizar-status');
  if (statusDiv) statusDiv.innerHTML = '';
  try {
    const data = await fetchJson(`/api/actualizar/${leagueCode}`, { method: 'POST' });
    refresh.innerHTML = '<i class="fas fa-check"></i> Listo';
    if (statusDiv) {
      const msg = data.message || 'Completado';
      const extra = data.requests_used ? ` (requests: ${data.requests_used}/${data.daily_limit})` : '';
      statusDiv.innerHTML = `<div class="notice"><i class="fas fa-info-circle"></i> ${msg}${extra}</div>`;
    }
    await cargarEquipos();
  } catch (e) {
    refresh.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Reintentar';
    if (statusDiv) statusDiv.innerHTML = `<div class="notice">${e.message}</div>`;
  } finally {
    setTimeout(() => {
      refresh.disabled = false;
      refresh.innerHTML = '<i class="fas fa-sync"></i> Actualizar datos';
    }, 2500);
  }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  $('#nav-inicio').addEventListener('click', goHome);
  $('#nav-ligas').addEventListener('click', goRegiones);
  $('#nav-proximos').addEventListener('click', goProximos);
});