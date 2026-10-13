const form = document.querySelector('#job-form');
const runButton = document.querySelector('#run-button');
const stopButton = document.querySelector('#stop-button');
const statusBadge = document.querySelector('#status-badge');
const statusText = statusBadge.querySelector('span');
const activityMessage = document.querySelector('#activity-message');
const logElement = document.querySelector('#log');

const HEARTBEAT_INTERVAL = 4000;

const statusLabels = {
  idle: 'GOTOWY',
  running: 'W TOKU',
  completed: 'ZAKOŃCZONO',
  failed: 'BŁĄD',
  stopped: 'ZATRZYMANO',
};

let polling = false;
let lastStatus = 'idle';

function startHeartbeat() {
  const ping = () => {
    fetch('/api/heartbeat', { cache: 'no-store' }).catch(() => {});
  };
  ping();
  window.setInterval(ping, HEARTBEAT_INTERVAL);
}

function notifyServerClosing() {
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/close');
      return;
    }
  } catch (error) {
    // ignorujemy i próbujemy fallbacku
  }
  fetch('/api/close', { method: 'POST', keepalive: true }).catch(() => {});
}

window.addEventListener('pagehide', notifyServerClosing);
window.addEventListener('beforeunload', notifyServerClosing);

async function loadPlatformConfig() {
  try {
    const response = await fetch('/api/config', { cache: 'no-store' });
    const config = await response.json();
    const linux = config.platform === 'Linux';
    const folderInput = document.querySelector('#folder');
    const ffmpegInput = document.querySelector('#ffmpeg');
    folderInput.placeholder = linux ? '/home/user/Videos' : 'D:\\Filmy';
    ffmpegInput.placeholder = linux ? '/usr/bin/ffmpeg lub folder z narzędziami' : 'Automatycznie z PATH lub własna ścieżka';
    document.querySelector('#ffmpeg-hint').textContent = linux
      ? 'Linux: zainstaluj ffmpeg i ffprobe w systemie albo wskaż ich folder.'
      : 'Folder z ffmpeg i ffprobe albo ścieżka do ffmpeg.';
  } catch (error) {
    document.querySelector('#ffmpeg-hint').textContent = 'Folder z ffmpeg i ffprobe albo ścieżka do ffmpeg.';
  }
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Nie udało się wykonać operacji.');
  return result;
}

function setStatus(status, returnCode) {
  statusBadge.dataset.status = status;
  statusText.textContent = statusLabels[status] || status.toUpperCase();
  runButton.disabled = status === 'running';
  stopButton.disabled = status !== 'running';
  if (status === 'running') activityMessage.textContent = 'Skrypt przetwarza pliki';
  else if (status === 'completed') activityMessage.textContent = 'Zadanie zakończone pomyślnie';
  else if (status === 'failed') activityMessage.textContent = `Skrypt zakończył pracę z kodem ${returnCode ?? 'błędu'}`;
  else if (status === 'stopped') activityMessage.textContent = 'Zadanie zatrzymane';
  else activityMessage.textContent = 'Oczekiwanie na uruchomienie';
}

function showLog(text) {
  const atBottom = logElement.scrollHeight - logElement.scrollTop - logElement.clientHeight < 36;
  logElement.textContent = text || '';
  if (atBottom) logElement.scrollTop = logElement.scrollHeight;
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    const result = await response.json();
    showLog(result.logs);
    setStatus(result.status, result.return_code);
    if (result.status !== lastStatus) lastStatus = result.status;
    if (result.status !== 'running') {
      polling = false;
      return;
    }
  } catch (error) {
    activityMessage.textContent = 'Utracono połączenie z serwerem';
    polling = false;
    return;
  }
  window.setTimeout(refreshStatus, 350);
}

function beginPolling() {
  if (polling) return;
  polling = true;
  refreshStatus();
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = {
    folder: data.get('folder'),
    output: data.get('output'),
    ffmpeg: data.get('ffmpeg'),
    overwrite: document.querySelector('#overwrite').checked,
  };
  try {
    await postJson('/api/run', payload);
    showLog('Uruchamianie skryptu...\n');
    lastStatus = 'running';
    beginPolling();
  } catch (error) {
    activityMessage.textContent = error.message;
  }
});

stopButton.addEventListener('click', async () => {
  try {
    await postJson('/api/stop');
    activityMessage.textContent = 'Wysyłanie sygnału zatrzymania...';
  } catch (error) {
    activityMessage.textContent = error.message;
  }
});

beginPolling();
startHeartbeat();
loadPlatformConfig();