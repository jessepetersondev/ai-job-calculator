/* ============================================================
   CALCULATOR — client logic
   ============================================================ */

(() => {
  const $ = (sel) => document.querySelector(sel);
  const config = window.APP_CONFIG || {};

  const occInput   = $("#occupation-input");
  const acList     = $("#autocomplete-list");
  const stateInput = $("#state-input");
  const submitBtn  = $("#calc-submit");
  const errBox     = $("#calc-error");
  const stageIn    = $("#stage-input");
  const stageOut   = $("#stage-result");

  let currentResult = null;
  let acDebounce = null;
  let acIndex = -1;
  let acItems = [];

  // ─── Error helpers ─────────────────────────────────────────
  function showError(msg) {
    errBox.textContent = msg;
    errBox.classList.add("show");
  }
  function clearError() {
    errBox.classList.remove("show");
    errBox.textContent = "";
  }

  // ─── Autocomplete ──────────────────────────────────────────
  async function loadAutocomplete(q) {
    try {
      const res = await fetch(`/api/occupations?q=${encodeURIComponent(q)}&limit=10`);
      if (!res.ok) return;
      const items = await res.json();
      renderAutocomplete(items);
    } catch (e) { /* swallow */ }
  }

  function renderAutocomplete(items) {
    acItems = items;
    acIndex = -1;
    if (!items.length) {
      acList.classList.remove("open");
      acList.innerHTML = "";
      return;
    }
    acList.innerHTML = items.map((it, i) => `
      <div class="item" data-i="${i}">
        <span>${escapeHtml(it.title)}</span>
        <span class="cat">${escapeHtml(it.category)}</span>
      </div>
    `).join("");
    acList.classList.add("open");
    [...acList.querySelectorAll(".item")].forEach((el) => {
      el.addEventListener("mousedown", (e) => {
        // mousedown (not click) so the blur doesn't fire first
        e.preventDefault();
        selectAcItem(parseInt(el.dataset.i, 10));
      });
    });
  }

  function selectAcItem(i) {
    if (i < 0 || i >= acItems.length) return;
    occInput.value = acItems[i].title;
    acList.classList.remove("open");
    acIndex = -1;
    stateInput.focus();
  }

  occInput.addEventListener("input", (e) => {
    clearError();
    const q = e.target.value.trim();
    clearTimeout(acDebounce);
    if (q.length < 2) {
      acList.classList.remove("open");
      return;
    }
    acDebounce = setTimeout(() => loadAutocomplete(q), 150);
  });

  occInput.addEventListener("focus", () => {
    if (occInput.value.length >= 2) loadAutocomplete(occInput.value.trim());
  });

  occInput.addEventListener("blur", () => {
    setTimeout(() => acList.classList.remove("open"), 120);
  });

  occInput.addEventListener("keydown", (e) => {
    const items = acList.querySelectorAll(".item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      acIndex = Math.min(acIndex + 1, items.length - 1);
      updateAcHighlight(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      acIndex = Math.max(acIndex - 1, -1);
      updateAcHighlight(items);
    } else if (e.key === "Enter") {
      if (acIndex >= 0) {
        e.preventDefault();
        selectAcItem(acIndex);
      } else if (occInput.value.trim() && stateInput.value) {
        // Enter to submit if everything is filled
        e.preventDefault();
        runCalculate();
      }
    } else if (e.key === "Escape") {
      acList.classList.remove("open");
    }
  });

  function updateAcHighlight(items) {
    items.forEach((el, i) => el.classList.toggle("active", i === acIndex));
    if (acIndex >= 0 && items[acIndex]) {
      items[acIndex].scrollIntoView({ block: "nearest" });
    }
  }

  // ─── Submit ────────────────────────────────────────────────
  submitBtn.addEventListener("click", runCalculate);

  async function runCalculate() {
    clearError();
    const occ = occInput.value.trim();
    const state = stateInput.value;
    if (!occ) {
      showError("Please enter your job title.");
      occInput.focus();
      return;
    }
    if (!state) {
      showError("Please select your state.");
      stateInput.focus();
      return;
    }

    const label = submitBtn.querySelector(".btn-label");
    const arrow = submitBtn.querySelector(".arrow");
    label.innerHTML = '<span class="spinner"></span> Calculating';
    arrow.style.display = "none";
    submitBtn.disabled = true;

    try {
      const res = await fetch("/api/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ occupation: occ, state }),
      });
      const data = await res.json();
      if (!res.ok) {
        showError(data.error || "Couldn't find that occupation. Try a more common title.");
        return;
      }
      currentResult = data;
      renderResult(data);
    } catch (err) {
      showError("Network error — please try again.");
      console.error(err);
    } finally {
      label.textContent = "Show my score";
      arrow.style.display = "";
      submitBtn.disabled = false;
    }
  }

  // ─── Result rendering ──────────────────────────────────────
  function renderResult(r) {
    stageIn.style.display = "none";
    stageOut.style.display = "block";
    window.scrollTo({ top: 0, behavior: "smooth" });

    $("#r-badge").textContent = badgeText(r.severity);
    $("#r-badge").className = "badge badge-" + r.severity;

    $("#r-occ").textContent = r.occupation_title;
    $("#r-meta").innerHTML = `
      ${escapeHtml(r.state_name)} (${r.state_code}) ·
      ${escapeHtml(r.category)} ·
      ${dateStamp()}
    `;

    // Animate score count-up
    animateNum("#r-score-num", 0, r.vulnerability_pct, 900);
    $("#r-rank").textContent = r.rank;
    $("#r-total").textContent = r.total;
    $("#r-severity").textContent = r.severity_label;

    // Sparkline
    drawSparkline("#r-spark", r.trajectory);

    // Tasks preview (show first 2 of 4)
    const tasksPrev = $("#r-tasks-preview");
    const tasks = (r.at_risk_tasks || []).slice(0, 2);
    tasksPrev.innerHTML = tasks.map(t => `<li>${escapeHtml(t)}</li>`).join("") +
      `<li style="color: var(--bone-4); font-style: italic;">+ ${Math.max(0, (r.at_risk_tasks || []).length - 2)} more in the full report</li>`;

    // Adjacent (show first 1)
    const adjPrev = $("#r-adj-preview");
    const adj = (r.adjacent_safer || []).slice(0, 1);
    adjPrev.innerHTML = adj.map(a => `<li>${escapeHtml(a)}</li>`).join("") +
      `<li style="color: var(--bone-4); font-style: italic;">+ ${Math.max(0, (r.adjacent_safer || []).length - 1)} more in the full report</li>`;
  }

  function badgeText(sev) {
    return {
      critical: "ACUTE",
      high:     "ELEVATED",
      moderate: "MODERATE",
      low:      "LOW",
      minimal:  "MINIMAL",
    }[sev] || "—";
  }

  function animateNum(sel, from, to, durMs) {
    const el = $(sel);
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / durMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const val = from + (to - from) * eased;
      el.textContent = val.toFixed(1);
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = to.toFixed(1);
    }
    requestAnimationFrame(tick);
  }

  function drawSparkline(sel, traj) {
    const svg = $(sel);
    svg.innerHTML = "";
    const W = 800, H = 180, padL = 40, padR = 20, padT = 20, padB = 32;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    const maxY = Math.max(20, Math.ceil(Math.max(...traj.map(p => p.pct)) / 10) * 10);

    // y-axis grid
    for (let i = 0; i <= 4; i++) {
      const yVal = maxY * i / 4;
      const yPx = padT + chartH * (1 - i/4);
      svg.appendChild(svgEl("line", {
        x1: padL, x2: W - padR, y1: yPx, y2: yPx,
        stroke: "rgba(244,236,216,0.06)", "stroke-width": "1"
      }));
      const t = svgEl("text", {
        x: padL - 6, y: yPx + 4, "text-anchor": "end",
        fill: "var(--bone-4)", "font-size": "10", "font-family": "JetBrains Mono"
      });
      t.textContent = Math.round(yVal) + "%";
      svg.appendChild(t);
    }

    // points
    const pts = traj.map((p, i) => {
      const x = padL + chartW * (i / (traj.length - 1));
      const y = padT + chartH * (1 - p.pct / maxY);
      return { x, y, year: p.year, pct: p.pct };
    });

    // filled area
    const areaPath = `M ${pts[0].x} ${padT + chartH} ${pts.map(p => `L ${p.x} ${p.y}`).join(" ")} L ${pts[pts.length-1].x} ${padT + chartH} Z`;
    svg.appendChild(svgEl("path", {
      d: areaPath, fill: "rgba(255,77,46,0.16)", stroke: "none"
    }));

    // line
    const linePath = `M ${pts[0].x} ${pts[0].y} ${pts.slice(1).map(p => `L ${p.x} ${p.y}`).join(" ")}`;
    svg.appendChild(svgEl("path", {
      d: linePath, fill: "none", stroke: "var(--signal)", "stroke-width": "2.5",
      "stroke-linecap": "round", "stroke-linejoin": "round"
    }));

    // dots + labels
    pts.forEach(p => {
      svg.appendChild(svgEl("circle", {
        cx: p.x, cy: p.y, r: 4, fill: "var(--signal)",
        stroke: "var(--ink-2)", "stroke-width": "2"
      }));
      const yearT = svgEl("text", {
        x: p.x, y: padT + chartH + 18, "text-anchor": "middle",
        fill: "var(--bone-3)", "font-size": "11",
        "font-family": "JetBrains Mono", "letter-spacing": "0.05em"
      });
      yearT.textContent = p.year;
      svg.appendChild(yearT);

      const pctT = svgEl("text", {
        x: p.x, y: p.y - 10, "text-anchor": "middle",
        fill: "var(--bone)", "font-size": "10",
        "font-family": "JetBrains Mono", "font-weight": "700"
      });
      pctT.textContent = p.pct + "%";
      svg.appendChild(pctT);
    });
  }

  function svgEl(name, attrs) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
  }

  // ─── Stripe checkout ───────────────────────────────────────
  const payBtn = $("#pay-btn");
  payBtn.addEventListener("click", async () => {
    const email = $("#pay-email").value.trim();
    if (!email || !email.includes("@")) {
      showError("Please enter a valid email to receive your report.");
      $("#pay-email").focus();
      $("#pay-email").scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }
    if (!currentResult) {
      showError("Calculate your score first.");
      return;
    }

    const label = payBtn.querySelector(".btn-label");
    const arrow = payBtn.querySelector(".arrow");
    label.innerHTML = '<span class="spinner"></span> Redirecting to Stripe';
    arrow.style.display = "none";
    payBtn.disabled = true;

    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          occupation: currentResult.occupation_title,
          state: currentResult.state_code,
          email,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        showError(data.error || "Couldn't start checkout.");
        return;
      }
      window.location.href = data.url;
    } catch (err) {
      showError("Couldn't reach the payment processor. Try again in a moment.");
      console.error(err);
    } finally {
      // Won't run if redirect succeeds, but here for safety
      label.textContent = `Get my report · $${(config.reportPriceCents / 100).toFixed(0)}`;
      arrow.style.display = "";
      payBtn.disabled = false;
    }
  });

  // ─── Share / recalc ────────────────────────────────────────
  $("#share-x").addEventListener("click", () => {
    if (!currentResult) return;
    const pct = currentResult.vulnerability_pct;
    const occ = currentResult.occupation_title;
    const rank = currentResult.rank;
    const total = currentResult.total;
    const text = `My job (${occ}) has a ${pct}% AI displacement risk — ranked #${rank} most exposed of ${total} US occupations. What's yours?`;
    const url = config.baseUrl + "/calculator";
    window.open(
      `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`,
      "_blank"
    );
  });

  $("#share-link").addEventListener("click", async () => {
    const url = config.baseUrl + "/calculator";
    try {
      await navigator.clipboard.writeText(url);
      const btn = $("#share-link");
      const orig = btn.textContent;
      btn.textContent = "✓ Copied";
      setTimeout(() => btn.textContent = orig, 1800);
    } catch (e) {
      window.prompt("Copy this link:", url);
    }
  });

  $("#recalc-btn").addEventListener("click", () => {
    stageOut.style.display = "none";
    stageIn.style.display = "block";
    occInput.value = "";
    stateInput.value = "";
    currentResult = null;
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => occInput.focus(), 300);
  });

  // ─── Utilities ─────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function dateStamp() {
    return new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }).toUpperCase();
  }

  // Auto-focus on load
  setTimeout(() => occInput.focus(), 200);
})();
