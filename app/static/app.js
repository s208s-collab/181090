(() => {
  "use strict";

  const tg = window.Telegram?.WebApp;
  const isDevBrowser = new URLSearchParams(window.location.search).get("dev") === "1";
  const REFRESH_INTERVAL_MS = 4000;
  let isLoading = false;
  let allOrders = [];
  let lastOrdersFingerprint = "";

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
  // Номера в российских форматах: +7 999 123-45-67, 8 (999) 123-45-67 и т.п.
  const PHONE_PATTERN = /(?:(?:\+7|8|7)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}|\b\d{3}[\s(.-]*\d{3}[\s).-]*\d{2}[\s.-]*\d{2})/g;

  const elements = {
    orders: document.querySelector("#orders"),
    count: document.querySelector("#order-count"),
    countLabel: document.querySelector("#order-count-label"),
    sync: document.querySelector("#sync-status"),
    error: document.querySelector("#app-error"),
    refresh: document.querySelector("#refresh-button"),
    statusFilter: document.querySelector("#status-filter"),
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
    if (response.status === 204) return null;
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

  function phoneMatches(text) {
    const pattern = new RegExp(PHONE_PATTERN.source, "g");
    const found = [];
    let match;

    while ((match = pattern.exec(text)) !== null) {
      const digits = match[0].replace(/\D/g, "");
      if (digits.length !== 10 && digits.length !== 11) continue;

      found.push({
        start: match.index,
        end: match.index + match[0].length,
        value: match[0],
        href: digits.length === 10 ? `tel:+7${digits}` : `tel:+7${digits.slice(1)}`,
      });
    }
    return found;
  }

  function appendMessageWithPhoneLinks(container, text, phones) {
    let cursor = 0;
    for (const phone of phones) {
      container.append(document.createTextNode(text.slice(cursor, phone.start)));
      const link = document.createElement("a");
      link.className = "phone-link";
      link.href = phone.href;
      link.textContent = phone.value;
      link.setAttribute("aria-label", `Позвонить ${phone.value}`);
      link.addEventListener("click", (event) => startPhoneCall(event, phone.href));
      container.append(link);
      cursor = phone.end;
    }
    container.append(document.createTextNode(text.slice(cursor)));
  }

  function startPhoneCall(event, phoneHref) {
    // В Telegram Mini App явно передаём tel: системе, чтобы открыть звонилку.
    event.preventDefault();
    tg?.HapticFeedback?.impactOccurred("light");
    window.location.href = phoneHref;
  }

  async function copyText(text) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.cssText = "position:fixed;opacity:0;pointer-events:none";
    document.body.append(helper);
    helper.select();
    const copied = document.execCommand("copy");
    helper.remove();
    if (!copied) throw new Error("Не удалось скопировать текст.");
  }

  function setupStatusFilter() {
    for (const [name] of STATUS) {
      elements.statusFilter.append(createOption(name, false));
    }
    elements.statusFilter.addEventListener("change", () => renderOrders(allOrders));
  }

  function visibleOrders(orders) {
    const selectedStatus = elements.statusFilter.value;
    return selectedStatus ? orders.filter((order) => order.status === selectedStatus) : orders;
  }

  function ordersFingerprint(orders) {
    // Не перерисовываем список без изменений: это сохраняет место прокрутки.
    return JSON.stringify(orders);
  }

  function renderOrders(orders) {
    const scrollTop = window.scrollY;
    elements.orders.replaceChildren();
    const visible = visibleOrders(orders);
    elements.count.textContent = String(visible.length);
    elements.countLabel.textContent = elements.statusFilter.value
      ? `из ${orders.length} заказов`
      : "всего заказов";

    if (visible.length === 0) {
      const template = document.querySelector("#empty-state-template");
      elements.orders.append(template.content.cloneNode(true));
      return;
    }

    for (const order of visible) {
      const status = statusClass[order.status] || "new";
      const displayNumber = order.order_number || String(order.id);
      const card = document.createElement("article");
      card.className = `order-card status-${status}`;
      card.dataset.orderId = String(order.id);

      const inner = document.createElement("div");
      inner.className = "order-card-inner";

      const heading = document.createElement("div");
      heading.className = "order-heading";
      const number = document.createElement("span");
      number.className = "order-number";
      number.textContent = `№${displayNumber}`;
      const select = document.createElement("select");
      select.className = "status-select";
      select.setAttribute("aria-label", `Статус заказа №${displayNumber}`);
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

      const messageHeader = document.createElement("div");
      messageHeader.className = "message-header";
      const messageLabel = document.createElement("span");
      messageLabel.className = "message-label";
      messageLabel.textContent = "Текст заказа";
      const copy = document.createElement("button");
      copy.className = "copy-button";
      copy.type = "button";
      copy.textContent = "Копировать";
      copy.addEventListener("click", async () => {
        copy.disabled = true;
        setError();
        try {
          await copyText(order.message_text);
          copy.textContent = "Скопировано ✓";
          tg?.HapticFeedback?.notificationOccurred("success");
          window.setTimeout(() => { copy.textContent = "Копировать"; copy.disabled = false; }, 1800);
        } catch (error) {
          copy.disabled = false;
          setError(error.message || "Не удалось скопировать текст.");
        }
      });
      messageHeader.append(messageLabel, copy);
      const message = document.createElement("p");
      message.className = "message-text";
      const phones = phoneMatches(order.message_text);
      appendMessageWithPhoneLinks(message, order.message_text, phones);
      inner.append(messageHeader, message);

      const uniquePhones = [...new Map(phones.map((phone) => [phone.href, phone])).values()];
      if (uniquePhones.length) {
        const callActions = document.createElement("div");
        callActions.className = "call-actions";
        for (const phone of uniquePhones) {
          const call = document.createElement("a");
          call.className = "call-button";
          call.href = phone.href;
          call.textContent = `Позвонить: ${phone.value}`;
          call.addEventListener("click", (event) => startPhoneCall(event, phone.href));
          callActions.append(call);
        }
        inner.append(callActions);
      }

      const commentLabel = document.createElement("label");
      commentLabel.className = "comment-label";
      commentLabel.textContent = "Комментарий";
      const textarea = document.createElement("textarea");
      textarea.className = "comment-field";
      textarea.maxLength = 2000;
      textarea.value = order.comment || "";
      textarea.placeholder = "Например: позвонить за час, адрес уточнить…";
      textarea.setAttribute("aria-label", `Комментарий к заказу №${displayNumber}`);
      inner.append(commentLabel, textarea);

      const footer = document.createElement("div");
      footer.className = "card-footer";
      const save = document.createElement("button");
      save.className = "save-button";
      save.type = "button";
      save.textContent = "Сохранить комментарий";
      save.addEventListener("click", () => saveUpdate(order.id, { comment: textarea.value }, save));
      const remove = document.createElement("button");
      remove.className = "delete-button";
      remove.type = "button";
      remove.textContent = "Удалить";
      remove.addEventListener("click", () => deleteOrder(order.id, displayNumber, remove));
      const actions = document.createElement("div");
      actions.className = "card-actions";
      actions.append(save, remove);
      const meta = document.createElement("p");
      meta.className = "meta";
      meta.textContent = order.updated_by_name
        ? `Изменил(а): ${order.updated_by_name}\n${formatDate(order.updated_at)}`
        : `Добавлен: ${formatDate(order.created_at)}`;
      footer.append(actions, meta);
      inner.append(footer);
      card.append(inner);
      elements.orders.append(card);
    }

    // При реальном обновлении заказа оставляем пользователя на том же месте списка.
    window.requestAnimationFrame(() => window.scrollTo({ top: scrollTop, left: 0 }));
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

  async function deleteOrder(orderId, displayNumber, control) {
    if (!window.confirm(`Удалить заказ №${displayNumber}? Это действие нельзя отменить.`)) return;

    control.disabled = true;
    setError();
    try {
      await request(`/api/orders/${orderId}`, { method: "DELETE" });
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
      const nextOrders = await request("/api/orders");
      const nextFingerprint = ordersFingerprint(nextOrders);
      allOrders = nextOrders;
      if (nextFingerprint !== lastOrdersFingerprint) {
        renderOrders(allOrders);
        lastOrdersFingerprint = nextFingerprint;
      }
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
  setupStatusFilter();
  loadOrders();
  window.setInterval(loadOrders, REFRESH_INTERVAL_MS);
})();
