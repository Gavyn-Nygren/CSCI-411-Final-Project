const authView = document.querySelector("#auth-view");
const appView = document.querySelector("#app-view");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authSubmit = document.querySelector("#auth-submit");
const authAlt = document.querySelector("#auth-alt");
const authMessage = document.querySelector("#auth-message");
const appMessage = document.querySelector("#app-message");
let setupRequired = false;
let authMode = "login";
let customers = [];

function addCustomerServiceRow(service = {}) {
  const schedule = document.querySelector("#customer-services");
  const row = document.createElement("div");
  row.className = "schedule-row";

  const serviceLabel = document.createElement("label");
  setText(serviceLabel, "Service Type");
  const serviceInput = document.createElement("input");
  serviceInput.name = "service_type";
  serviceInput.maxLength = 50;
  serviceInput.required = true;
  serviceInput.value = service.service_type || "";
  serviceLabel.append(serviceInput);

  const frequencyLabel = document.createElement("label");
  setText(frequencyLabel, "Frequency");
  const frequencyInput = document.createElement("input");
  frequencyInput.name = "frequency";
  frequencyInput.maxLength = 50;
  frequencyInput.required = true;
  frequencyInput.value = service.frequency || "";
  frequencyLabel.append(frequencyInput);

  const remove = document.createElement("button");
  remove.className = "secondary icon-action";
  remove.type = "button";
  setText(remove, "Remove");
  remove.addEventListener("click", () => {
    if (schedule.children.length > 1) {
      row.remove();
    }
  });

  row.append(serviceLabel, frequencyLabel, remove);
  schedule.append(row);
}

function setCustomerSchedule(services = [{}]) {
  const schedule = document.querySelector("#customer-services");
  schedule.replaceChildren();
  services.forEach((service) => addCustomerServiceRow(service));
}

function setCustomerFormMode(customer = null) {
  const form = document.querySelector("#customer-form");
  const title = document.querySelector("#customer-form-title");
  const cancel = document.querySelector("#customer-cancel-edit");

  if (!customer) {
    form.reset();
    form.elements.id.value = "";
    setCustomerSchedule();
    setText(title, "Add Customer");
    cancel.classList.add("hidden");
    return;
  }

  Object.entries(customer).forEach(([key, value]) => {
    if (form.elements[key] && key !== "services") form.elements[key].value = value ?? "";
  });
  setCustomerSchedule(customer.services?.length ? customer.services : [{ service_type: customer.service_type, frequency: customer.frequency }]);
  setText(title, `Edit ${customer.name}`);
  cancel.classList.remove("hidden");
}

function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(data?.detail || "Request failed.");
  }
  return data;
}

function formDataObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function customerPayload(form) {
  const payload = formDataObject(form);
  const services = [...document.querySelectorAll("#customer-services .schedule-row")].map((row) => ({
    service_type: row.querySelector("[name='service_type']").value,
    frequency: row.querySelector("[name='frequency']").value,
  }));
  delete payload.service_type;
  delete payload.frequency;
  payload.services = services;
  return payload;
}

function showAuth(isSetup, mode = isSetup ? "setup" : "login") {
  setupRequired = isSetup;
  authMode = mode;
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
  authMessage.textContent = "";
  authForm.reset();
  setText(authTitle, authMode === "login" ? "Secure business operations" : isSetup ? "Create owner account" : "Create account");
  setText(authSubmit, authMode === "login" ? "Log in" : "Create Account");
  setText(authAlt, authMode === "login" ? "Create account" : "Back to login");
  authAlt.classList.toggle("hidden", isSetup);
  authForm.password.autocomplete = authMode === "login" ? "current-password" : "new-password";
}

function showApp(username) {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  setText(document.querySelector("#current-user"), username);
}

function makeItem(lines, action) {
  const item = document.createElement("div");
  item.className = "item";
  lines.forEach((line, index) => {
    const node = document.createElement(index === 0 ? "strong" : "span");
    setText(node, line);
    item.append(node);
  });
  if (action) item.append(action);
  return item;
}

function formatTimeRange(startTime, durationMinutes) {
  const [hours, minutes] = String(startTime || "00:00").split(":").map(Number);
  const start = new Date(2000, 0, 1, hours || 0, minutes || 0);
  const end = new Date(start.getTime() + Number(durationMinutes || 0) * 60000);
  return `${formatClock(start)}-${formatClock(end)}`;
}

function formatClock(date) {
  const hours = date.getHours();
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const suffix = hours >= 12 ? "pm" : "am";
  const hour = hours % 12 || 12;
  return `${hour}:${minutes}${suffix}`;
}

function activateTab(tabId) {
  document.querySelectorAll(".tabs button").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabId));
  document.querySelectorAll(".tab-page").forEach((page) => page.classList.toggle("active", page.id === tabId));
}

function selectedCustomer(form) {
  const customerId = form.elements.customer_id?.value;
  return customers.find((customer) => String(customer.id) === String(customerId));
}

function setServiceFormMode(service = null) {
  const form = document.querySelector("#service-form");
  const title = document.querySelector("#service-form-title");
  const submit = document.querySelector("#service-submit");
  const cancel = document.querySelector("#service-cancel-edit");

  if (!service) {
    form.reset();
    form.elements.id.value = "";
    setText(title, "Add Service");
    setText(submit, "Add Service");
    cancel.classList.add("hidden");
    syncServiceTypeToCustomer();
    return;
  }

  form.elements.id.value = service.id;
  form.elements.customer_id.value = service.customer_id;
  syncServiceTypeToCustomer();
  form.elements.service_type.value = service.service_type;
  form.elements.job_date.value = service.job_date;
  form.elements.service_time.value = service.service_time;
  form.elements.cost.value = service.cost;
  form.elements.duration_minutes.value = service.duration_minutes;
  form.elements.notes.value = service.notes || "";
  setText(title, `Edit ${service.service_type}`);
  setText(submit, "Save Service");
  cancel.classList.remove("hidden");
}

function syncServiceTypeToCustomer() {
  const form = document.querySelector("#service-form");
  const customer = selectedCustomer(form);
  const select = form.elements.service_type;
  const current = select.value;
  select.replaceChildren();
  (customer?.services || []).forEach((service) => {
    select.append(new Option(`${service.service_type} (${service.frequency})`, service.service_type));
  });
  select.value = current;
  if (!select.value && select.options.length > 0) {
    select.selectedIndex = 0;
  }
}

function fillCustomerSelects() {
  document.querySelectorAll("select[name='customer_id']").forEach((select) => {
    const current = select.value;
    const optional = Boolean(select.closest("#financial-form"));
    select.replaceChildren();
    if (optional) {
      select.append(new Option("No customer", ""));
    }
    customers.forEach((customer) => select.append(new Option(customer.name, customer.id)));
    select.value = current;
    if (!select.value && !optional && select.options.length > 0) {
      select.selectedIndex = 0;
    }
  });
  syncServiceTypeToCustomer();
}

async function loadCustomers(search = "") {
  const data = await api(`/api/customers?search=${encodeURIComponent(search)}&page_size=100`);
  customers = data.items;
  fillCustomerSelects();
  const list = document.querySelector("#customer-list");
  const count = document.querySelector("#customer-count");
  list.replaceChildren();
  setText(count, `${customers.length} customer${customers.length === 1 ? "" : "s"}`);
  if (customers.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    setText(empty, search ? "No customers match that search." : "No customers added yet.");
    list.append(empty);
    return;
  }
  customers.forEach((customer) => {
    const actions = document.createElement("div");
    actions.className = "item-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    setText(edit, "Edit");
    edit.addEventListener("click", () => setCustomerFormMode(customer));
    const deleteButton = document.createElement("button");
    deleteButton.className = "danger";
    deleteButton.type = "button";
    setText(deleteButton, "Delete");
    deleteButton.addEventListener("click", async () => {
      if (!confirm(`Delete ${customer.name} and their related records?`)) return;
      try {
        await api(`/api/customers/${customer.id}`, { method: "DELETE" });
        await refreshAll();
      } catch (error) {
        setText(appMessage, error.message);
      }
    });
    actions.append(edit, deleteButton);
    list.append(
      makeItem(
        [
          customer.name,
          `${customer.email} | ${customer.phone}`,
          `${customer.address}`,
          (customer.services || []).map((service) => `${service.service_type} | ${service.frequency}`).join("; "),
          customer.notes,
        ],
        actions,
      ),
    );
  });
}

async function loadServices() {
  const data = await api("/api/services");
  const list = document.querySelector("#service-list");
  list.replaceChildren();
  data.items.forEach((service) => {
    const timeRange = formatTimeRange(service.service_time, service.duration_minutes);
    const actions = document.createElement("div");
    actions.className = "item-actions service-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    setText(edit, "Edit");
    edit.addEventListener("click", () => setServiceFormMode(service));
    const deleteButton = document.createElement("button");
    deleteButton.className = "danger";
    deleteButton.type = "button";
    setText(deleteButton, "Delete");
    deleteButton.addEventListener("click", async () => {
      if (!confirm(`Delete ${service.service_type} for ${service.customer_name} on ${service.job_date}?`)) return;
      try {
        await api(`/api/services/${service.id}`, { method: "DELETE" });
        if (document.querySelector("#service-form").elements.id.value === String(service.id)) {
          setServiceFormMode();
        }
        await loadServices();
      } catch (error) {
        setText(appMessage, error.message);
      }
    });
    const complete = document.createElement("button");
    complete.className = "complete-action";
    complete.type = "button";
    setText(complete, service.completed ? "Completed" : "Complete");
    complete.disabled = Boolean(service.completed);
    complete.addEventListener("click", async () => {
      try {
        await api(`/api/services/${service.id}/complete`, { method: "POST" });
        await Promise.all([loadServices(), loadFinancials()]);
        const serviceDate = new Date(`${service.job_date}T00:00:00`);
        document.querySelector("#summary-form [name='year']").value = serviceDate.getFullYear();
        document.querySelector("#summary-form [name='month']").value = serviceDate.getMonth() + 1;
        document.querySelector("#summary-form").requestSubmit();
        activateTab("financials");
      } catch (error) {
        setText(appMessage, error.message);
      }
    });
    actions.append(edit, deleteButton, complete);
    list.append(
      makeItem(
        [
          `${service.service_type} on ${service.job_date}`,
          `${timeRange} | ${service.customer_name} | $${service.cost} | ${service.duration_minutes} minutes`,
          service.customer_address,
          service.notes,
        ],
        actions,
      ),
    );
  });
}

async function loadContracts() {
  const data = await api("/api/contracts");
  const list = document.querySelector("#contract-list");
  list.replaceChildren();
  data.items.forEach((contract) => {
    const actions = document.createElement("div");
    actions.className = "item-actions";
    const view = document.createElement("button");
    view.type = "button";
    setText(view, "View");
    view.addEventListener("click", () => showContractPreview(contract));
    const download = document.createElement("a");
    download.href = `/api/contracts/${contract.id}/download`;
    setText(download, "Download");
    const deleteButton = document.createElement("button");
    deleteButton.className = "danger";
    deleteButton.type = "button";
    setText(deleteButton, "Delete");
    deleteButton.addEventListener("click", async () => {
      if (!confirm(`Delete ${contract.original_filename} for ${contract.customer_name}?`)) return;
      try {
        await api(`/api/contracts/${contract.id}`, { method: "DELETE" });
        const frame = document.querySelector("#contract-preview");
        if (frame.src.includes(`/api/contracts/${contract.id}/view`)) {
          document.querySelector("#contract-preview-close").click();
        }
        await loadContracts();
      } catch (error) {
        setText(appMessage, error.message);
      }
    });
    actions.append(view, download, deleteButton);
    list.append(
      makeItem(
        [
          contract.customer_name,
          contract.original_filename,
        ],
        actions,
      ),
    );
  });
}

function showContractPreview(contract) {
  const panel = document.querySelector("#contract-preview-panel");
  const frame = document.querySelector("#contract-preview");
  setText(document.querySelector("#contract-preview-title"), `${contract.customer_name} - ${contract.original_filename}`);
  frame.src = `/api/contracts/${contract.id}/view`;
  panel.classList.remove("hidden");
}

async function loadFinancials() {
  const data = await api("/api/financials");
  const list = document.querySelector("#financial-list");
  list.replaceChildren();
  data.items.forEach((entry) => {
    list.append(
      makeItem([
        `${entry.entry_type}: $${entry.amount} on ${entry.entry_date}`,
        `${entry.category} | ${entry.service_type}`,
        entry.notes,
      ]),
    );
  });
}

async function runMonthlySummary(year, month) {
  const summary = await api(`/api/financials/summary?year=${year}&month=${month}`);
  const node = document.querySelector("#summary");
  node.replaceChildren();
  [`Income: $${summary.income}`, `Expenses: $${summary.expenses}`, `Net: $${summary.net}`].forEach((line) => {
    const div = document.createElement("div");
    setText(div, line);
    node.append(div);
  });
}

async function refreshAll() {
  await loadCustomers(document.querySelector("#customer-search").value);
  await Promise.all([loadServices(), loadContracts(), loadFinancials()]);
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.textContent = "";
  const payload = formDataObject(authForm);
  const path = authMode === "setup" ? "/api/setup" : authMode === "register" ? "/api/register" : "/api/login";
  try {
    const data = await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showApp(data.username);
    await refreshAll();
  } catch (error) {
    setText(authMessage, error.message);
  }
});

authAlt.addEventListener("click", () => {
  showAuth(false, authMode === "login" ? "register" : "login");
});

document.querySelector("#logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  showAuth(false);
});

document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

document.querySelector("#customer-search").addEventListener("input", (event) => {
  loadCustomers(event.target.value).catch((error) => setText(appMessage, error.message));
});

document.querySelector("#customer-cancel-edit").addEventListener("click", () => {
  setCustomerFormMode();
});

document.querySelector("#add-customer-service").addEventListener("click", () => {
  addCustomerServiceRow();
});

document.querySelector("#service-form [name='customer_id']").addEventListener("change", () => {
  syncServiceTypeToCustomer();
});

document.querySelector("#service-cancel-edit").addEventListener("click", () => {
  setServiceFormMode();
});

document.querySelector("#customer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  appMessage.textContent = "";
  const form = event.currentTarget;
  const payload = customerPayload(form);
  const id = payload.id;
  delete payload.id;
  try {
    await api(id ? `/api/customers/${id}` : "/api/customers", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    setCustomerFormMode();
    await refreshAll();
  } catch (error) {
    setText(appMessage, error.message);
  }
});

document.querySelector("#service-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formDataObject(form);
  const id = payload.id;
  delete payload.id;
  try {
    syncServiceTypeToCustomer();
    await api(id ? `/api/services/${id}` : "/api/services", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    setServiceFormMode();
    await loadServices();
  } catch (error) {
    setText(appMessage, error.message);
  }
});

document.querySelector("#contract-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api("/api/contracts", { method: "POST", body: new FormData(form) });
    form.reset();
    await loadContracts();
  } catch (error) {
    setText(appMessage, error.message);
  }
});

document.querySelector("#contract-preview-close").addEventListener("click", () => {
  const panel = document.querySelector("#contract-preview-panel");
  const frame = document.querySelector("#contract-preview");
  frame.removeAttribute("src");
  panel.classList.add("hidden");
});

document.querySelector("#financial-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formDataObject(form);
  try {
    await api("/api/financials", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await loadFinancials();
    const entryDate = new Date(`${payload.entry_date}T00:00:00`);
    const year = entryDate.getFullYear();
    const month = entryDate.getMonth() + 1;
    document.querySelector("#summary-form [name='year']").value = year;
    document.querySelector("#summary-form [name='month']").value = month;
    await runMonthlySummary(year, month);
  } catch (error) {
    setText(appMessage, error.message);
  }
});

document.querySelector("#summary-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formDataObject(event.currentTarget);
  try {
    await runMonthlySummary(payload.year, payload.month);
  } catch (error) {
    setText(appMessage, error.message);
  }
});

async function init() {
  setCustomerSchedule();
  const today = new Date();
  document.querySelector("#summary-form [name='year']").value = today.getFullYear();
  document.querySelector("#summary-form [name='month']").value = today.getMonth() + 1;
  try {
    const me = await api("/api/me");
    showApp(me.username);
    await refreshAll();
  } catch {
    const setup = await api("/api/setup-required");
    showAuth(setup.setup_required);
  }
}

init();
