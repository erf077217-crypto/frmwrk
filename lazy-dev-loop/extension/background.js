const BRIDGE = (() => {
  try {
    const stored = localStorage.getItem("BRIDGE_URL");
    if (stored) return stored;
  } catch {}
  return "http://localhost:7777";
})();
const CHATGPT_ORIGIN = "https://chatgpt.com";

// ---------------------------------------------------------------------------
// Context menu — opens side panel synchronously during the user gesture,
//                 stores the prompt for the side panel to pick up.
//                 NO async/await before sidePanel.open().
// ---------------------------------------------------------------------------
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "send-to-opencode",
    title: "Send To OpenCode",
    contexts: ["selection"],
  });
  console.log("[LazyDev] context menu created");
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "send-to-opencode" || !info.selectionText) return;

  const prompt = info.selectionText;

  console.log("[LazyDev] context menu clicked", {
    tabId: tab.id,
    windowId: tab.windowId,
    promptPreview: prompt.substring(0, 60),
  });

  // 1. Store prompt synchronously (gesture-safe)
  chrome.storage.session.set({
    pendingPrompt: prompt,
    panelState: "pending",
  });

  // 2. Open side panel synchronously — still inside the user gesture.
  //    Chrome permits sidePanel.open() here because no await has yielded
  //    to the event loop yet.
  chrome.sidePanel.open({ tabId: tab.id }).catch((err) => {
    console.error("[LazyDev] sidePanel.open failed (context menu):", err);
  });

  console.log("[LazyDev] side panel open requested");
});

// ---------------------------------------------------------------------------
// Action icon click — also opens the side panel (user gesture via toolbar)
// ---------------------------------------------------------------------------
chrome.action.onClicked.addListener((tab) => {
  console.log("[LazyDev] action icon clicked", { tabId: tab.id, windowId: tab.windowId });
  chrome.sidePanel.open({ windowId: tab.windowId }).catch((err) => {
    console.error("[LazyDev] sidePanel.open failed (action):", err);
  });
});

// ---------------------------------------------------------------------------
// Message handling (no sidePanel.open() calls — all async-safe)
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "insertIntoChatGPT") {
    handleInsert(request, sendResponse);
    return true;
  }
  if (request.action === "pingChatGPT") {
    handlePing(sendResponse);
    return true;
  }
  if (request.action === "getTabInfo") {
    handleGetTabInfo(sendResponse);
    return true;
  }
});

async function handleInsert(request, sendResponse) {
  const tab = await findChatGPTTab();
  if (!tab) {
    sendResponse({ success: false, error: "no_chatgpt_tab", detail: "Open chatgpt.com first." });
    return;
  }

  const ready = await ensureContentScript(tab.id);
  if (!ready) {
    sendResponse({ success: false, error: "content_script_missing", detail: "Could not inject content script. Reload chatgpt.com and try again." });
    return;
  }

  try {
    const result = await chrome.tabs.sendMessage(tab.id, {
      action: "insertText",
      text: request.text,
    });
    if (result && result.success) {
      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: "insertion_failed", detail: (result && result.error) || "Content script reported failure." });
    }
  } catch (err) {
    sendResponse({ success: false, error: "unknown", detail: `Failed to reach content script: ${err.message}` });
  }
}

async function handlePing(sendResponse) {
  const tab = await findChatGPTTab();
  if (!tab) {
    sendResponse({ success: false, error: "no_chatgpt_tab", detail: "No ChatGPT tab found." });
    return;
  }

  try {
    await ensureContentScript(tab.id);
    const result = await chrome.tabs.sendMessage(tab.id, { type: "PING" });
    sendResponse({ success: true, tabId: tab.id, contentType: "content-script", detail: result });
  } catch (err) {
    sendResponse({ success: false, error: "ping_failed", detail: err.message, tabId: tab.id });
  }
}

async function handleGetTabInfo(sendResponse) {
  const tab = await findChatGPTTab();
  if (!tab) {
    const allTabs = await chrome.tabs.query({ active: true, currentWindow: true });
    sendResponse({
      activeTabExists: allTabs.length > 0,
      activeTab: allTabs[0] ? { id: allTabs[0].id, url: allTabs[0].url, title: allTabs[0].title } : null,
      chatgptTab: null,
    });
    return;
  }
  sendResponse({ chatgptTab: { id: tab.id, url: tab.url, title: tab.title } });
}

async function findChatGPTTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true, url: `${CHATGPT_ORIGIN}/*` });
  return tabs.length > 0 ? tabs[0] : null;
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "PING" });
    return true;
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content_script.js"] });
      await new Promise((r) => setTimeout(r, 150));
      return true;
    } catch {
      return false;
    }
  }
}
