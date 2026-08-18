(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const isDevBrowser = new URLSearchParams(window.location.search).get("dev") === "1";
  const REFRESH_INTERVAL_MS = 4000;
  let isLoading = false;

  const STATUS = [
    ["Новый", "new"],
    ["На сборку", "assembly-queue"],
    ["Собирается", "assembling"],
    ["Не хватает позиции", "missing-item"],
    ["Собран", "assembled"],
    ["Передан в доставку", "handed-to-delivery"],
    ["Отправлен СДЭК", "sent-cdek"],
    ["Передан курьеру", "handed-to-courier"],
    ["Доставлен", "delivered"],
  ];
  const statusClass = Object.fromEntries(STATUS);

  const elements = {
    orders: document.querySelector("#orders"),
    count: document.querySelector("#order-count"),
    sync: document.querySelector("#sync-status"),
    error: document.querySelector("#app-error"),
    refresh: document.querySelector("#refresh-button"),
  };

  if (tg) {
    tg.ready();
    tg.expand();
    tg.setHeaderColor?.("bg_color");
  }

  function headers() {
    if (tg?.initData) return { "X-Telegram-Init-Data": tg.initData };
    if (isDevBrowser) {
      return { "X-Dev-User-Id": "999999", "X-Dev-User-Name": "Тестовый пользователь" };
    }
    return {};
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { ...headers(), ...(options.headers || {}) },
    });
    if (!response.ok) {
      let message = "Не удалось связаться с сервером.";
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch (_) { /* Оставляем понятное сообщение по умолчанию. */ }
      throw new Error(message);
    }
    return response.json();
  }

  function setError(message = "") {
    elements.error.hidden = !message;
    elements.error.textContent = message;
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
  }

  function createOption(status, selected) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    option.selected = status === selected;
    return option;
  }

  function renderOrders(orders) {
    elements.orders.replaceChildren();
    elements.count.textContent = String(orders.length);

    if (orders.length === 0) {
      const template = document.querySelector("#empty-state-template");
      elements.orders.append(template.content.cloneNode(true));
      return;
    }

    for (const order of orders) {
      const status = statusClass[order.status] || "new";
      const card = document.createElement("article");
      card.className = `order-card status-${status}`;
      card.dataset.orderId = String(order.id);

      const inner = document.createElement("div");
      inner.className = "order-card-inner";

      const heading = document.createElement("div");
      heading.className = "order-heading";
      const number = document.createElement("span");
      number.className = "order-number";
      number.textContent = `№${order.id}`;
      const select = document.createElement("select");
      select.className = "status-select";
      select.setAttribute("aria-label", `Статус заказа №${order.id}`);
      for (const [name] of STATUS) select.append(createOption(name, order.status));
      select.addEventListener("change", () => saveUpdate(order.id, { status: select.value }, select));
      heading.append(number, select);
      inner.append(heading);

      if (order.forwarded_from) {
        const source = document.createElement("p");
        source.className = "source";
        source.textContent = `Переслано от: ${order.forwarded_from}`;
        inner.append(source);
      }

      const messageLabel = document.createElement("span");
      messageLabel.className = "message-label";
      messageLabel.textContent = "Текст заказа";
      const message = document.createElement("p");
      message.className = "message-text";
      message.textContent = order.message_text;
      inner.append(messageLabel, message);

      const commentLabel = document.createElement("label");
      commentLabel.className = "comment-label";
      commentLabel.textContent = "Комментарий";
      const textarea = document.createElement("textarea");
      textarea.className = "comment-field";
      textarea.maxLength = 2000;
      textarea.value = order.comment || "";
      textarea.placeholder = "Например: позвонить за час, адрес уточнить…";
      textarea.setAttribute("aria-label", `Комментарий к заказу №${order.id}`);
      inner.append(commentLabel, textarea);

      const footer = document.createElement("div");
      footer.className = "card-footer";
      const save = document.createElement("button");
      save.className = "save-button";
      save.type = "button";
      save.textContent = "Сохранить комментарий";
      save.addEventListener("click", () => saveUpdate(order.id, { comment: textarea.value }, save));
      const meta = document.createElement("p");
      meta.className = "meta";
      meta.textContent = order.updated_by_name
        ? `Изменил(а): ${order.updated_by_name}\n${formatDate(order.updated_at)}`
        : `Добавлен: ${formatDate(order.created_at)}`;
      footer.append(save, meta);
      inner.append(footer);
      card.append(inner);
      elements.orders.append(card);
    }
  }

  async function saveUpdate(orderId, data, control) {
    control.disabled = true;
    setError();
    try {
      await request(`/api/orders/${orderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      tg?.HapticFeedback?.notificationOccurred("success");
      await loadOrders();
    } catch (error) {
      tg?.HapticFeedback?.notificationOccurred("error");
      setError(error.message);
      control.disabled = false;
    }
  }

  async function loadOrders() {
    if (isLoading || document.activeElement?.classList?.contains("comment-field")) return;
    isLoading = true;
    elements.refresh.disabled = true;
    try {
      const orders = await request("/api/orders");
      renderOrders(orders);
      setError();
      elements.sync.textContent = `Обновлено ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
    } catch (error) {
      setError(error.message);
      elements.sync.textContent = "Нет связи с базой";
    } finally {
      isLoading = false;
      elements.refresh.disabled = false;
    }
  }

  elements.refresh.addEventListener("click", loadOrders);
  loadOrders();
  window.setInterval(loadOrders, REFRESH_INTERVAL_MS);
})();

