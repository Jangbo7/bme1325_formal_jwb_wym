export function createEventSubscriber({ baseUrl, onEvent, onStatusChange }) {
  let source = null;
  let reconnectTimer = null;
  let closed = false;

  function emitStatus(status, error = "") {
    if (typeof onStatusChange === "function") {
      onStatusChange({ status, error });
    }
  }

  function clearReconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function scheduleReconnect() {
    if (closed) return;
    clearReconnect();
    reconnectTimer = setTimeout(() => {
      connect();
    }, 2000);
  }

  function handlePayload(raw) {
    if (!raw) return;
    try {
      const envelope = JSON.parse(raw);
      if (typeof onEvent === "function") {
        onEvent(envelope);
      }
    } catch (error) {
      emitStatus("parse_error", error?.message || "invalid event payload");
    }
  }

  function connect() {
    if (closed) return;
    clearReconnect();
    if (source) {
      source.close();
      source = null;
    }
    emitStatus("connecting");
    source = new EventSource(`${baseUrl}/api/v1/events/stream`);
    source.onopen = () => emitStatus("connected");
    source.onerror = () => {
      emitStatus("disconnected", "event stream disconnected");
      if (source) {
        source.close();
        source = null;
      }
      scheduleReconnect();
    };
    source.onmessage = (event) => {
      handlePayload(event.data);
    };
  }

  function close() {
    closed = true;
    clearReconnect();
    if (source) {
      source.close();
      source = null;
    }
    emitStatus("closed");
  }

  return { connect, close };
}
