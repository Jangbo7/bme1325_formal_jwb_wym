export function createQueueRuntime() {
  const state = {
    queues: [],
    playerTicket: null,
  };

  function syncFromApi(queues, playerId = "P-self") {
    state.queues = Array.isArray(queues) ? queues : [];
    state.playerTicket = null;
    for (const queue of state.queues) {
      const allTickets = [...(queue.waiting || []), ...(queue.called ? [queue.called] : [])];
      const playerTicket = allTickets.find((ticket) => ticket.patient_id === playerId);
      if (playerTicket) {
        state.playerTicket = playerTicket;
        break;
      }
    }
  }

  function draw(ctx, canvas) {
    const panelWidth = 320;
    const panelHeight = 236;
    const panelX = canvas.width - panelWidth - 16;
    const panelY = canvas.height - panelHeight - 16;

    ctx.fillStyle = "rgba(14, 16, 28, 0.9)";
    ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
    ctx.strokeStyle = "rgba(125, 233, 255, 0.74)";
    ctx.lineWidth = 2;
    ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

    ctx.fillStyle = "#c9f4ff";
    ctx.font = "bold 14px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText("Queue Board", panelX + panelWidth / 2, panelY + 22);

    let y = panelY + 50;
    for (const queue of state.queues) {
      const isPlayerDept = state.playerTicket?.department_id === queue.department_id;
      if (isPlayerDept) {
        ctx.fillStyle = "rgba(132, 255, 201, 0.14)";
        ctx.fillRect(panelX + 6, y - 14, panelWidth - 12, 22);
      }
      ctx.fillStyle = "#f0ecff";
      ctx.font = "12px 'Segoe UI'";
      ctx.textAlign = "left";
      ctx.fillText(`${isPlayerDept ? "* " : ""}${queue.department_name}`, panelX + 12, y);

      ctx.fillStyle = "#8ef0be";
      ctx.textAlign = "right";
      ctx.fillText(`Waiting ${(queue.waiting || []).length}`, panelX + panelWidth - 108, y);

      ctx.fillStyle = "#ffe99c";
      ctx.fillText(`Called ${queue.called?.number ?? "-"}`, panelX + panelWidth - 12, y);
      y += 28;
    }

    ctx.textAlign = "left";
    ctx.font = "11px 'Segoe UI'";
    ctx.fillStyle = state.playerTicket ? "#cfd8ff" : "#9fb0c0";
    if (state.playerTicket) {
      const queue = state.queues.find((item) => item.department_id === state.playerTicket.department_id);
      const ahead = Math.max(
        0,
        (queue?.waiting || []).findIndex((item) => item.id === state.playerTicket.id)
      );
      const footerText =
        state.playerTicket.status === "called"
          ? `Your ticket ${state.playerTicket.number}: called`
          : `Ticket ${state.playerTicket.number} | ${state.playerTicket.department_name} | Ahead ${ahead}`;
      ctx.fillText(footerText, panelX + 12, panelY + panelHeight - 26);
    } else {
      ctx.fillText("Not queued yet", panelX + 12, panelY + panelHeight - 26);
    }
  }

  return {
    state,
    syncFromApi,
    draw,
  };
}
