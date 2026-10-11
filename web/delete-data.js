// "Удалить мои данные": a code to the email, then every review left from that address is deleted on our server.
const LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
const API = LOCAL ? 'http://127.0.0.1:8085' : 'https://data.egematch.ru';
const $ = selector => document.querySelector(selector);
let form = null, requestToken = null;

async function api(path, options) {
  let response;
  try {
    response = await fetch(`${API}${path}`, {...options, credentials: 'omit', mode: 'cors'});
  } catch {
    throw new Error('Нет связи с сервером. Проверь интернет и попробуй ещё раз.');
  }
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) throw new Error(data.error || 'Что-то пошло не так. Попробуй ещё раз чуть позже.');
  return data;
}

function busy(button, on) { button.disabled = on; }
const error = (id, message) => { $(`#${id}-error`).textContent = message || ''; };

async function loadToken() {
  form = {...await api('/api/reviews/form', {method: 'GET'}), loadedAt: Date.now()};
}

$('#dd-form').addEventListener('submit', async event => {
  event.preventDefault();
  error('dd-email', '');
  const email = $('#dd-email').value.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { error('dd-email', 'Проверь адрес почты.'); return; }
  const button = $('#dd-send');
  busy(button, true);
  try {
    if (!form) await loadToken();
    const wait = 9000 - (Date.now() - form.loadedAt);
    if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
    const result = await api('/api/data/delete/request', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, formToken: form.formToken, website: $('#dd-website').value})});
    requestToken = result.requestToken;
    $('#dd-form').hidden = true;
    $('#dd-code-form').hidden = false;
    $('#dd-code-email').textContent = result.email;
    $('#dd-code').focus();
  } catch (err) {
    form = null;
    error('dd-email', err.message);
  } finally {
    busy(button, false);
  }
});

$('#dd-code').addEventListener('input', event => { event.target.value = event.target.value.replace(/\D/g, '').slice(0, 6); });
$('#dd-code-form').addEventListener('submit', async event => {
  event.preventDefault();
  error('dd-code', '');
  const code = $('#dd-code').value;
  if (code.length !== 6) { error('dd-code', 'Код — шесть цифр из письма.'); return; }
  const button = $('#dd-confirm');
  busy(button, true);
  try {
    const result = await api('/api/data/delete/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({requestToken, code})});
    $('#dd-code-form').hidden = true;
    $('#dd-done').hidden = false;
    $('#dd-done-text').textContent = result.reviews
      ? `Удалили отзывов: ${result.reviews}. Оценки школ пересчитаны, на сайте этих отзывов больше нет.`
      : 'С этой почты отзывов не было — хранить было нечего.';
  } catch (err) {
    error('dd-code', err.message);
  } finally {
    busy(button, false);
  }
});

loadToken().catch(() => {});
