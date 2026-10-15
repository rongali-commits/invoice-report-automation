/* Shared browser core, also loaded directly by Node's built-in test runner. */
(function (root) {
  'use strict';

  const fields = ['invoice_id', 'client', 'email', 'service', 'amount', 'status'];
  const maxCents = 99999999999999n;
  const reserved = /^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$/;

  function parseCSV(text) {
    const records = [];
    let cells = [], value = '', quoted = false, closed = false, started = false;
    const field = () => { cells.push(value); value = ''; closed = false; };
    const record = () => {
      if (started || cells.length) { field(); records.push(cells); }
      cells = []; value = ''; closed = false; started = false;
    };
    text = text.replace(/^\uFEFF/, '');
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (quoted) {
        if (char === '"') {
          if (text[i + 1] === '"') { value += '"'; i++; }
          else { quoted = false; closed = true; }
        } else value += char;
      } else if (char === ',') { field(); started = true; }
      else if (char === '\r' || char === '\n') {
        record();
        if (char === '\r' && text[i + 1] === '\n') i++;
      } else if (closed) throw new Error('Malformed CSV: unexpected text after a closing quote');
      else if (char === '"' && value === '') { quoted = true; started = true; }
      else { value += char; started = true; }
    }
    if (quoted) throw new Error('Malformed CSV: unterminated quoted field');
    record();
    return records;
  }

  function formatCents(cents) {
    return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
  }

  function money(cents) {
    const [whole, fraction] = formatCents(cents).split('.');
    return `$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
  }

  function amountCents(value) {
    const text = value.trim();
    if (/^[+-]?(?:inf(?:inity)?|s?nan[0-9]*)$/i.test(text)) {
      throw new Error('amount must be finite');
    }
    const match = /^([+-]?)(?:([0-9]+)(?:\.([0-9]*))?|\.([0-9]+))(?:[eE]([+-]?[0-9]+))?$/.exec(text);
    if (!match) throw new Error('amount is not a number');
    const exponent = Number(match[5] || '0');
    if (Math.abs(exponent) > 1000) {
      throw new Error('amount exponent must be between -1000 and 1000');
    }
    const fraction = match[3] === undefined ? (match[4] || '') : match[3];
    const digits = ((match[2] || '') + fraction).replace(/^0+/, '') || '0';
    if (match[1] === '-' || digits === '0') {
      throw new Error('amount must be greater than zero');
    }
    const shift = exponent - fraction.length + 2;
    const cut = digits.length + shift;
    if (cut > 14) throw new Error('amount must not exceed USD 999999999999.99');
    let cents, discarded;
    if (shift >= 0) {
      cents = BigInt(digits) * (10n ** BigInt(shift));
      discarded = '';
    } else {
      cents = cut > 0 ? BigInt(digits.slice(0, cut)) : 0n;
      discarded = cut >= 0 ? digits.slice(cut) : '';
    }
    const remainder = /[1-9]/.test(discarded);
    if (cents > maxCents || (cents === maxCents && remainder)) {
      throw new Error('amount must not exceed USD 999999999999.99');
    }
    // Half-even rounding on decimal digits, without floating point conversion.
    if (discarded[0] > '5' || (discarded[0] === '5' &&
        (/[1-9]/.test(discarded.slice(1)) || cents % 2n === 1n))) cents++;
    if (cents === 0n) throw new Error('amount must round to at least USD 0.01');
    return cents;
  }

  function validateCSV(text) {
    const rows = parseCSV(text);
    const headers = rows.shift() || [];
    const missing = fields.filter(name => !headers.includes(name)).sort();
    if (missing.length) throw new Error(`Missing required columns: ${missing.join(', ')}`);
    if (new Set(headers).size !== headers.length) {
      throw new Error('Duplicate column names are not allowed');
    }
    const clean = [], issues = [], seen = new Set();
    let totalCents = 0n;
    rows.forEach((cells, index) => {
      const data = Object.fromEntries(fields.map(name => [name, (cells[headers.indexOf(name)] || '').trim()]));
      data.email = data.email.toLowerCase(); data.status = data.status.toLowerCase();
      const reasons = [];
      if (cells.length > headers.length) reasons.push('row has more cells than header');
      let cents;
      try { cents = amountCents(data.amount); } catch (error) { reasons.push(error.message); }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) reasons.push('email is missing or invalid');
      const id = data.invoice_id, key = id.toUpperCase();
      if (!id) reasons.push('invoice_id is required');
      else if (new TextEncoder().encode(id).length > 251) {
        reasons.push('invoice_id must be at most 251 UTF-8 bytes');
      }
      else if (id === '.' || id === '..' || /[<>:"/\\|?*\x00-\x1f]/.test(id) ||
          /[. ]$/.test(id) || reserved.test(id.split('.')[0].replace(/ +$/, '').toUpperCase())) {
        reasons.push('invoice_id must be a safe filename');
      } else if (seen.has(key)) reasons.push('invoice_id is duplicated');
      if (!['paid', 'pending'].includes(data.status)) reasons.push('status must be paid or pending');
      if (!data.client || !data.service) reasons.push('client and service are required');
      if (reasons.length) {
        issues.push({row_number: index + 2, invoice_id: id, reason: reasons.join('; ')});
      } else {
        seen.add(key); data.amount = formatCents(cents); clean.push(data); totalCents += cents;
      }
    });
    return {rows_read: rows.length, clean, issues, totalCents, clean_total_decimal: formatCents(totalCents)};
  }

  function spreadsheetText(value) {
    return /^\s*[=+\-@]/.test(value) ? `'${value}` : value;
  }

  function exportCSV(clean) {
    const quote = value => `"${spreadsheetText(String(value)).replaceAll('"', '""')}"`;
    return [fields.join(','), ...clean.map(row => fields.map(name => quote(row[name])).join(','))].join('\r\n') + '\r\n';
  }

  const api = {fields, parseCSV, amountCents, formatCents, money, validateCSV, exportCSV};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LedgerFlow = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
