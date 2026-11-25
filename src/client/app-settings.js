// Model settings: provider selection, effort, keys and connection tests.

const settingsDialog = byId("settings-dialog");
const settingsFields = byId("settings-fields");
const settingsKey = byId("settings-key");
const settingsMessage = byId("settings-message");
const settingsProvider = byId("settings-provider");
const settingsModel = byId("settings-model");
const settingsAddress = byId("settings-address");
const settingsEffort = byId("settings-effort");
const quickModel = byId("quick-model");
const quickEffort = byId("quick-effort");
const modelMenuStatus = byId("model-menu-status");
const effortLabels = { low: "低", medium: "中", high: "高", max: "最高" };
const shortProvider = { deepseek: "DeepSeek", openai: "GPT", anthropic: "Claude", gemini: "Gemini", compatible: "自定义" };
const deepseekModels = new Map([["deepseek-flash", "Flash"], ["deepseek-v4-pro", "V4 Pro"]]);

function option(value, label) {
  const node = element("option", "", label);
  node.value = value;
  return node;
}

function profileFor(id) {
  return currentModelSettings?.profiles.find((profile) => profile.id === id);
}

function effortOptions(select, profile) {
  select.replaceChildren(...(profile?.efforts || []).map((effort) => option(
    effort, effort === "none" ? (profile.id === "deepseek" ? "关闭" : "默认") : effortLabels[effort],
  )));
  select.value = profile?.effort || "";
}

function quickModelOption(profile, model) {
  const deepseekShort = deepseekModels.get(model);
  const label = profile.id === "deepseek" && deepseekShort ? "DeepSeek " + deepseekShort : (model || profile.label);
  const id = `${profile.id}:${model}`;
  const node = option(id, label);
  node.dataset.provider = profile.id;
  node.dataset.model = model;
  node.dataset.shortLabel = profile.id === "deepseek" && deepseekShort ? deepseekShort : shortProvider[profile.id];
  return node;
}

function paintModelSelection(settings) {
  currentModelSettings = settings;
  if (settings) modelConfigured = settings.enabled;
  const profile = profileFor(settings?.active);
  const local = option("local", "本地知识库");
  local.dataset.shortLabel = "本地";
  quickModel.replaceChildren(local, ...(settings?.profiles || []).flatMap((row) =>
    [...new Set([row.model, ...row.choices])].map((model) => quickModelOption(row, model)),
  ));
  quickModel.value = profile ? `${profile.id}:${profile.model}` : "local";
  effortOptions(quickEffort, profile);
  const selected = quickModel.selectedOptions[0];
  const label = !settings && modelConfigured ? "模型服务" : selected.textContent;
  const effort = profile?.effort === "none" && profile.id !== "deepseek" ? "" : quickEffort.selectedOptions[0]?.textContent;
  byId("active-model").textContent = label;
  byId("active-model-short").textContent = selected.dataset.shortLabel || label;
  byId("active-effort").textContent = effort || "";
  byId("active-effort").hidden = !effort;
  byId("quick-effort-field").hidden = !profile || profile.efforts.length < 2;
  const title = effort ? label + " · " + effort : label;
  byId("model-heading").title = title;
  byId("model-heading").setAttribute("aria-label", "选择模型：" + title);
}

async function updateModelChoice(payload) {
  modelPending = true;
  modelMenuStatus.textContent = "";
  updateControls();
  try {
    paintModelSelection(await request(settingsEndpoint, payload));
  } catch (error) {
    paintModelSelection(currentModelSettings);
    modelMenuStatus.textContent = error.message;
  } finally {
    modelPending = false;
    updateControls();
  }
}

function changeQuickModel(event) {
  if (!currentModelSettings || busy || modelPending) return;
  const { provider, model } = quickModel.selectedOptions[0].dataset;
  const profile = profileFor(provider);
  if (profile && !profile.has_key) {
    paintModelSelection(currentModelSettings);
    showModelSettings({ provider, model });
    return;
  }
  const payload = { action: "select", provider: provider || "local" };
  if (profile) {
    payload.model = model;
    payload.effort = event.target === quickEffort ? quickEffort.value : profile.effort;
  }
  updateModelChoice(payload);
}

function modelSettingsMessage(message, error = false) {
  settingsMessage.textContent = message;
  settingsMessage.dataset.kind = error ? "error" : "status";
}

function paintSettings(profile, model = profile.model) {
  const custom = profile.id === "compatible";
  settingsProvider.value = profile.id;
  settingsModel.value = model;
  byId("settings-model-list").replaceChildren(...profile.choices.map((choice) => option(choice, choice)));
  byId("settings-address-field").hidden = !custom;
  settingsAddress.value = custom ? profile.base_url : "";
  effortOptions(settingsEffort, profile);
  byId("settings-effort-field").hidden = profile.efforts.length < 2;
  byId("settings-clear").hidden = !profile.has_key;
  settingsKey.value = "";
  settingsKey.placeholder = profile.has_key ? "已配置，留空沿用当前密钥" : "粘贴你的 API Key";
  byId("settings-key-note").textContent = profile.using_environment_key
    ? "此供应商的密钥来自本机环境变量"
    : "网页填写的密钥和设置只保留到本地服务重启";
}

async function modelSettingsAction(action, requested) {
  settingsFields.disabled = true;
  modelSettingsMessage(action === "test" ? "正在验证连接…" : "");
  try {
    if (action === "load") {
      const settings = await request(settingsEndpoint);
      paintModelSelection(settings);
      updateControls();
      settingsProvider.replaceChildren(...settings.profiles.map((row) => option(row.id, row.label)));
      const profile = profileFor(requested?.provider || settings.active) || settings.profiles[0];
      paintSettings(profile, requested?.model || profile.model);
    } else {
      const clearing = action === "clear";
      const payload = {
        action: clearing ? "clear" : "save",
        provider: settingsProvider.value,
        model: settingsModel.value.trim(),
        effort: settingsEffort.value,
        key: clearing ? "" : settingsKey.value,
        base_url: settingsAddress.value.trim(),
      };
      const tested = action === "test";
      const result = await request(settingsEndpoint + (tested ? "/test" : ""), payload);
      if (tested) {
        modelSettingsMessage("连接成功，所选模型可用");
      } else {
        paintModelSelection(result);
        paintSettings(profileFor(payload.provider));
        updateControls();
        modelSettingsMessage(clearing ? "当前密钥已移除" : "设置已应用");
      }
    }
  } catch (error) {
    modelSettingsMessage(error.message, true);
  } finally {
    settingsFields.disabled = false;
    if (action === "load" && requested && settingsDialog.open) {
      (requested.provider === "compatible" && !settingsAddress.value ? settingsAddress : settingsKey).focus();
    }
  }
}

function showModelSettings(requested, trigger = modelPicker) {
  if (trigger?.open) closeToolbarPopup(trigger);
  settingsDialog.showModal();
  modelSettingsAction("load", requested);
}

byId("model-heading").addEventListener("click", (event) => {
  if (!ready || busy) event.preventDefault();
});
modelPicker.addEventListener("toggle", () => {
  if (modelPicker.open && !busy && !modelPending) updateModelChoice();
});
quickModel.addEventListener("change", changeQuickModel);
quickEffort.addEventListener("change", changeQuickModel);
byId("show-settings").addEventListener("click", () => showModelSettings());
byId("rail-settings").addEventListener("click", () => showModelSettings(undefined, null));
settingsProvider.addEventListener("change", () => {
  const profile = profileFor(settingsProvider.value);
  if (profile) paintSettings(profile);
  modelSettingsMessage("");
});
byId("settings-close").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("close", () => { settingsKey.value = ""; });
byId("settings-test").addEventListener("click", () => modelSettingsAction("test"));
byId("settings-clear").addEventListener("click", () => modelSettingsAction("clear"));
byId("settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  modelSettingsAction("save");
});
