(function () {
  'use strict';
  const core = globalThis.LedgerFlow;
  const get = id => document.getElementById(id);
  const input = get('csv'), sample = input.value;
  const download = get('download');
  let clean = [];

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function render(result) {
    clean = result.clean;
    get('rows').textContent = String(result.rows_read);
    get('ready').textContent = String(clean.length);
    get('total').textContent = core.money(result.totalCents);
    get('output').replaceChildren();
    for (const invoice of clean) {
      const row = element('tr');
      const id = element('td'); id.append(element('strong', invoice.invoice_id)); row.append(id);
      row.append(element('td', invoice.client), element('td', invoice.service));
      row.append(element('td', core.money(core.amountCents(invoice.amount))));
      const status = element('td');
      status.append(element('span', invoice.status, `badge ${invoice.status}`)); row.append(status);
      get('output').append(row);
    }
    if (!clean.length) {
      const row = element('tr'), cell = element('td', 'No valid rows');
      cell.colSpan = 5; row.append(cell); get('output').append(row);
    }
    get('issues').replaceChildren();
    for (const issue of result.issues) {
      const item = element('li');
      const invoice = issue.invoice_id ? ` · Invoice ${issue.invoice_id}` : '';
      item.append(element('strong', `Row ${issue.row_number}${invoice}: `), document.createTextNode(issue.reason));
      if (issue.reason.split('; ').includes('invoice_id is duplicated')) {
        item.append(document.createTextNode(
          ' The earlier valid row is kept. Compare the records before removing a repeated invoice or correcting its details. Change the ID only if it is a different invoice.'
        ));
      }
      get('issues').append(item);
    }
    if (!result.issues.length) get('issues').append(element('li', 'No exceptions found.'));
    get('issue-title').textContent = `${result.issues.length} ${result.issues.length === 1 ? 'row requires' : 'rows require'} review`;
    download.disabled = !clean.length;
  }

  function run() {
    try {
      render(core.validateCSV(input.value));
      get('timestamp').textContent = `Run ${new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    } catch (error) {
      render({rows_read: 0, clean: [], issues: [], totalCents: 0n});
      get('timestamp').textContent = 'Input needs correction';
      get('issue-title').textContent = 'CSV could not be processed';
      get('issues').replaceChildren(element('li', error.message));
    }
  }

  download.addEventListener('click', () => {
    if (!clean.length) return;
    const url = URL.createObjectURL(new Blob([core.exportCSV(clean)], {type: 'text/csv;charset=utf-8'}));
    const link = element('a'); link.href = url; link.download = 'clean-invoices.csv';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  });
  get('run').addEventListener('click', run);
  get('reset').addEventListener('click', () => { input.value = sample; run(); });
  input.addEventListener('input', () => {
    clean = []; download.disabled = true;
    get('timestamp').textContent = 'Input changed — run validation';
  });
  run();
})();
