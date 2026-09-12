(function (root) {
  'use strict';
  function create(options) {
    const fetcher = options.fetch;
    const notify = options.notify || (() => {});
    let epoch = 0, sequence = 0, active = null;
    class RequestError extends Error {
      constructor(message, status) { super(message); this.name = 'RequestError'; this.status = status; }
    }
    async function request(url, init = {}) {
      try {
        const headers=new Headers(init.headers||{});
        if(active)headers.set('X-Client-Turn-Id',active.id);
        const response = await fetcher(url, Object.assign({},init,{headers}));
        if (!response.ok) throw new RequestError('Request failed (' + response.status + ').', response.status);
        if (!['GET', 'HEAD'].includes((init.method || 'GET').toUpperCase()) &&
            (response.headers.get('content-type') || '').includes('json')) {
          const body = await response.clone().json();
          if (body.success === false || body.ok === false || body.error)
            throw new RequestError(String(body.error || body.detail || 'The change was not accepted.'), response.status);
        }
        return response;
      } catch (error) {
        notify(error instanceof RequestError ? error.message : 'Connection failed. The outcome is unknown; your draft is kept.');
        throw error;
      }
    }
    function begin(surface) {
      if (active) { notify('The previous turn is still pending. Your draft is kept.'); return null; }
      active = { id: 'client-' + Date.now() + '-' + (++sequence), epoch, surface };
      return active;
    }
    function current(turn) { return active === turn && turn.epoch === epoch; }
    function finish(turn) { if (active === turn) active = null; }
    function invalidate() { epoch++; }
    function ack(input, sent) {
      if (input && input.value === sent) {
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
    function text(value) {
      return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    return { request, begin, current, finish, invalidate, ack, text, RequestError };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { create };
  else {
    root.VintosUI = create({ fetch: root.fetch.bind(root), notify(message) {
      let status = document.getElementById('client-status');
      if (!status) {
        status = document.createElement('div'); status.id = 'client-status'; status.setAttribute('role', 'status');
        status.style.cssText = 'position:fixed;bottom:80px;left:12px;right:12px;padding:12px;background:#262126;color:#fff;z-index:100000;border-radius:8px';
        document.body.appendChild(status);
      }
      status.textContent = message;
      clearTimeout(status.dismiss); status.dismiss = setTimeout(() => status.remove(), 12000);
    }});
  }
})(typeof window === 'undefined' ? globalThis : window);
