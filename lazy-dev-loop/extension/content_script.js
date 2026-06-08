console.log("[LazyDev] content script loaded");

const PROMPT_SELECTORS = [
  "#prompt-textarea",
  "[contenteditable=\"true\"][role=\"textbox\"]",
  "[contenteditable=\"true\"]:not([aria-hidden=\"true\"])",
];

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log("[LazyDev] received message:", request);

  if (request.type === "PING") {
    sendResponse({ success: true, source: "content-script" });
    return;
  }

  if (request.action !== "insertText") return;

  const textbox = findPromptTextbox();
  if (!textbox) {
    sendResponse({ success: false, error: "ChatGPT textbox not found." });
    return;
  }

  try {
    insertAtCursor(textbox, request.text);
    sendResponse({ success: true });
  } catch (err) {
    sendResponse({ success: false, error: `Insertion failed: ${err.message}` });
  }

  return true;
});

function findPromptTextbox() {
  for (const sel of PROMPT_SELECTORS) {
    const el = document.querySelector(sel);
    if (el && el.isContentEditable) return el;
  }
  return null;
}

function insertAtCursor(element, text) {
  element.focus();

  const sel = window.getSelection();
  if (sel.rangeCount > 0 && element.contains(sel.anchorNode)) {
    const range = sel.getRangeAt(0);
    range.deleteContents();
    range.insertNode(document.createTextNode(text));
    range.collapse(false);
  } else {
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    range.insertNode(document.createTextNode(text));
    range.collapse(false);
  }

  sel.removeAllRanges();

  element.dispatchEvent(new InputEvent("input", { bubbles: true, cancelable: true }));
}
