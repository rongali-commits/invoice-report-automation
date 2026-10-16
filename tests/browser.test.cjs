const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const core = require('../site/ledgerflow.js');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/contract.json'), 'utf8'));

for (const fixture of cases) {
  test(`shared CSV contract: ${fixture.name}`, () => {
    if (fixture.error) {
      assert.throws(() => core.validateCSV(fixture.csv), new RegExp(fixture.error));
      return;
    }
    const result = core.validateCSV(fixture.csv);
    assert.deepEqual(result.clean, fixture.clean);
    assert.deepEqual(result.issues, fixture.issues);
    assert.equal(result.rows_read, fixture.clean.length + fixture.issues.length);
    assert.equal(result.clean_total_decimal, fixture.total);
    const exported = core.parseCSV(core.exportCSV(result.clean));
    assert.deepEqual(exported.shift(), core.fields);
    assert.deepEqual(exported, fixture.clean.map(row => core.fields.map(name => {
      const value = row[name];
      return /^[=+\-@]/.test(value) ? `'${value}` : value;
    })));
  });
}

// Minimal DOM with innerHTML forbidden: rendering must use text nodes. This
// executes the actual page controller, including reset, errors and downloads.
function page() {
  class Node {
    constructor(tag) { this.tagName = tag; this.children = []; this.events = {}; this.value = ''; }
    set textContent(value) { this.text = String(value); this.children = []; }
    get textContent() { return (this.text || '') + this.children.map(node => node.textContent).join(''); }
    set innerHTML(value) { throw new Error(`Unsafe HTML rendering: ${value}`); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.text = ''; this.children = nodes; }
    addEventListener(name, callback) { this.events[name] = callback; }
    click() { if (this.events.click) this.events.click(); }
    remove() {}
  }
  const nodes = new Map();
  for (const id of ['csv', 'download', 'rows', 'ready', 'total', 'output', 'issues', 'issue-title', 'timestamp', 'run', 'reset']) {
    nodes.set(id, new Node(id));
  }
  const html = fs.readFileSync(path.join(__dirname, '../site/index.html'), 'utf8');
  nodes.get('csv').value = html.match(/<textarea[^>]*>([\s\S]*?)<\/textarea>/)[1];
  const blobs = [];
  const context = {
    LedgerFlow: core, Blob, Date,
    URL: {createObjectURL(blob) { blobs.push(blob); return 'blob:test'; }, revokeObjectURL() {}},
    setTimeout(callback) { callback(); },
    document: {
      getElementById(id) { return nodes.get(id); },
      createElement(tag) { return new Node(tag); },
      createTextNode(text) { const node = new Node('#text'); node.textContent = text; return node; },
      body: new Node('body'),
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../site/app.js'), 'utf8'), context);
  return {nodes, blobs};
}

test('page renders literal input, downloads normalized safe CSV and restores sample', async () => {
  const {nodes, blobs} = page();
  assert.equal(nodes.get('rows').textContent, '6');
  assert.equal(nodes.get('ready').textContent, '4');
  assert.equal(nodes.get('total').textContent, '$2,290.00');
  const fixture = cases.find(value => value.name === 'safe_text_and_formula_export');
  nodes.get('csv').value = fixture.csv;
  nodes.get('run').click();
  assert.match(nodes.get('output').textContent, /<img src=x onerror=alert\(1\)>/);
  nodes.get('download').click();
  const rows = core.parseCSV(await blobs[0].text());
  assert.equal(rows[1][4], '2.00');
  assert.equal(rows[1][3], '\'=HYPERLINK("https://example.com")');
  assert.equal(rows[2][0], "'+ID");
  nodes.get('reset').click();
  assert.equal(nodes.get('ready').textContent, '4');
  assert.equal(nodes.get('total').textContent, '$2,290.00');
});

test('fatal input errors clear old rows, totals and downloadable records', () => {
  const {nodes, blobs} = page();
  for (const fixture of cases.filter(value => value.error)) {
    nodes.get('csv').value = fixture.csv;
    nodes.get('run').click();
    assert.equal(nodes.get('rows').textContent, '0');
    assert.equal(nodes.get('ready').textContent, '0');
    assert.equal(nodes.get('total').textContent, '$0.00');
    assert.equal(nodes.get('output').textContent, 'No valid rows');
    assert.equal(nodes.get('download').disabled, true);
    assert.match(nodes.get('issues').textContent, new RegExp(fixture.error));
    nodes.get('download').click();
    assert.equal(blobs.length, 0);
    nodes.get('reset').click();
  }
});

test('editing invalidates the old download until validation runs again', () => {
  const {nodes, blobs} = page();
  nodes.get('csv').value = 'unfinished edit';
  nodes.get('csv').events.input();
  nodes.get('download').click();
  assert.equal(nodes.get('download').disabled, true);
  assert.equal(blobs.length, 0);
  assert.match(nodes.get('timestamp').textContent, /Input changed/);
});

test('exact currency display does not convert large totals to Number', () => {
  assert.equal(core.money(9999999999999900n), '$99,999,999,999,999.00');
});

test('duplicate guidance identifies the retained invoice and preserves the clean export', async () => {
  const {nodes, blobs} = page();
  const csv = [
    'invoice_id,client,email,service,amount,status',
    'TRY-100,"Example, Limited",BILLING@EXAMPLE.COM,"Monthly reporting",1.005,PAID',
    'TRY-101,Example Studio,ops@example.com,Reporting,2.675,pending',
    'TRY-101,Example Studio,ops@example.com,Duplicate invoice,10,paid',
  ].join('\n');
  nodes.get('csv').value = csv;
  nodes.get('run').click();
  assert.equal(nodes.get('rows').textContent, '3');
  assert.equal(nodes.get('ready').textContent, '2');
  assert.equal(nodes.get('total').textContent, '$3.68');
  assert.equal(nodes.get('issue-title').textContent, '1 row requires review');
  const warning = nodes.get('issues').textContent;
  assert.match(warning, /Row 4.*TRY-101.*invoice_id is duplicated/s);
  assert.match(warning, /compare/i);
  assert.match(warning, /earlier valid row.*(?:kept|retained|remains)/i);
  assert.match(warning, /correct.*ID.*different invoice/i);
  nodes.get('download').click();
  assert.deepEqual(core.parseCSV(await blobs[0].text()), [
    core.fields,
    ['TRY-100', 'Example, Limited', 'billing@example.com', 'Monthly reporting', '1.00', 'paid'],
    ['TRY-101', 'Example Studio', 'ops@example.com', 'Reporting', '2.68', 'pending'],
  ]);

  // A distinct invoice can have its ID corrected, without replacing the retained
  // pending invoice or changing its rounded amount.
  nodes.get('csv').value = csv.replace(
    'TRY-101,Example Studio,ops@example.com,Duplicate',
    'TRY-102,Example Studio,ops@example.com,Duplicate',
  );
  nodes.get('csv').events.input();
  assert.equal(nodes.get('download').disabled, true);
  nodes.get('run').click();
  assert.equal(nodes.get('ready').textContent, '3');
  assert.equal(nodes.get('total').textContent, '$13.68');
  assert.equal(nodes.get('issue-title').textContent, '0 rows require review');
  assert.equal(nodes.get('issues').textContent, 'No exceptions found.');
  nodes.get('download').click();
  const corrected = core.parseCSV(await blobs[1].text());
  assert.deepEqual(corrected[2], ['TRY-101', 'Example Studio', 'ops@example.com', 'Reporting', '2.68', 'pending']);
  assert.deepEqual(corrected[3], ['TRY-102', 'Example Studio', 'ops@example.com', 'Duplicate invoice', '10.00', 'paid']);
});

test('duplicate advice follows accepted case-insensitive IDs and preserves other errors', async () => {
  const {nodes, blobs} = page();
  nodes.get('csv').value = [
    'invoice_id,client,email,service,amount,status',
    ' Repeat ,Example,invalid,Work,999,paid',
    'repeat,Example,ops@example.com,Work,2.675,pending',
    ' REPEAT ,Example,invalid,Work,10,paid',
    'OTHER,Example,ops@example.com,Work,0,paid',
  ].join('\n');
  nodes.get('run').click();
  assert.equal(nodes.get('ready').textContent, '1');
  assert.equal(nodes.get('total').textContent, '$2.68');
  assert.equal(nodes.get('issue-title').textContent, '3 rows require review');
  const warnings = nodes.get('issues').children.map(node => node.textContent);
  assert.equal(warnings.length, 3);
  assert.match(warnings[0], /Row 2.*Repeat.*email is missing or invalid/s);
  assert.doesNotMatch(warnings[0], /earlier valid row|different invoice/i);
  assert.match(warnings[1], /Row 4.*REPEAT.*email is missing or invalid; invoice_id is duplicated/s);
  assert.match(warnings[1], /earlier valid row.*(?:kept|retained|remains)/i);
  assert.match(warnings[1], /compare/i);
  assert.match(warnings[2], /Row 5.*OTHER.*amount must be greater than zero/s);
  assert.doesNotMatch(warnings[2], /earlier valid row|different invoice/i);
  nodes.get('download').click();
  assert.deepEqual(core.parseCSV(await blobs[0].text()), [
    core.fields,
    ['repeat', 'Example', 'ops@example.com', 'Work', '2.68', 'pending'],
  ]);
});

test('exception invoice IDs are literal text and cannot trigger duplicate advice', () => {
  const {nodes} = page();
  const unsafeID = '<img src=x onerror=alert(1)>';
  nodes.get('csv').value = [
    'invoice_id,client,email,service,amount,status',
    `${unsafeID},Example,ops@example.com,Work,1,paid`,
    'invoice_id is duplicated,Example,invalid,Work,1,paid',
  ].join('\n');
  nodes.get('run').click();
  const warnings = nodes.get('issues').children.map(node => node.textContent);
  assert.equal(warnings.length, 2);
  assert.match(warnings[0], /Row 2.*<img src=x onerror=alert\(1\)>.*invoice_id must be a safe filename/s);
  assert.match(warnings[1], /Row 3.*invoice_id is duplicated.*email is missing or invalid/s);
  for (const warning of warnings) {
    assert.doesNotMatch(warning, /earlier valid row|different invoice/i);
  }
  // The helper rejects innerHTML; also ensure no element was created from the ID.
  function tags(node) { return [node.tagName, ...node.children.flatMap(tags)]; }
  assert.equal(tags(nodes.get('issues')).includes('img'), false);
  assert.equal(nodes.get('download').disabled, true);
});
