// Aplicación web del Agente de Apuestas Deportivas
// Flujo: Inicio → Regiones/Ligas → Equipos → Recomendación → Próximos

let estado = {
  regionActual: null,
  ligaActual: null,
  ligaNombre: '',
  equipos: [],
  equipoActual: null,
  rivalActual: null,
  equipoEsLocal: true,
  bankroll: 1000,
  kellyFrac: 0.25,
  minEdge: 0.02,
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
  $('#nav-mejores').classList.remove('active');
  await cargarProximosPartidos();
}

async function goMejores() {
  mostrar('#view-mejores');
  $('#nav-inicio').classList.remove('active');
  $('#nav-ligas').classList.remove('active');
  $('#nav-proximos').classList.remove('active');
  $('#nav-mejores').classList.add('active');
  // Cargar inputs del estado
  $('#bankroll-input-global').value = estado.bankroll;
  $('#kelly-frac-select-global').value = estado.kellyFrac;
  $('#min-edge-select-global').value = estado.minEdge;
  await cargarMejoresApuestas();
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
  estado.rivalActual = null; // Resetear rival al cambiar de equipo
  estado.equipoEsLocal = true; // Default a local
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

  // Construir URL con parámetros opcionales
  let url = `/api/recomendaciones/${leagueCode}/${encodeURIComponent(teamName)}`;
  const params = new URLSearchParams();
  if (estado.rivalActual) params.set('rival', estado.rivalActual);
  params.set('is_home', estado.equipoEsLocal);
  params.set('bankroll', estado.bankroll);
  params.set('kelly_frac', estado.kellyFrac);
  url += '?' + params.toString();

  try {
    const data = await fetchJson(url);

    const fuente = data.stats && data.stats.data_source === 'real'
      ? '<i class="fas fa-check-circle"></i> Datos reales (API-Football)'
      : '<i class="fas fa-info-circle"></i> Datos preseleccionados. Usa "Actualizar" para datos reales.';
    
    // Actualizar inputs de bankroll/kelly con valores del estado
    $('#bankroll-input').value = estado.bankroll;
    $('#kelly-frac-select').value = estado.kellyFrac;
    $('#min-edge-select').value = estado.minEdge;
    
    // Construir selector de rival
    const rivalesDisponibles = estado.equipos
      .filter(e => e.name !== teamName)
      .map(e => e.name);
    
    let rivalSelectorHtml = `
      <div class="rival-selector">
        <label><i class="fas fa-users"></i> Rival:</label>
        <select id="rival-select" onchange="cambiarRival(this.value)">
          <option value="">-- Seleccionar rival --</option>
          ${rivalesDisponibles.map(r => 
            `<option value="${encodeURIComponent(r)}" ${estado.rivalActual === r ? 'selected' : ''}>${r}</option>`
          ).join('')}
        </select>
      </div>
    `;
    
    // Toggle local/visitante
    let homeAwayToggleHtml = `
      <div class="home-away-toggle">
        <label><i class="fas fa-home"></i> Localidad:</label>
        <div class="toggle-buttons">
          <button class="toggle-btn ${estado.equipoEsLocal ? 'active' : ''}" onclick="cambiarLocalidad(true)">
            <i class="fas fa-home"></i> Local
          </button>
          <button class="toggle-btn ${!estado.equipoEsLocal ? 'active' : ''}" onclick="cambiarLocalidad(false)">
            <i class="fas fa-plane"></i> Visitante
          </button>
        </div>
      </div>
    `;
    
    recoDiv.innerHTML = `<div class="notice">${fuente}</div>${rivalSelectorHtml}${homeAwayToggleHtml}`;

    const s = data.stats;
    const isHome = s.is_home !== false;
    const locationLabel = isHome ? 'Local' : 'Visitante';
    
    const statsItems = [
      ['Rival', data.rival || '—'],
      ['Condición', locationLabel],
      ['Posición', s.position || '—'],
      ['Goles/partido', s.goals_per_game],
      ['Recibidos/partido', s.conceded_per_game],
      ['Éxito local', s.home_wr ? `${Math.round(s.home_wr*100)}%` : '—'],
      ['Forma', s.form || '—'],
      ['Tiros puerta', s.shots],
      ['Córners', s.corners],
      ['Posesión', `${s.possession}%`],
    ];

    // Agregar stats H2H si están disponibles
    let h2hHtml = '';
    if (data.h2h_stats && data.h2h_stats.total_matches > 0) {
      const h2h = data.h2h_stats;
      h2hHtml = `
        <div class="h2h-section">
          <h4><i class="fas fa-history"></i> Historial H2H: ${h2h.team_a} vs ${h2h.team_b}</h4>
          <div class="h2h-stats-grid">
            <div class="h2h-stat"><span class="label">Partidos</span><span class="value">${h2h.total_matches}</span></div>
            <div class="h2h-stat"><span class="label">${h2h.team_a} victorias</span><span class="value">${h2h.team_a_wins} (${h2h.team_a_win_pct}%)</span></div>
            <div class="h2h-stat"><span class="label">Empates</span><span class="value">${h2h.draws} (${h2h.draw_pct}%)</span></div>
            <div class="h2h-stat"><span class="label">${h2h.team_b} victorias</span><span class="value">${h2h.team_b_wins} (${h2h.team_b_win_pct}%)</span></div>
            <div class="h2h-stat"><span class="label">Goles ${h2h.team_a}</span><span class="value">${h2h.team_a_goals} (${h2h.team_a_avg_goals}/part.)</span></div>
            <div class="h2h-stat"><span class="label">Goles ${h2h.team_b}</span><span class="value">${h2h.team_b_goals} (${h2h.team_b_avg_goals}/part.)</span></div>
          </div>
          <div class="h2h-matches">
            <h5>Últimos enfrentamientos:</h5>
            ${data.matches ? data.matches.slice(0, 5).map(m => {
              const date = new Date(m.match_date);
              const dateStr = date.toLocaleDateString('es', { day: 'numeric', month: 'short', year: '2-digit' });
              return `<div class="h2h-match"><span>${m.home_team}</span><strong>${m.home_goals} - ${m.away_goals}</strong><span>${m.away_team}</span><small>${dateStr}</small></div>`;
            }).join('') : '<span>Sin datos</span>'}
          </div>
        </div>
      `;
    }

    statsDiv.innerHTML = statsItems.map(([l, v]) =>
      `<div class="stat-item"><div class="label">${l}</div><div class="value">${v}</div></div>`
    ).join('') + h2hHtml;

    const eg = data.expected_goals;
    // Si es visitante, intercambiar los goles esperados para mostrar
    const displayHome = isHome ? eg.home : eg.away;
    const displayAway = isHome ? eg.away : eg.home;
    expDiv.innerHTML = `
      <div class="expected-line"><i class="fas fa-futbol"></i> Goles esperados (Poisson): 
        <strong>${displayHome}</strong> - <strong>${displayAway}</strong> 
        (total <strong>${eg.total}</strong>)
      </div>
    `;

    const p = data.probabilities;
    // Intercambiar probabilidades si es visitante
    const probHome = isHome ? p['1'] : p['2'];
    const probAway = isHome ? p['2'] : p['1'];
    expDiv.innerHTML += `
      <div class="expected-line" style="margin-top:8px;font-size:14px;color:var(--muted)">
        <i class="fas fa-chart-pie"></i> ${teamName} ${(probHome*100).toFixed(0)}% | Empate ${(p['draw']*100).toFixed(0)}% | 
        Rival ${(probAway*100).toFixed(0)}% · Over2.5 ${(p['over_2.5']*100).toFixed(0)}% · 
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
      // Kelly stake info
      if (rec.kelly_stake_pct !== null && rec.kelly_stake_pct !== undefined && rec.kelly_stake_pct > 0) {
        meta += ` · <strong>Kelly: ${rec.kelly_stake_pct}%</strong>`;
        if (rec.kelly_stake_units !== null && rec.kelly_stake_units !== undefined) {
          meta += ` (${rec.kelly_stake_units.toFixed(2)}€)`;
        }
      }
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

function recargarConKelly() {
  estado.bankroll = parseFloat($('#bankroll-input').value) || 1000;
  estado.kellyFrac = parseFloat($('#kelly-frac-select').value) || 0.25;
  estado.minEdge = parseFloat($('#min-edge-select').value) || 0.02;
  if (estado.equipoActual && estado.ligaActual) {
    cargarRecomendaciones(estado.ligaActual, estado.equipoActual);
  }
}

async function cambiarRival(rivalValue) {
  if (!rivalValue) {
    estado.rivalActual = null;
  } else {
    estado.rivalActual = decodeURIComponent(rivalValue);
  }
  if (estado.equipoActual && estado.ligaActual) {
    await cargarRecomendaciones(estado.ligaActual, estado.equipoActual);
  }
}

async function cambiarLocalidad(esLocal) {
  estado.equipoEsLocal = esLocal;
  if (estado.equipoActual && estado.ligaActual) {
    await cargarRecomendaciones(estado.ligaActual, estado.equipoActual);
  }
}

// ---- Próximos partidos ----
async function cargarProximosPartidos() {
  const cont = $('#proximos-ligas-container');
  cont.innerHTML = '<div class="empty"><i class="fas fa-spinner fa-spin"></i> Cargando partidos...</div>';

  try {
    const daysAhead = parseInt($('#days-ahead-proximos')?.value || '1') || 1;
    const data = await fetchJson(`/api/proximos-todos?days_ahead=${daysAhead}`);

    if (!data.leagues || data.leagues.length === 0) {
      cont.innerHTML = '<div class="empty">No hay partidos próximos disponibles.</div>';
      return;
    }

    let html = '';
    data.leagues.forEach(l => {
      html += `<div class="card">
        <h3 class="card-title"><i class="fas fa-trophy"></i> ${l.league}</h3>
        <div class="fixtures-list">`;
      l.fixtures.forEach(f => {
        const date = new Date(f.date);
        const dateStr = date.toLocaleDateString('es', { weekday: 'short', day: 'numeric', month: 'short' });
        const timeStr = date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
        html += `<div class="fixture-card">
          <div class="fixture-teams">
            ${f.home_logo ? `<img class="fixture-logo" src="${f.home_logo}" alt="" loading="lazy"/>` : ''}
            <span>${f.home_team}</span>
            <span class="fixture-vs">vs</span>
            <span>${f.away_team}</span>
            ${f.away_logo ? `<img class="fixture-logo" src="${f.away_logo}" alt="" loading="lazy"/>` : ''}
          </div>
          <div class="fixture-date">${dateStr} ${timeStr}</div>
        </div>`;
      });
      html += '</div></div>';
    });

    cont.innerHTML = html;

    if (data.total_fixtures > 0) {
      cont.insertAdjacentHTML('afterbegin', `
        <div class="mejores-summary">
          <span><i class="fas fa-futbol"></i> ${data.total_fixtures} partidos próximos</span>
          <span><i class="fas fa-database"></i> ${data.requests_used ?? '—'} requests API</span>
        </div>
      `);
    }
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

// ---- Mejores Apuestas del Día ----
async function cargarMejoresApuestas() {
  const loading = $('#mejores-loading');
  const errorDiv = $('#mejores-error');
  const cont = $('#mejores-container');
  
  loading.classList.remove('hidden');
  errorDiv.classList.add('hidden');
  cont.innerHTML = '';
  
  // Leer parámetros
  estado.bankroll = parseFloat($('#bankroll-input-global').value) || 1000;
  estado.kellyFrac = parseFloat($('#kelly-frac-select-global').value) || 0.25;
  estado.minEdge = parseFloat($('#min-edge-select-global').value) || 0.02;
  const demoMode = $('#demo-mode-global').checked;
  const daysAhead = parseInt($('#days-ahead-select-global').value) || 1;
  
  try {
    const params = new URLSearchParams({
      bankroll: estado.bankroll,
      kelly_frac: estado.kellyFrac,
      min_edge: estado.minEdge,
      max_per_league: 3,
      demo: demoMode,
      days_ahead: daysAhead,
    });
    
    const data = await fetchJson(`/api/mejores-apuestas?${params.toString()}`);
    
    loading.classList.add('hidden');
    
    if (!data.top_bets || data.top_bets.length === 0) {
      cont.innerHTML = '<div class="empty">No se encontraron value bets con los filtros actuales. Prueba bajar el edge mínimo.</div>';
      return;
    }
    
    let html = `<div class="mejores-summary">
      <span><i class="fas fa-chart-line"></i> Analizados: ${data.total_analyzed} apuestas</span>
      <span><i class="fas fa-gem"></i> Top seleccionadas: ${data.top_bets.length}</span>
      <span><i class="fas fa-calendar"></i> ${new Date(data.date).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })}</span>
    </div>`;
    
    html += '<div class="mejores-grid">';
    
    data.top_bets.forEach(bet => {
      const date = new Date(bet.date);
      const dateStr = date.toLocaleDateString('es', { weekday: 'short', day: 'numeric', month: 'short' });
      const timeStr = date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
      const edgeClass = bet.edge_pct >= 5 ? 'edge-alta' : (bet.edge_pct >= 3 ? 'edge-media' : 'edge-baja');
      const confClass = bet.confidence === 'ALTA' ? 'conf-alta' : (bet.confidence === 'MEDIA' ? 'conf-media' : 'conf-baja');
      
      html += `
        <div class="mejor-bet-card">
          <div class="mejor-bet-header">
            <span class="mejor-league">${bet.league}</span>
            <span class="mejor-date">${dateStr} ${timeStr}</span>
          </div>
          <div class="mejor-match">${bet.match}</div>
          <div class="mejor-pick">
            <span class="mejor-market">${bet.market}</span>
            <span class="mejor-choice">${bet.pick}</span>
          </div>
          <div class="mejor-stats">
            <div class="stat"><span class="label">Prob</span><span class="value">${(bet.probability*100).toFixed(0)}%</span></div>
            <div class="stat"><span class="label">Cuota</span><span class="value">${bet.best_odds || bet.odds || '—'}</span></div>
            <div class="stat ${edgeClass}"><span class="label">Edge</span><span class="value">${bet.edge_pct ? bet.edge_pct.toFixed(1) + '%' : '—'}</span></div>
            <div class="stat ${confClass}"><span class="label">Conf</span><span class="value">${bet.confidence}</span></div>
          </div>
          ${bet.best_bookmaker ? `<div class="mejor-bookmaker"><i class="fas fa-building"></i> Mejor cuota: <strong>${bet.best_bookmaker}</strong> (${bet.best_odds})</div>` : ''}
          ${bet.odds_source === 'the_odds_api' ? '<div class="mejor-source"><i class="fas fa-check-circle"></i> Odds reales (The Odds API)</div>' : ''}
          <div class="mejor-kelly">
            <span class="label">Kelly Stake</span>
            <span class="value">${bet.kelly_stake_pct ? bet.kelly_stake_pct.toFixed(2) + '%' : '—'}</span>
            <span class="value-units">${bet.kelly_stake_units ? bet.kelly_stake_units.toFixed(2) + '€' : ''}</span>
          </div>
          <div class="mejor-xg">
            <span class="label">xG</span>
            <span class="value">${bet.expected_goals.home} - ${bet.expected_goals.away} (total ${bet.expected_goals.total})</span>
          </div>
        </div>
      `;
    });
    
    html += '</div>';
    cont.innerHTML = html;
    
  } catch (e) {
    loading.classList.add('hidden');
    errorDiv.classList.remove('hidden');
    errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${e.message}`;
  }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  $('#nav-inicio').addEventListener('click', goHome);
  $('#nav-ligas').addEventListener('click', goRegiones);
  $('#nav-proximos').addEventListener('click', goProximos);
  $('#nav-mejores').addEventListener('click', goMejores);
  $('#nav-bookmakers').addEventListener('click', goBookmakers);
  $('#nav-paper').addEventListener('click', goPaper);
  
  // Cargar ligas para el selector de bookmakers
  cargarLigasBookmakers();
});

// ===================== BOOKMAKERS RANKING =====================
// ... existing bookmakers code ...

// ===================== PAPER TRADING =====================

let paperPortfolioId = null;

async function goPaper() {
  mostrar('#view-paper');
  $('#nav-inicio').classList.remove('active');
  $('#nav-ligas').classList.remove('active');
  $('#nav-proximos').classList.remove('active');
  $('#nav-mejores').classList.remove('active');
  $('#nav-bookmakers').classList.remove('active');
  $('#nav-paper').classList.add('active');
  
  await cargarPaperPortfolio();
  await cargarPaperPicks();
}

async function cargarPaperPortfolio() {
  try {
    const data = await fetchJson('/api/paper/portfolios');
    
    if (data.portfolios && data.portfolios.length > 0) {
      // Usar el primero activo
      const active = data.portfolios.find(p => p.is_active) || data.portfolios[0];
      paperPortfolioId = active.id;
      mostrarPaperPortfolio(active);
      await cargarPaperPerformance(paperPortfolioId);
    } else {
      // Crear portfolio por defecto
      await crearPortfolioPorDefecto();
    }
  } catch (e) {
    console.error('Error cargando portfolio:', e);
  }
}

function mostrarPaperPortfolio(p) {
  const info = $('#paper-portfolio-info');
  const initial = parseFloat(p.initial_bankroll);
  const current = parseFloat(p.current_bankroll);
  const totalReturn = ((current - initial) / initial * 100).toFixed(2);
  const returnClass = totalReturn >= 0 ? 'value' : 'value edge-baja';
  
  info.innerHTML = `
    <div class="stat-item"><div class="label">Portfolio</div><div class="value">${p.name}</div></div>
    <div class="stat-item"><div class="label">Inicial</div><div class="value">${initial.toFixed(2)} ${p.currency}</div></div>
    <div class="stat-item"><div class="label">Actual</div><div class="value">${current.toFixed(2)} ${p.currency}</div></div>
    <div class="stat-item"><div class="label">Retorno Total</div><div class="value ${returnClass}">${totalReturn >= 0 ? '+' : ''}${totalReturn}%</div></div>
    <div class="stat-item"><div class="label">Kelly</div><div class="value">${(p.kelly_fraction*100).toFixed(0)}%</div></div>
    <div class="stat-item"><div class="label">Max Bet</div><div class="value">${(p.max_bet_pct*100).toFixed(0)}%</div></div>
  `;
  
  $('#paper-kelly-select').value = p.kelly_fraction;
  $('#paper-maxbet-select').value = p.max_bet_pct;
  
  $('#paper-perf-card').style.display = 'block';
  $('#paper-period-card').style.display = 'block';
  $('#paper-history-card').style.display = 'block';
}

async function crearPortfolioPorDefecto() {
  try {
    const data = await fetchJson('/api/paper/portfolios', { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Default', initial_bankroll: 1000 })
    });
    if (data.portfolio) {
      paperPortfolioId = data.portfolio.id;
      mostrarPaperPortfolio(data.portfolio);
      await cargarPaperPerformance(paperPortfolioId);
    }
  } catch (e) {
    console.error('Error creando portfolio:', e);
  }
}

async function crearNuevoPortfolio() {
  const name = prompt('Nombre del portfolio:') || 'Portfolio ' + Date.now();
  const bankroll = parseFloat(prompt('Bankroll inicial (€):') || '1000');
  
  try {
    const data = await fetchJson('/api/paper/portfolios', { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, initial_bankroll: bankroll })
    });
    if (data.portfolio) {
      paperPortfolioId = data.portfolio.id;
      mostrarPaperPortfolio(data.portfolio);
      await cargarPaperPerformance(paperPortfolioId);
      await cargarPaperPicks();
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function actualizarPaperSettings() {
  if (!paperPortfolioId) return;
  
  const kelly = parseFloat($('#paper-kelly-select').value);
  const maxbet = parseFloat($('#paper-maxbet-select').value);
  
  try {
    await fetchJson(`/api/paper/portfolios/${paperPortfolioId}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kelly_fraction: kelly, max_bet_pct: maxbet })
    });
    await cargarPaperPortfolio();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function cargarPaperPerformance(portfolioId) {
  try {
    const data = await fetchJson(`/api/paper/portfolios/${portfolioId}/performance?days=30`);
    const perf = data.performance;
    const summary = data.summary;
    
    // Performance summary
    const perfHtml = `
      <div class="stat-item"><div class="label">Picks (30d)</div><div class="value">${perf.total_picks}</div></div>
      <div class="stat-item"><div class="label">ROI (30d)</div><div class="value ${perf.roi_pct >= 0 ? '' : 'edge-baja'}">${perf.roi_pct >= 0 ? '+' : ''}${perf.roi_pct.toFixed(2)}%</div></div>
      <div class="stat-item"><div class="label">Win Rate</div><div class="value">${perf.win_rate.toFixed(1)}%</div></div>
      <div class="stat-item"><div class="label">P&L (30d)</div><div class="value ${perf.total_pnl >= 0 ? '' : 'edge-baja'}">${perf.total_pnl >= 0 ? '+' : ''}${perf.total_pnl.toFixed(2)}€</div></div>
      <div class="stat-item"><div class="label">Sharpe</div><div class="value">${perf.sharpe.toFixed(2)}</div></div>
      <div class="stat-item"><div class="label">Max DD</div><div class="value edge-baja">${perf.max_drawdown.toFixed(2)}€</div></div>
    `;
    $('#paper-perf-summary').innerHTML = perfHtml;
    
    // Period table
    const periods = ['7d', '30d', '90d', '1y', 'all'];
    const periodLabels = ['7 días', '30 días', '90 días', '1 año', 'Todo'];
    let tableHtml = '';
    
    periods.forEach((p, i) => {
      const s = summary[p];
      const roiClass = s.roi >= 0 ? '' : 'edge-baja';
      const pnlClass = s.pnl >= 0 ? '' : 'edge-baja';
      tableHtml += `
        <tr>
          <td><strong>${periodLabels[i]}</strong></td>
          <td>${s.picks}</td>
          <td class="${roiClass}">${s.roi >= 0 ? '+' : ''}${s.roi.toFixed(2)}%</td>
          <td>${s.win_rate.toFixed(1)}%</td>
          <td class="${pnlClass}">${s.pnl >= 0 ? '+' : ''}${s.pnl.toFixed(2)}€</td>
          <td>${s.sharpe.toFixed(2)}</td>
          <td class="edge-baja">${s.max_dd.toFixed(2)}€</td>
        </tr>
      `;
    });
    $('#paper-period-body').innerHTML = tableHtml;
    
    // By market
    if (perf.by_market) {
      let marketHtml = '<h4 style="margin:16px 0 8px;color:var(--accent)"><i class="fas fa-list"></i> Por Mercado</h4>';
      marketHtml += '<div class="stats-grid">';
      for (const [market, stats] of Object.entries(perf.by_market)) {
        const roiClass = stats.roi >= 0 ? '' : 'edge-baja';
        marketHtml += `
          <div class="stat-item">
            <div class="label">${market.toUpperCase()}</div>
            <div class="value">${stats.picks} picks | WR: ${stats.win_rate}% | ROI: <span class="${roiClass}">${stats.roi >= 0 ? '+' : ''}${stats.roi}%</span></div>
          </div>
        `;
      }
      marketHtml += '</div>';
      $('#paper-perf-summary').innerHTML += marketHtml;
    }
    
    // By league
    if (perf.by_league) {
      let leagueHtml = '<h4 style="margin:16px 0 8px;color:var(--accent)"><i class="fas fa-trophy"></i> Por Liga</h4>';
      leagueHtml += '<div class="stats-grid">';
      for (const [league, stats] of Object.entries(perf.by_league)) {
        const roiClass = stats.roi >= 0 ? '' : 'edge-baja';
        leagueHtml += `
          <div class="stat-item">
            <div class="label">${league}</div>
            <div class="value">${stats.picks} picks | WR: ${stats.win_rate}% | ROI: <span class="${roiClass}">${stats.roi >= 0 ? '+' : ''}${stats.roi}%</span></div>
          </div>
        `;
      }
      leagueHtml += '</div>';
      $('#paper-perf-summary').innerHTML += leagueHtml;
    }
    
  } catch (e) {
    console.error('Error cargando performance:', e);
  }
}

async function cargarPaperPicks() {
  if (!paperPortfolioId) return;
  
  const status = $('#paper-status-filter').value || null;
  
  try {
    const data = await fetchJson(`/api/paper/portfolios/${paperPortfolioId}/picks?status=${status || ''}&limit=100`);
    
    const body = $('#paper-picks-body');
    if (!data.picks || data.picks.length === 0) {
      body.innerHTML = '<tr><td colspan="10" class="empty">No hay picks</td></tr>';
      return;
    }
    
    body.innerHTML = data.picks.map(pick => {
      const date = new Date(pick.placed_at);
      const dateStr = date.toLocaleDateString('es', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
      
      let statusClass = '';
      let statusText = pick.status;
      if (pick.status === 'pending') { statusClass = 'status-pending'; statusText = '⏳ Pendiente'; }
      else if (pick.status === 'won') { statusClass = 'status-won'; statusText = '✅ Ganado'; }
      else if (pick.status === 'lost') { statusClass = 'status-lost'; statusText = '❌ Perdido'; }
      else if (pick.status === 'void') { statusClass = 'status-void'; statusText = '⚪ Anulado'; }
      else if (pick.status === 'settled') { statusClass = 'status-settled'; statusText = pick.result === 'win' ? '✅ Ganado' : pick.result === 'loss' ? '❌ Perdido' : '⚪ Push'; }
      else if (pick.status === 'cancelled') { statusClass = 'status-void'; statusText = '🚫 Cancelado'; }
      
      const pnlClass = pick.pnl !== null && pick.pnl !== undefined 
        ? (pick.pnl >= 0 ? 'value' : 'value edge-baja') 
        : '';
      const pnlText = pick.pnl !== null && pick.pnl !== undefined 
        ? (pick.pnl >= 0 ? '+' : '') + pick.pnl.toFixed(2) + '€' 
        : '—';
      
      let actionsHtml = '';
      if (pick.status === 'pending') {
        actionsHtml = `<button class="btn btn-secondary btn-sm" onclick="liquidarPaperPick(${pick.id})" style="padding:4px 8px;font-size:11px;margin-right:4px;"><i class="fas fa-check"></i> Liquidar</button>
          <button class="btn btn-ghost btn-sm" onclick="cancelarPaperPick(${pick.id})" style="padding:4px 8px;font-size:11px;"><i class="fas fa-times"></i> Cancelar</button>`;
      } else {
        actionsHtml = '—';
      }
      
      return `
        <tr>
          <td>${dateStr}</td>
          <td>${pick.home_team} vs ${pick.away_team}</td>
          <td>${pick.league}</td>
          <td><span class="mejor-market">${pick.market}</span></td>
          <td><strong>${pick.choice}</strong></td>
          <td>${parseFloat(pick.odds).toFixed(2)}</td>
          <td>${parseFloat(pick.stake_units).toFixed(2)}€</td>
          <td><span class="${statusClass}">${statusText}</span></td>
          <td class="${pnlClass}">${pnlText}</td>
          <td>${actionsHtml}</td>
        </tr>
      `;
    }).join('');
    
  } catch (e) {
    console.error('Error cargando picks:', e);
  }
}

async function colocarPaperPick() {
  if (!paperPortfolioId) {
    alert('No hay portfolio activo');
    return;
  }
  
  const match = $('#paper-match').value.trim();
  const league = $('#paper-league').value;
  const kickoff = $('#paper-kickoff').value;
  const market = $('#paper-market').value;
  const choice = $('#paper-choice').value.trim();
  const odds = parseFloat($('#paper-odds').value);
  const prob = parseFloat($('#paper-prob').value) / 100;
  const stake = $('#paper-stake').value ? parseFloat($('#paper-stake').value) : null;
  
  if (!match || !league || !kickoff || !market || !choice || !odds || !prob) {
    alert('Completa todos los campos obligatorios');
    return;
  }
  
  // Parsear equipos del match
  const teams = match.split(' vs ').map(t => t.trim());
  if (teams.length !== 2) {
    alert('Formato partido: "Equipo Local vs Equipo Visitante"');
    return;
  }
  const home_team = teams[0];
  const away_team = teams[1];
  
  const match_id = `${home_team}_vs_${away_team}_${league}_${kickoff.split('T')[0]}`;
  
  try {
    let result;
    if (stake) {
      result = await fetchJson(`/api/paper/portfolios/${paperPortfolioId}/picks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          match_id, home_team, away_team, league, kickoff,
          market, choice, odds, probability: prob, stake_units: stake
        })
      });
    } else {
      result = await fetchJson(`/api/paper/portfolios/${paperPortfolioId}/picks/from-recommendation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          league_code: league, home_team, away_team,
          market, choice, odds, probability: prob
        })
      });
    }
    
    alert(`✅ Pick colocado: ${result.stake_units.toFixed(2)}€ (Kelly: ${result.kelly_stake_pct.toFixed(2)}%)`);
    
    // Limpiar formulario
    $('#paper-match').value = '';
    $('#paper-choice').value = '';
    $('#paper-odds').value = '';
    $('#paper-prob').value = '';
    $('#paper-stake').value = '';
    $('#paper-kickoff').value = '';
    
    await cargarPaperPortfolio();
    await cargarPaperPicks();
    
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function liquidarPaperPick(pickId) {
  const score = prompt('Resultado final (ej: 2-1):');
  if (!score) return;
  
  try {
    const result = await fetchJson(`/api/paper/picks/${pickId}/settle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actual_score: score })
    });
    
    alert(`${result.result.toUpperCase()} | P&L: ${result.pnl >= 0 ? '+' : ''}${result.pnl.toFixed(2)}€ (ROI: ${result.roi_pct.toFixed(2)}%)`);
    
    await cargarPaperPortfolio();
    await cargarPaperPicks();
    
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function cancelarPaperPick(pickId) {
  if (!confirm('¿Cancelar este pick? Se devolverá el stake al bankroll.')) return;
  
  try {
    await fetchJson(`/api/paper/picks/${pickId}/cancel`, { method: 'POST' });
    alert('Pick cancelado, stake devuelto');
    await cargarPaperPortfolio();
    await cargarPaperPicks();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ===================== BOOKMAKERS RANKING =====================

async function goBookmakers() {
  mostrar('#view-bookmakers');
  $('#nav-inicio').classList.remove('active');
  $('#nav-ligas').classList.remove('active');
  $('#nav-proximos').classList.remove('active');
  $('#nav-mejores').classList.remove('active');
  $('#nav-bookmakers').classList.add('active');
  await cargarBookmakersRanking();
}

async function cargarLigasBookmakers() {
  try {
    const data = await fetchJson('/api/bookmakers/leagues');
    const select = $('#bm-league-select');
    if (select && data.leagues) {
      data.leagues.forEach(l => {
        const opt = document.createElement('option');
        opt.value = l.league;
        opt.textContent = `${l.league} (${l.bookmakers_count} books, ${l.total_snapshots} snaps)`;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error('Error cargando ligas bookmakers:', e);
  }
}

async function cargarBookmakersRanking() {
  const loading = $('#bm-loading');
  const errorDiv = $('#bm-error');
  const tableCard = $('#bm-table-card');
  const summaryCard = $('#bm-summary-card');
  const body = $('#bm-ranking-body');
  const summary = $('#bm-summary');
  
  loading.classList.remove('hidden');
  errorDiv.classList.add('hidden');
  tableCard.style.display = 'none';
  summaryCard.style.display = 'none';
  body.innerHTML = '';
  
  try {
    const league = $('#bm-league-select').value || null;
    const periodDays = parseInt($('#bm-period-select').value) || 30;
    const minMarkets = parseInt($('#bm-min-markets-select').value) || 50;
    const top = 25;
    
    const params = new URLSearchParams({
      period_days: periodDays,
      top: top,
      min_markets: minMarkets,
    });
    if (league) params.set('league', league);
    
    const data = await fetchJson(`/api/bookmakers/ranking?${params.toString()}`);
    
    loading.classList.add('hidden');
    
    if (!data.ranking || data.ranking.length === 0) {
      body.innerHTML = '<tr><td colspan="11" class="empty">No hay datos suficientes. Necesitas polling de odds primero.</td></tr>';
      tableCard.style.display = 'block';
      return;
    }
    
    // Resumen
    const avgSharp = (data.ranking.reduce((s, b) => s + b.sharp_factor, 0) / data.ranking.length).toFixed(1);
    const avgClv = (data.ranking.reduce((s, b) => s + b.clv_beat_rate, 0) / data.ranking.length).toFixed(1);
    const avgAcc = (data.ranking.reduce((s, b) => s + b.accuracy_score, 0) / data.ranking.length).toFixed(2);
    const avgCons = (data.ranking.reduce((s, b) => s + b.consistency_score, 0) / data.ranking.length).toFixed(2);
    
    summary.innerHTML = `
      <div class="stat-item"><div class="label">Bookmakers analizados</div><div class="value">${data.ranking.length}</div></div>
      <div class="stat-item"><div class="label">Sharp Factor promedio</div><div class="value">${avgSharp}</div></div>
      <div class="stat-item"><div class="label">CLV Beat Rate promedio</div><div class="value">${avgClv}%</div></div>
      <div class="stat-item"><div class="label">Accuracy promedio</div><div class="value">${avgAcc}</div></div>
      <div class="stat-item"><div class="label">Consistency promedio</div><div class="value">${avgCons}</div></div>
      <div class="stat-item"><div class="label">Período</div><div class="value">${periodDays} días</div></div>
    `;
    summaryCard.style.display = 'block';
    
    // Tabla
    body.innerHTML = data.ranking.map(bm => {
      const sharpClass = bm.sharp_factor >= 80 ? 'sharp-elite' : 
                         bm.sharp_factor >= 65 ? 'sharp-high' : 
                         bm.sharp_factor >= 50 ? 'sharp-medium' : 'sharp-low';
      const clvClass = bm.clv_beat_rate >= 60 ? 'clv-high' : 
                       bm.clv_beat_rate >= 40 ? 'clv-medium' : 'clv-low';
      const badgesHtml = bm.badges && bm.badges.length 
        ? bm.badges.map(b => `<span class="bm-badge">${b}</span>`).join(' ')
        : '—';
      
      return `
        <tr>
          <td class="rank">${bm.rank}</td>
          <td class="bookmaker-name"><strong>${bm.bookmaker}</strong></td>
          <td class="league">${bm.league}</td>
          <td class="sharp-factor ${sharpClass}">${bm.sharp_factor.toFixed(1)}</td>
          <td class="clv-score">${(bm.clv_score * 100).toFixed(0)}%</td>
          <td class="beat-rate ${clvClass}">${bm.clv_beat_rate.toFixed(1)}%</td>
          <td class="avg-clv">${bm.avg_clv_pct >= 0 ? '+' : ''}${bm.avg_clv_pct.toFixed(2)}%</td>
          <td class="accuracy">${(bm.accuracy_score * 100).toFixed(0)}%</td>
          <td class="consistency">${(bm.consistency_score * 100).toFixed(0)}%</td>
          <td class="markets">${bm.total_markets}</td>
          <td class="badges">${badgesHtml}</td>
        </tr>
      `;
    }).join('');
    
    tableCard.style.display = 'block';
    
  } catch (e) {
    loading.classList.add('hidden');
    errorDiv.classList.remove('hidden');
    errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${e.message}`;
  }
}