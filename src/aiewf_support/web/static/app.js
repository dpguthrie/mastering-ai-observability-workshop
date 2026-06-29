const app = document.getElementById("app");
const messagesEl = document.getElementById("messages");
const emptyState = document.getElementById("emptyState");
const composer = document.getElementById("composer");
const promptEl = document.getElementById("prompt");
const sendButton = document.getElementById("sendButton");
const historyList = document.getElementById("historyList");
const modelButton = document.getElementById("modelButton");
const modelLabel = document.getElementById("modelLabel");
const modelMenu = document.getElementById("modelMenu");
const modelList = document.getElementById("modelList");
const modelSearch = document.getElementById("modelSearch");
const customerSelect = document.getElementById("customerSelect");
const visibilityButton = document.getElementById("visibilityButton");
const visibilityMenu = document.getElementById("visibilityMenu");
const accountMenu = document.getElementById("accountMenu");

const STORAGE_KEY = "aiewf-chat-ui-state";

const state = {
  chats: [],
  activeChatId: null,
  models: [],
  customers: [],
  selectedModel: "gpt-5-mini",
  customerId: "cus_1002",
  busy: false,
  theme: "dark",
};

function uid() {
  return `chat_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function activeChat() {
  return state.chats.find((chat) => chat.id === state.activeChatId) || null;
}

function saveState() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      chats: state.chats,
      activeChatId: state.activeChatId,
      selectedModel: state.selectedModel,
      customerId: state.customerId,
      theme: state.theme,
    }),
  );
}

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    state.chats = parsed.chats || [];
    state.activeChatId = parsed.activeChatId || state.chats[0]?.id || null;
    state.selectedModel = parsed.selectedModel || state.selectedModel;
    state.customerId = parsed.customerId || state.customerId;
    state.theme = parsed.theme || state.theme;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function applyTheme() {
  document.body.classList.toggle("light", state.theme === "light");
}

function closeMenus() {
  modelMenu.classList.remove("open");
  visibilityMenu.classList.remove("open");
  accountMenu.classList.remove("open");
  document.querySelectorAll(".chat-menu").forEach((menu) => menu.remove());
}

function hasConversation(chat) {
  return Boolean(chat?.messages?.some((message) => message.role === "user" || message.role === "assistant"));
}

function createChat(title = "New support chat") {
  const chat = { id: uid(), title, visibility: "private", messages: [], widgets: [] };
  state.chats.unshift(chat);
  state.activeChatId = chat.id;
  saveState();
  render();
}

function startNewChat() {
  const chat = activeChat();
  if (chat && !hasConversation(chat)) {
    promptEl.focus();
    return;
  }
  if (!chat && !state.chats.length) {
    promptEl.focus();
    return;
  }
  createChat();
}

function deleteAllChats() {
  state.chats = [];
  state.activeChatId = null;
  saveState();
  render();
}

function renderHistory() {
  historyList.innerHTML = "";
  if (!state.chats.length) {
    const empty = document.createElement("div");
    empty.className = "muted-empty";
    empty.textContent = "Your conversations will appear here once you start chatting.";
    historyList.append(empty);
    return;
  }
  for (const chat of state.chats) {
    const row = document.createElement("button");
    row.className = `history-item ${chat.id === state.activeChatId ? "active" : ""}`;
    row.innerHTML = `<span></span><span class="history-options">•••</span>`;
    row.querySelector("span").textContent = chat.title;
    row.addEventListener("click", () => {
      state.activeChatId = chat.id;
      saveState();
      render();
    });
    row.querySelector(".history-options").addEventListener("click", (event) => {
      event.stopPropagation();
      showChatMenu(chat, row);
    });
    historyList.append(row);
  }
}

function showChatMenu(chat, anchor) {
  closeMenus();
  const menu = document.createElement("div");
  menu.className = "chat-menu open";
  menu.innerHTML = `
    <button data-action="share">Share <span style="float:right">›</span></button>
    <button data-action="private">Private <span style="float:right">${chat.visibility === "private" ? "✓" : ""}</span></button>
    <button data-action="public">Public <span style="float:right">${chat.visibility === "public" ? "✓" : ""}</span></button>
    <button data-action="delete">Delete</button>
  `;
  document.body.append(menu);
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${rect.right - 12}px`;
  menu.style.top = `${rect.top + 26}px`;
  menu.addEventListener("click", (event) => {
    const action = event.target.closest("button")?.dataset.action;
    if (!action) return;
    if (action === "delete") {
      state.chats = state.chats.filter((item) => item.id !== chat.id);
      state.activeChatId = state.chats[0]?.id || null;
    }
    if (action === "private" || action === "public") {
      chat.visibility = action;
    }
    saveState();
    closeMenus();
    render();
  });
}

function renderMessages() {
  const chat = activeChat();
  messagesEl.innerHTML = "";
  emptyState.style.display = chat && chat.messages.length ? "none" : "grid";
  if (!chat) return;
  for (const message of chat.messages) {
    if (message.role === "user") {
      const node = document.createElement("div");
      node.className = "message user";
      node.textContent = message.content;
      messagesEl.append(node);
    } else {
      const wrap = document.createElement("div");
      wrap.className = "assistant-wrap";
      const thinking = document.createElement("div");
      thinking.className = "thinking";
      thinking.innerHTML = `<span class="spark">✦</span><span>${message.pending ? "Working..." : "Done"}</span>`;
      const thought = document.createElement("div");
      thought.className = "thought";
      if (message.activity?.length) {
        thought.classList.add("activity-log");
        for (const activity of message.activity) {
          thought.append(renderActivityRow(activity));
        }
      } else {
        thought.textContent = message.thought || "Reviewing customer context, available tools, and policy boundaries.";
      }
      const body = document.createElement("div");
      body.className = `message assistant ${message.pending ? "cursor" : ""}`;
      body.innerHTML = markdownToHtml(message.content || "");
      wrap.append(thinking, thought, body);
      if (message.widgets?.length) {
        wrap.append(renderWidgets(message.widgets));
      }
      messagesEl.append(wrap);
    }
  }
  messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
}

function renderActivityRow(activity) {
  const row = document.createElement("div");
  row.className = "activity-row";
  const status = activity.status || "active";

  const dot = document.createElement("span");
  dot.className = `activity-dot ${status}`;
  dot.setAttribute("aria-hidden", "true");

  const label = document.createElement("span");
  label.className = "activity-label";
  label.textContent = activity.label || "Working";

  row.append(dot, label);
  if (activity.tool) {
    const tool = document.createElement("code");
    tool.className = "activity-tool";
    tool.textContent = activity.tool;
    row.append(tool);
  }
  return row;
}

function renderWidgets(widgets) {
  const box = document.createElement("div");
  box.className = "widgets";
  for (const widget of widgets) {
    const node = document.createElement("div");
    node.className = "widget";
    node.innerHTML = `
      <div class="widget-header">
        <strong></strong>
        <span class="status-pill"></span>
      </div>
      <div class="widget-body">
        <div class="widget-detail"></div>
      </div>
    `;
    node.querySelector("strong").textContent = widget.title;
    node.querySelector(".status-pill").textContent = widget.status;
    node.querySelector(".widget-detail").textContent = widget.detail;
    box.append(node);
  }
  return box;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function markdownToHtml(value) {
  const lines = escapeHtml(value).split(/\n{2,}/);
  return lines
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      const withInline = trimmed
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>");
      if (/^[-*] /m.test(withInline)) {
        const items = withInline
          .split("\n")
          .filter((line) => /^[-*] /.test(line))
          .map((line) => `<li>${line.replace(/^[-*] /, "")}</li>`)
          .join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${withInline.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function renderModels() {
  const query = modelSearch.value.toLowerCase();
  modelList.innerHTML = "";
  const filtered = state.models.filter((model) => model.label.toLowerCase().includes(query) || model.id.toLowerCase().includes(query));
  for (const model of filtered) {
    const button = document.createElement("button");
    button.className = `model-option ${model.id === state.selectedModel ? "active" : ""}`;
    button.innerHTML = `
      <span>
        <span class="model-name"></span>
        <span class="model-meta"></span>
      </span>
    `;
    button.querySelector(".model-name").textContent = model.label;
    button.querySelector(".model-meta").textContent = model.provider;
    button.addEventListener("click", () => {
      state.selectedModel = model.id;
      saveState();
      closeMenus();
      render();
    });
    modelList.append(button);
  }
}

function renderCustomers() {
  customerSelect.innerHTML = "";
  for (const customer of state.customers) {
    const option = document.createElement("option");
    option.value = customer.customer_id;
    option.textContent = `${customer.name} (${customer.customer_id})`;
    customerSelect.append(option);
  }
  customerSelect.value = state.customerId;
}

function render() {
  applyTheme();
  const selected = state.models.find((model) => model.id === state.selectedModel);
  modelLabel.textContent = selected?.label || state.selectedModel;
  renderHistory();
  renderMessages();
  renderModels();
  renderCustomers();
}

async function loadConfig() {
  const [configResponse, customersResponse] = await Promise.all([fetch("/api/config"), fetch("/api/customers")]);
  const config = await configResponse.json();
  const customers = await customersResponse.json();
  state.models = config.models || [];
  state.customers = customers.customers || [];
  state.customerId = config.customer_id || state.customerId;
  if (!state.models.some((model) => model.id === state.selectedModel)) {
    state.selectedModel = config.default_model || state.models[0]?.id || state.selectedModel;
  }
  render();
}

function appendUserMessage(content) {
  let chat = activeChat();
  if (!chat) {
    createChat(content.split(/\s+/).slice(0, 5).join(" "));
    chat = activeChat();
  }
  if (!chat.messages.length) {
    chat.title = content.split(/\s+/).slice(0, 5).join(" ").replace(/[?.!,]+$/, "") || "Support chat";
  }
  chat.messages.push({ role: "user", content });
  const assistant = {
    id: uid(),
    role: "assistant",
    content: "",
    pending: true,
    thought: "Thinking through the customer request and available support tools.",
    activity: [],
    widgets: [],
    requestId: null,
  };
  chat.messages.push(assistant);
  saveState();
  render();
  return assistant;
}

async function sendMessage(content) {
  if (state.busy) return;
  state.busy = true;
  sendButton.disabled = true;
  const assistant = appendUserMessage(content);
  const chat = activeChat();
  const payloadMessages = chat.messages
    .filter((message) => !message.pending)
    .map((message) => ({ role: message.role, content: message.content }));

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: payloadMessages,
        model: state.selectedModel,
        customer_id: state.customerId,
        conversation_id: chat.id,
      }),
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        handleSsePart(part, assistant);
      }
    }
  } catch (error) {
    assistant.content += `\n${error.message}`;
  } finally {
    assistant.pending = false;
    state.busy = false;
    sendButton.disabled = false;
    saveState();
    render();
  }
}

function upsertActivity(assistant, activity) {
  assistant.activity ||= [];
  const id = activity.id || `${activity.tool || "activity"}-${activity.label || assistant.activity.length}`;
  const existing = assistant.activity.find((item) => item.id === id);
  const next = {
    id,
    status: activity.status || "active",
    tool: activity.tool || null,
    label: activity.label || "Working",
  };
  if (existing) {
    Object.assign(existing, next);
  } else {
    assistant.activity.push(next);
  }
  assistant.thought = next.label;
}

function completeOpenActivities(assistant) {
  if (!assistant.activity?.length) return;
  for (const activity of assistant.activity) {
    if (activity.status === "active") {
      activity.status = "complete";
    }
  }
}

function handleSsePart(part, assistant) {
  const eventLine = part.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = part.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return;
  const event = eventLine.slice(6).trim();
  const data = JSON.parse(dataLine.slice(5).trim());
  if (event === "delta") {
    assistant.content += data.text || "";
  }
  if (event === "meta") {
    assistant.thought = `Using ${data.model}. Preparing support context.`;
    upsertActivity(assistant, {
      id: "run",
      status: "active",
      label: `Using ${data.model}`,
    });
    assistant.requestId = data.request_id || assistant.requestId;
  }
  if (event === "activity") {
    upsertActivity(assistant, data);
  }
  if (event === "widgets") {
    assistant.widgets = data.widgets || [];
  }
  if (event === "done") {
    assistant.pending = false;
    completeOpenActivities(assistant);
    assistant.requestId = data.request_id || assistant.requestId;
  }
  if (event === "error") {
    assistant.thought = data.message;
    upsertActivity(assistant, {
      id: "error",
      status: "error",
      label: data.message,
    });
  }
  renderMessages();
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const value = promptEl.value.trim();
  if (!value) return;
  promptEl.value = "";
  sendButton.classList.remove("ready");
  sendMessage(value);
});

promptEl.addEventListener("input", () => {
  sendButton.classList.toggle("ready", Boolean(promptEl.value.trim()));
});

promptEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.querySelectorAll(".suggestions button").forEach((button) => {
  button.addEventListener("click", () => {
    const value = button.textContent.trim();
    if (value) {
      promptEl.value = "";
      sendButton.classList.remove("ready");
      sendMessage(value);
    }
  });
});

document.getElementById("newChat").addEventListener("click", startNewChat);
document.getElementById("newChatRail").addEventListener("click", startNewChat);
document.getElementById("deleteAll").addEventListener("click", deleteAllChats);
document.getElementById("deleteRail").addEventListener("click", deleteAllChats);
document.getElementById("sidebarToggle").addEventListener("click", () => app.classList.toggle("sidebar-collapsed"));
customerSelect.addEventListener("change", () => {
  state.customerId = customerSelect.value;
  saveState();
});
modelButton.addEventListener("click", (event) => {
  event.stopPropagation();
  modelMenu.classList.toggle("open");
});
modelSearch.addEventListener("input", renderModels);
visibilityButton.addEventListener("click", (event) => {
  event.stopPropagation();
  visibilityMenu.classList.toggle("open");
});
document.getElementById("accountMenuButton").addEventListener("click", (event) => {
  event.stopPropagation();
  accountMenu.classList.toggle("open");
});
document.getElementById("themeToggle").addEventListener("click", toggleTheme);
document.getElementById("themeToggleText").addEventListener("click", toggleTheme);
visibilityMenu.addEventListener("click", (event) => {
  const visibility = event.target.closest("button")?.dataset.visibility;
  const chat = activeChat();
  if (!visibility || !chat) return;
  chat.visibility = visibility;
  saveState();
  closeMenus();
  render();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".model-menu, .model-pill, .visibility-menu, .visibility, .account")) {
    closeMenus();
  }
});

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  saveState();
  render();
}

loadState();
applyTheme();
loadConfig();
render();
