'use strict';

const state = { sessionId: null, sending: false };

const els = {
  sessionsList: document.getElementById('sessions-list'),
  newSessionBtn: document.getElementById('new-session'),
  messages: document.getElementById('messages'),
  input: document.getElementById('chat-input'),
  sendBtn: document.getElementById('send-btn'),
  sessionTitle: document.getElementById('session-title'),
};

let pendingToolCard = null; // 最近一次 tool_call 的卡片，用于 tool_result 回填

async function api(url, options) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(err.detail || '请求失败');
  }
  return resp.json();
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function appendUser(text) {
  const div = document.createElement('div');
  div.className = 'bubble user';
  div.textContent = text;
  els.messages.appendChild(div);
  scrollToBottom();
}

function appendAssistant(text) {
  const div = document.createElement('div');
  div.className = 'bubble assistant';
  div.textContent = text;
  els.messages.appendChild(div);
  scrollToBottom();
  return div;
}

function appendError(text) {
  const div = document.createElement('div');
  div.className = 'bubble error';
  div.textContent = '出错了：' + text;
  els.messages.appendChild(div);
  scrollToBottom();
}

function createToolCard(name, args, result) {
  const card = document.createElement('div');
  card.className = 'tool-card';

  const header = document.createElement('div');
  header.className = 'tool-card-header';
  const nameEl = document.createElement('span');
  nameEl.className = 'tool-name';
  nameEl.textContent = '🔧 ' + name;
  const statusEl = document.createElement('span');
  statusEl.className = 'tool-status';
  statusEl.textContent = result === undefined ? '运行中…' : '完成';
  if (result !== undefined) statusEl.classList.add('done');
  header.append(nameEl, statusEl);

  const body = document.createElement('div');
  body.className = 'tool-card-body collapsed';

  const argsLabel = document.createElement('div');
  argsLabel.className = 'tool-label';
  argsLabel.textContent = '参数';
  const argsPre = document.createElement('pre');
  argsPre.textContent = JSON.stringify(args ?? {}, null, 2);
  const resultLabel = document.createElement('div');
  resultLabel.className = 'tool-label';
  resultLabel.textContent = '返回';
  const resultPre = document.createElement('pre');
  resultPre.textContent = result === undefined ? '…' : String(result);

  body.append(argsLabel, argsPre, resultLabel, resultPre);
  header.onclick = () => body.classList.toggle('collapsed');

  card.append(header, body);
  els.messages.appendChild(card);
  scrollToBottom();
  return { card, statusEl, resultPre };
}

function renderMessage(m) {
  if (m.role === 'user') {
    appendUser(m.content);
  } else if (m.role === 'assistant') {
    if (m.tool_calls) {
      for (const tc of m.tool_calls) {
        createToolCard(tc.name, tc.arguments, tc.result);
      }
    }
    if (m.content) {
      appendAssistant(m.content);
    }
  }
}

async function loadSessions() {
  const { sessions } = await api('/api/sessions');
  els.sessionsList.innerHTML = '';
  for (const s of sessions) {
    const item = document.createElement('div');
    item.className = 'session-item' + (s.id === state.sessionId ? ' active' : '');
    item.textContent = s.title || '新会话';
    item.onclick = () => selectSession(s.id);
    els.sessionsList.appendChild(item);
  }
}

async function newSession() {
  const { id } = await api('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: '新会话' }),
  });
  state.sessionId = id;
  els.messages.innerHTML = '';
  els.sessionTitle.textContent = '新会话';
  await loadSessions();
  els.input.focus();
}

async function selectSession(id) {
  state.sessionId = id;
  await loadSessions();
  const { messages } = await api(`/api/sessions/${id}/messages`);
  const { sessions } = await api('/api/sessions');
  const s = sessions.find((x) => x.id === id);
  els.sessionTitle.textContent = s ? s.title : '会话';
  els.messages.innerHTML = '';
  for (const m of messages) renderMessage(m);
  scrollToBottom();
}

function parseSSE(raw) {
  let event = 'message';
  let data = '';
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  return { event, data };
}

function handleEvent(event, data) {
  let obj;
  try { obj = JSON.parse(data); } catch { obj = {}; }

  if (event === 'token') {
    appendAssistant(obj.delta);
  } else if (event === 'tool_call') {
    pendingToolCard = createToolCard(obj.name, obj.arguments);
  } else if (event === 'tool_result') {
    if (pendingToolCard) {
      pendingToolCard.resultPre.textContent = String(obj.result);
      pendingToolCard.statusEl.textContent = '完成';
      pendingToolCard.statusEl.classList.add('done');
      pendingToolCard = null;
    }
  } else if (event === 'done') {
    loadSessions();
  } else if (event === 'error') {
    appendError(obj.message || '未知错误');
  }
}

async function sendMessage() {
  if (state.sending) return;
  const text = els.input.value.trim();
  if (!text) return;
  if (state.sessionId === null) await newSession();

  appendUser(text);
  els.input.value = '';
  els.input.style.height = 'auto';
  setSending(true);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, message: text }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '请求失败' }));
      throw new Error(err.detail || '请求失败');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let assistantBubble = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const { event, data } = parseSSE(raw);
        if (event === 'token') {
          if (!assistantBubble) assistantBubble = appendAssistant('');
          const obj = JSON.parse(data);
          assistantBubble.textContent += obj.delta;
          scrollToBottom();
        } else {
          handleEvent(event, data);
        }
      }
    }
  } catch (e) {
    appendError(e.message);
  } finally {
    setSending(false);
    els.input.focus();
  }
}

function setSending(v) {
  state.sending = v;
  els.sendBtn.disabled = v;
  els.input.disabled = v;
}

els.newSessionBtn.addEventListener('click', newSession);
els.sendBtn.addEventListener('click', sendMessage);
els.input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
els.input.addEventListener('input', () => {
  els.input.style.height = 'auto';
  els.input.style.height = Math.min(els.input.scrollHeight, 120) + 'px';
});

(async function init() {
  await loadSessions();
  const { sessions } = await api('/api/sessions');
  if (sessions.length === 0) {
    await newSession();
  } else {
    await selectSession(sessions[0].id);
  }
})();
