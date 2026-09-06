const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../static/mobile.js'), 'utf8');

async function boot(query, { online = true, status = 200, cached = null } = {}) {
  const requests = [], rendered = [], nodes = new Map();
  const ticket = { id: 42, status: 'COMPLETED', archived_at: '2026-09-01T10:00:00Z' };
  const storage = new Map(cached ? [[42, cached]] : []);
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, { textContent: '', classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {} });
    return nodes.get(id);
  }
  const context = {
    window: { MOBILE_BOOTSTRAP: { userId: 3, username: 'master1' }, addEventListener() {} },
    navigator: { onLine: online }, location: { search: query },
    localStorage: { getItem() { return null; }, setItem() {} },
    document: { getElementById: node, addEventListener() {} },
    URLSearchParams, Headers, setInterval() {}, console,
    fetch: async (url, options) => {
      requests.push({ url, owner: options.headers.get('X-Mobile-User') });
      return { status, ok: status === 200, json: async () => ticket };
    },
    storage, rendered,
  };
  // Stub persistence/UI collaborators, but execute the actual init, openTicket and mobileFetch.
  const setup = `
    verifyIdentity=async()=>true;
    setActiveTab=()=>{};
    refreshTickets=async()=>{state.tickets=[{id:1,status:'ASSIGNED'}];};
    updateSyncIndicators=async()=>{};
    syncAll=async()=>{};
    listOutboxEvents=async()=>[];
    loadTicketCache=async(id)=>storage.get(id)||null;
    saveTicketCache=async(ticket)=>storage.set(ticket.id,ticket);
    withStore=async(_name,_mode,fn)=>fn({delete:id=>storage.delete(id)});
    renderDetail=ticket=>rendered.push(ticket);
  `;
  vm.runInNewContext(source.replace('init().catch', `${setup}\nglobalThis.ready=init().catch`), context);
  await context.ready;
  return { requests, rendered, storage, nodes };
}

test('completed/archived deep link outside active list fetches the requested ticket with owner guard', async () => {
  const result = await boot('?ticket=42');
  assert.deepEqual(result.requests, [{ url: '/api/tickets/42', owner: '3' }]);
  assert.equal(result.rendered[0].id, 42);
  assert.equal(result.rendered[0].status, 'COMPLETED');
});

test('forbidden and missing deep links do not fall back to stale cached details', async () => {
  for (const status of [403, 404]) {
    const result = await boot('?ticket=42', { status, cached: { id: 42, description: 'stale' } });
    assert.deepEqual(result.rendered, [null]);
    assert.equal(result.storage.has(42), false);
    assert.match(result.nodes.get('ticket-detail').textContent, /недоступна/);
  }
});

test('offline closed ticket opens from personal cache, invalid ids do not request records', async () => {
  const cached = { id: 42, status: 'COMPLETED' };
  const result = await boot('?ticket=42', { online: false, cached });
  assert.deepEqual(result.requests, []);
  assert.equal(result.rendered[0], cached);
  for (const query of ['', '?ticket=-1', '?ticket=1.5', '?ticket=abc', '?ticket=9007199254740992']) {
    const invalid = await boot(query);
    assert.deepEqual(invalid.requests, []);
    assert.deepEqual(invalid.rendered, []);
  }
});
