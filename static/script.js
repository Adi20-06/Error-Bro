const $ = (id) => document.getElementById(id);

const chat = $("chat");
const inner = $("chat-inner");
const welcome = $("welcome");
const form = $("chat-form");
const input = $("user-input");
const sendBtn = $("send-btn");
const counter = $("counter");
const toast = $("toast");
const sidebar = $("sidebar");
const scrim = $("scrim");
const topicList = $("topic-list");

const SESSION_KEY = "errorTranslatorSession";
const REQUEST_TIMEOUT_MS = 45000;

let sessionId = null;
let busy = false;
let maxChars = 4000;
let toastTimer;

/* ---------- Small helpers ---------- */

// Builds an element. Uses textContent, so text can never run as HTML.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
}

function scrollDown(instant = false) {
  chat.scrollTo({ top: chat.scrollHeight, behavior: instant ? "auto" : "smooth" });
}

function loadSessionId() {
  try { return sessionStorage.getItem(SESSION_KEY); } catch (err) { return null; }
}

function storeSessionId(id) {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch (err) {
    // Storage can be blocked. The chat still works without it.
  }
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 180) + "px";
}

function updateCounter() {
  const n = input.value.length;
  if (n > maxChars * 0.8) {
    counter.textContent = `${n} / ${maxChars}`;
    counter.classList.toggle("over", n > maxChars);
  } else {
    counter.textContent = "";
    counter.classList.remove("over");
  }
}

function setBusy(value) {
  busy = value;
  sendBtn.disabled = value;
}

/* ---------- Mobile menu ---------- */

function openDrawer() {
  sidebar.classList.add("open");
  scrim.classList.add("show");
}
function closeDrawer() {
  sidebar.classList.remove("open");
  scrim.classList.remove("show");
}

/* ---------- Safe mini-markdown renderer ---------- */
// Turns the bot's text into real elements: bold, `code`, lists, code blocks, links.
// It only ever creates elements itself, so the bot's text cannot inject HTML.

function renderInline(text, parent) {
  text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).forEach((part) => {
    if (!part) return;
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      parent.append(el("strong", null, part.slice(2, -2)));
    } else if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      parent.append(el("code", null, part.slice(1, -1)));
    } else {
      parent.append(document.createTextNode(part));
    }
  });
}

function renderMarkdown(text) {
  const root = el("div", "md");
  const lines = text.replace(/\r/g, "").split("\n");
  let list = null;
  let listType = null;
  let code = null; // lines of a ``` block while we are inside one

  const closeList = () => { list = null; listType = null; };
  const addCodeBlock = (codeLines) => {
    const pre = el("pre");
    pre.append(el("code", null, codeLines.join("\n")));
    root.append(pre);
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (code !== null) {
      if (trimmed.startsWith("```")) { addCodeBlock(code); code = null; }
      else code.push(line);
      continue;
    }
    if (trimmed.startsWith("```")) { closeList(); code = []; continue; }
    if (!trimmed) { closeList(); continue; }

    let m = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
    if (m) {
      if (listType !== "ol") {
        list = el("ol");
        list.start = parseInt(m[1], 10);
        root.append(list);
        listType = "ol";
      }
      const li = el("li");
      renderInline(m[2], li);
      list.append(li);
      continue;
    }

    m = trimmed.match(/^[-*•]\s+(.*)$/);
    if (m) {
      if (listType !== "ul") {
        list = el("ul");
        root.append(list);
        listType = "ul";
      }
      const li = el("li");
      renderInline(m[1], li);
      list.append(li);
      continue;
    }

    closeList();

    // "Source: https://..." becomes a real link (http and https only)
    m = trimmed.match(/^Source:\s*(https?:\/\/\S+)$/i);
    if (m) {
      const p = el("p", "source");
      p.append(document.createTextNode("Source: "));
      const a = el("a", null, m[1]);
      a.href = m[1];
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      p.append(a);
      root.append(p);
      continue;
    }

    // Section titles: "## Title" or a line that is only **Title**
    m = trimmed.match(/^#{1,4}\s+(.*)$/) || trimmed.match(/^\*\*([^*]+)\*\*:?$/);
    if (m) {
      root.append(el("p", "sec", m[1]));
      continue;
    }

    const p = el("p");
    renderInline(trimmed, p);
    root.append(p);
  }

  if (code !== null && code.length) addCodeBlock(code);
  return root;
}

/* ---------- Message pieces ---------- */

function addUser(text) {
  const row = el("div", "row user");
  row.append(el("div", "bubble", text));
  inner.append(row);
  scrollDown();
}

function makeFeedback(messageId, startRating) {
  const box = el("div", "fb");
  const up = el("button", "fb-btn", "👍");
  const down = el("button", "fb-btn", "👎");
  up.title = "Helpful";
  down.title = "Not helpful";
  up.setAttribute("aria-label", "Helpful");
  down.setAttribute("aria-label", "Not helpful");

  const paint = (rating) => {
    up.classList.toggle("on", rating === 1);
    down.classList.toggle("on", rating === -1);
  };
  paint(startRating);

  const submit = async (rating) => {
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_id: messageId, rating }),
      });
      if (!res.ok) throw new Error("feedback failed");
      paint(rating);
      showToast("Thanks for the feedback");
    } catch (err) {
      showToast("Could not save your feedback.");
    }
  };

  up.addEventListener("click", () => submit(1));
  down.addEventListener("click", () => submit(-1));
  box.append(up, down);
  return box;
}

function addBot(text, opts = {}) {
  const row = el("div", "row bot");
  row.append(el("div", "avatar", "</>"));

  const wrap = el("div", "bot-wrap");
  const bubble = el("div", "bubble");
  bubble.append(renderMarkdown(text));
  wrap.append(bubble);

  // Source chips for any link the reply did not already include
  const extra = (opts.sources || []).filter((s) => s && /^https?:\/\//.test(s.url) && !text.includes(s.url));
  if (extra.length) {
    const srcRow = el("div", "src-row");
    extra.forEach((s) => {
      const a = el("a", "src-chip", "📖 " + s.title);
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      srcRow.append(a);
    });
    wrap.append(srcRow);
  }

  const foot = el("div", "foot");
  const bits = [];
  if (opts.latency != null) bits.push((opts.latency / 1000).toFixed(1) + "s");
  if (opts.tokens != null) bits.push(opts.tokens + " tokens");
  if (bits.length) foot.append(el("span", "meta", bits.join(" · ")));
  if (opts.messageId) foot.append(makeFeedback(opts.messageId, opts.rating || null));
  if (foot.children.length) wrap.append(foot);

  row.append(wrap);
  inner.append(row);
  scrollDown(opts.instant);
}

function addTyping() {
  const row = el("div", "row bot");
  row.append(el("div", "avatar", "</>"));
  const wrap = el("div", "bot-wrap");
  const bubble = el("div", "bubble typing");
  bubble.setAttribute("aria-label", "The bot is typing");
  bubble.append(el("span"), el("span"), el("span"));
  wrap.append(bubble);
  row.append(wrap);
  inner.append(row);
  scrollDown();
  return row;
}

function addError(message, onRetry) {
  const row = el("div", "row bot");
  row.append(el("div", "avatar warn", "!"));

  const wrap = el("div", "bot-wrap");
  const bubble = el("div", "bubble error");
  bubble.append(el("p", null, message));

  if (onRetry) {
    const btn = el("button", "retry-btn", "↻ Try again");
    btn.addEventListener("click", () => {
      row.remove();
      onRetry();
    });
    bubble.append(btn);
  }

  wrap.append(bubble);
  row.append(wrap);
  inner.append(row);
  scrollDown();
}

/* ---------- Talking to the server ---------- */

async function send(rawText, isRetry = false) {
  if (busy) return;

  const text = rawText.trim();
  if (!text) {
    showToast("Please type a message before sending.");
    return;
  }
  if (text.length > maxChars) {
    addError(`That message is ${text.length} characters, which is over the ${maxChars} limit. Try pasting just the error line.`);
    return;
  }

  setBusy(true);
  closeDrawer();
  welcome.hidden = true;

  if (!isRetry) {
    addUser(text);
    input.value = "";
    resizeInput();
    updateCounter();
  }

  const typing = addTyping();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => null);
    typing.remove();

    if (!res.ok) {
      const message = (data && data.error && data.error.message) || "Something went wrong. Please try again.";
      const retryable = [429, 500, 502, 503, 504].includes(res.status);
      addError(message, retryable ? () => send(text, true) : null);
    } else {
      sessionId = data.session_id;
      storeSessionId(sessionId);
      addBot(data.reply, {
        messageId: data.message_id,
        latency: data.latency_ms,
        tokens: data.tokens_used,
        sources: data.sources,
      });
    }
  } catch (err) {
    typing.remove();
    const timedOut = err.name === "AbortError";
    addError(
      timedOut ? "The server took too long to answer. Please try again." : "Could not reach the server. Is it running?",
      () => send(text, true)
    );
  } finally {
    clearTimeout(timer);
    setBusy(false);
    input.focus();
  }
}

async function newChat() {
  if (busy) return;
  if (sessionId) {
    try {
      await fetch("/api/reset/" + encodeURIComponent(sessionId), { method: "POST" });
    } catch (err) {
      // If the server is unreachable we still clear the screen.
    }
  }
  sessionId = null;
  storeSessionId(null);
  inner.querySelectorAll(".row").forEach((row) => row.remove());
  welcome.hidden = false;
  input.value = "";
  resizeInput();
  updateCounter();
  closeDrawer();
  chat.scrollTo({ top: 0 });
  input.focus();
}

/* ---------- Startup ---------- */

async function loadConfig() {
  try {
    const res = await fetch("/api/config-check");
    const data = await res.json();
    if (data.max_input_chars) maxChars = data.max_input_chars;
  } catch (err) {
    // Keep the default limit.
  }
}

async function loadTopics() {
  try {
    const res = await fetch("/api/topics");
    const data = await res.json();
    topicList.replaceChildren();
    (data.topics || []).forEach((t) => topicList.append(el("li", null, t)));
    if (!(data.topics || []).length) topicList.append(el("li", null, "No topics yet"));
  } catch (err) {
    topicList.replaceChildren(el("li", null, "Could not load topics"));
  }
}

// If the page is refreshed, bring back the conversation from the server.
async function restoreChat() {
  const id = loadSessionId();
  if (!id) return;
  try {
    const res = await fetch("/api/history/" + encodeURIComponent(id));
    if (!res.ok) {
      storeSessionId(null); // the server no longer has it (for example after a restart)
      return;
    }
    const data = await res.json();
    if (!data.messages.length) return;

    sessionId = id;
    welcome.hidden = true;
    data.messages.forEach((m) => {
      if (m.role === "user") addUser(m.content);
      else addBot(m.content, { messageId: m.message_id, rating: m.rating, instant: true });
    });
    scrollDown(true);
  } catch (err) {
    // Start fresh if anything goes wrong.
  }
}

/* ---------- Events ---------- */

form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});

input.addEventListener("input", () => {
  resizeInput();
  updateCounter();
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => send(chip.dataset.text));
});

$("new-chat").addEventListener("click", newChat);
$("new-chat-top").addEventListener("click", newChat);
$("menu-btn").addEventListener("click", openDrawer);
scrim.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDrawer();
});

loadConfig();
loadTopics();
restoreChat();
input.focus();