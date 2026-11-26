const byId = (id) => document.getElementById(id);
const dashboard = document.body.dataset.page === 'dashboard';
const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const icons = { buffet: '♨', churrasqueira: '◈', balanca: '⚖' };
let state;
let busy = false;
let sequence = 0;
let committed = 0;
let pendingArrival;

function duration(seconds) {
  if (seconds === null) return '—';
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${String(remainder).padStart(2, '0')}s` : `${remainder}s`;
}

function ticket(id) {
  return `#${String(id).padStart(3, '0')}`;
}

function meterValue(station) {
  return station.oldest === null ? 0 : Math.min(100, Math.round((station.oldest / station.limit) * 100));
}

function status(message, error = false) {
  const notice = byId('notice');
  notice.textContent = message;
  notice.hidden = !message;
  notice.classList.toggle('error', error);
}

function renderDashboard(data) {
  const alerts = data.stations.filter((station) => station.over_limit > 0)
    .sort((a, b) => b.extra - a.extra);
  byId('reset').hidden = !data.demo;
  byId('advance').hidden = !data.demo;
  byId('waiting-total').textContent = data.stations.reduce((sum, s) => sum + s.queue.length, 0);
  byId('alert-total').textContent = alerts.length;
  byId('completed-total').textContent = data.stations.reduce((sum, s) => sum + s.completed, 0);
  byId('departure-total').textContent = data.stations.reduce((sum, s) => sum + s.departures, 0);
  byId('stations').innerHTML = data.stations.map((station) => `
    <article class="station ${station.over_limit ? 'is-alert' : ''}">
      <header><span class="station-icon" aria-hidden="true">${icons[station.id]}</span>
        <h3>${station.name}</h3><span class="station-status">${station.over_limit ? 'Acima do limite' : 'Dentro do limite'}</span></header>
      <div class="station-main"><strong>${station.queue.length}</strong><span>em espera</span></div>
      <progress class="meter" max="100" value="${meterValue(station)}" aria-label="Maior espera em relação ao limite de ${station.limit / 60} min">${meterValue(station)}%</progress>
      <dl class="station-stats">
        <div><dt>Maior espera</dt><dd>${duration(station.oldest)}</dd></div>
        <div><dt>Mediana · 15 min</dt><dd>${duration(station.median)}</dd></div>
        <div><dt>Limite</dt><dd>${station.limit / 60} min</dd></div>
      </dl>
      <p class="station-foot">${station.completed ? `${station.completed_over_limit} de ${station.completed} atendimentos acima do limite` : 'Sem atendimentos iniciados nos últimos 15 min'}</p>
    </article>`).join('');
  byId('alerts').innerHTML = alerts.length ? alerts.map((station) => `
    <article class="alert-card"><div class="alert-details">
      <div class="alert-title"><span aria-hidden="true">!</span><h3>${station.name}</h3></div>
      <p><strong>${station.over_limit}</strong> acima de ${station.limit / 60} min · <strong>${duration(station.extra)}</strong> de espera extra acumulada na amostra.</p>
      <p class="action"><strong>Ação sugerida</strong> ${station.action}</p>
    </div><div class="impact"><span>Se 1 cliente desistisse</span><strong>${money.format(data.potential_sale_cents / 100)}</strong><span>em venda potencial por prato de ${data.weight_grams} g. Cenário hipotético.</span></div></article>`).join('') :
    '<p class="quiet">Nenhuma estação acima do limite da amostra.</p>';
  byId('reference').textContent = `Referências da Bovinu’S Augusta · ${data.reference_clients} clientes/dia · ${data.weight_grams} g por cliente durante a semana · ${money.format(data.price_cents / 100)}/kg`;
}

function renderOperation(data) {
  const station = data.stations.find((item) => item.id === byId('station-select').value);
  const queue = byId('queue');
  const focused = document.activeElement?.dataset;
  byId('arrival').disabled = busy;
  byId('queue-count').textContent = `${station.queue.length} ${station.queue.length === 1 ? 'registro' : 'registros'}`;
  queue.innerHTML = station.queue.length ? station.queue.map((item, index) => `
    <li><div><strong>${ticket(item.ticket)}</strong><span class="${item.wait > station.limit ? 'late' : ''}">${duration(item.wait)} em espera${index === 0 ? ' · Mais antigo' : ''}</span></div>
    <div class="queue-actions">
      <button class="secondary" type="button" data-action="start" data-visit="${item.id}" data-ticket="${item.ticket}" ${busy ? 'disabled' : ''}>Iniciar atendimento</button>
      <button class="secondary departure" type="button" data-action="depart" data-visit="${item.id}" data-ticket="${item.ticket}" ${busy ? 'disabled' : ''}>Saiu da fila</button>
    </div></li>`).join('') :
    '<li class="quiet">Fila sem registros ativos.</li>';
  if (focused?.visit) queue.querySelector(`[data-visit="${focused.visit}"][data-action="${focused.action}"]`)?.focus();
}

async function refresh() {
  const current = ++sequence;
  try {
    const response = await fetch('/api/state', { cache: 'no-store' });
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (current < committed) return;
    committed = current;
    state = data;
    byId('mode').textContent = data.demo ? 'Demo · Relógio pausado' : 'Operação · Amostra';
    byId('clock').textContent = data.clock;
    if (dashboard) renderDashboard(data);
    else renderOperation(data);
    if (byId('notice').dataset.offline) {
      delete byId('notice').dataset.offline;
      status('');
    }
  } catch {
    if (current >= committed) {
      byId('mode').textContent = 'Sem conexão';
      byId('notice').dataset.offline = 'true';
      status('Conexão indisponível. O painel tentará atualizar automaticamente.', true);
    }
  }
}

async function update(path, body, onSuccess) {
  if (busy) return;
  busy = true;
  committed = ++sequence;
  const controls = document.querySelectorAll('#arrival, #advance, [data-visit], dialog button[type="submit"]');
  controls.forEach((element) => { element.disabled = true; });
  try {
    const response = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a ação.');
    delete byId('notice').dataset.offline;
    status(onSuccess(result));
  } catch (error) {
    status(error instanceof TypeError ? 'Falha de conexão. Tente novamente.' : error.message, true);
  } finally {
    busy = false;
    controls.forEach((element) => { element.disabled = false; });
    await refresh();
  }
}

if (dashboard) {
  const limits = byId('limits');
  const resetDialog = byId('reset-dialog');
  byId('advance').addEventListener('click', () => update('/api/demo/advance', {}, () => 'Relógio da demo avançado em 1 minuto.'));
  byId('open-limits').addEventListener('click', () => {
    if (!state) return;
    byId('tools').open = false;
    byId('limit-fields').innerHTML = state.stations.map((s) => `
      <label class="limit-field">${s.name}<input name="${s.id}" type="number" value="${s.limit / 60}" min="1" max="30" required></label>`).join('');
    limits.showModal();
  });
  byId('close-limits').addEventListener('click', () => limits.close());
  byId('limit-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const values = Object.fromEntries(Array.from(new FormData(event.target), ([key, value]) => [key, Number(value)]));
    limits.close();
    update('/api/limits', values, () => 'Limites atualizados.');
  });
  byId('reset').addEventListener('click', () => {
    byId('tools').open = false;
    resetDialog.showModal();
  });
  byId('cancel-reset').addEventListener('click', () => resetDialog.close());
  byId('reset-form').addEventListener('submit', (event) => {
    event.preventDefault();
    resetDialog.close();
    update('/api/demo/reset', {}, () => 'Demonstração restaurada para 13h06.');
  });
} else {
  const departureDialog = byId('departure-dialog');
  let departure;
  byId('cancel-departure').addEventListener('click', () => departureDialog.close());
  byId('departure-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const { visit, ticket: number } = departure;
    departureDialog.close();
    update(`/api/visits/${visit}/depart`, {}, () => `Saída registrada. Senha ${ticket(number)}.`);
  });
  byId('station-select').addEventListener('change', () => {
    if (state) renderOperation(state);
  });
  byId('arrival').addEventListener('click', () => {
    const station = byId('station-select').value;
    if (!pendingArrival || pendingArrival.station !== station) {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      const request_id = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      pendingArrival = { station, request_id };
    }
    update('/api/arrivals', pendingArrival, (result) => {
      pendingArrival = undefined;
      return `Chegada registrada. Senha ${ticket(result.ticket)}.`;
    });
  });
  byId('queue').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-visit]');
    if (!button) return;
    if (button.dataset.action === 'depart') {
      departure = { ...button.dataset };
      byId('departure-message').textContent = `Senha ${ticket(departure.ticket)}. Confirme se a pessoa saiu antes de ser atendida.`;
      departureDialog.showModal();
      return;
    }
    update(`/api/visits/${button.dataset.visit}/start`, {}, () => `Atendimento iniciado. Senha ${ticket(button.dataset.ticket)}.`);
  });
}

refresh();
setInterval(() => { if (!busy && !document.hidden) refresh(); }, 5000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && !busy) refresh(); });
