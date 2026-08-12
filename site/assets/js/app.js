(function () {
  const STORAGE_KEY = "k8s-viper-node-ip";
  const grid = document.getElementById("quick-grid");
  if (!grid) return;

  const PLACEHOLDER = grid.dataset.placeholder || "<node-ip>";
  const DEFAULT_HINT = grid.dataset.defaultIp || "172.17.0.2";

  function getIp() {
    const v = (localStorage.getItem(STORAGE_KEY) || "").trim();
    return v || PLACEHOLDER;
  }

  function setIp(ip) {
    const cleaned = (ip || "").trim();
    if (!cleaned || cleaned === PLACEHOLDER) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, cleaned);
    render();
  }

  function esc(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderQuick(ip) {
    grid.querySelectorAll(".quick-card").forEach((card) => {
      const scheme = card.dataset.scheme;
      const port = card.dataset.port;
      const url = `${scheme}://${ip}:${port}/`;
      const urlEl = card.querySelector("[data-url]");
      if (urlEl) urlEl.textContent = url;

      const linkable = ip !== PLACEHOLDER;
      if (card.tagName === "A") {
        if (linkable) card.href = url;
        else card.removeAttribute("href");
        return;
      }
      // promote / demote to link for clickability
      if (linkable && card.tagName !== "A") {
        const a = document.createElement("a");
        a.className = card.className;
        a.href = url;
        a.target = "_blank";
        a.rel = "noopener";
        Object.keys(card.dataset).forEach((k) => {
          a.dataset[k] = card.dataset[k];
        });
        a.innerHTML = card.innerHTML;
        card.replaceWith(a);
      }
    });
    // second pass if we replaced nodes — ensure urls set
    grid.querySelectorAll(".quick-card").forEach((card) => {
      const scheme = card.dataset.scheme;
      const port = card.dataset.port;
      const url = `${scheme}://${ip}:${port}/`;
      const urlEl = card.querySelector("[data-url]");
      if (urlEl) urlEl.textContent = url;
      if (card.tagName === "A" && ip !== PLACEHOLDER) card.href = url;
    });
  }

  function renderUis(ip) {
    document.querySelectorAll("[data-ui]").forEach((row) => {
      const scheme = row.dataset.scheme;
      const host = row.dataset.host;
      const path = row.dataset.path || "/";
      let url;
      if (host) url = `${scheme}://${host}/`;
      else url = `${scheme}://${ip}${path}`;

      const cell = row.querySelector("[data-url-cell]");
      if (!cell) return;
      const linkable = ip !== PLACEHOLDER && !host;
      if (linkable) {
        cell.innerHTML = `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>`;
      } else {
        cell.textContent = url;
      }
    });
  }

  function render() {
    const ip = getIp();
    const input = document.getElementById("node-ip");
    if (input && document.activeElement !== input) {
      input.value = ip === PLACEHOLDER ? "" : ip;
      input.placeholder = `e.g. ${DEFAULT_HINT}`;
    }
    renderQuick(ip);
    renderUis(ip);
  }

  document.getElementById("save-ip")?.addEventListener("click", () => {
    setIp(document.getElementById("node-ip").value);
  });
  document.getElementById("reset-ip")?.addEventListener("click", () => setIp(""));
  document.getElementById("node-ip")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") setIp(e.target.value);
  });

  /* TOC active section + mobile drawer */
  const tocLinks = [...document.querySelectorAll("#toc-list a")];
  const sections = tocLinks
    .map((a) => document.querySelector(a.getAttribute("href")))
    .filter(Boolean);

  function setActiveToc() {
    if (!sections.length) return;
    let current = sections[0];
    const y = window.scrollY + 120;
    for (const s of sections) {
      if (s.offsetTop <= y) current = s;
    }
    tocLinks.forEach((a) => {
      a.classList.toggle("active", a.getAttribute("href") === `#${current.id}`);
    });
  }

  window.addEventListener("scroll", setActiveToc, { passive: true });
  setActiveToc();

  const toggle = document.getElementById("toc-toggle");
  toggle?.addEventListener("click", () => {
    const open = document.body.classList.toggle("toc-open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  tocLinks.forEach((a) =>
    a.addEventListener("click", () => {
      document.body.classList.remove("toc-open");
      toggle?.setAttribute("aria-expanded", "false");
    })
  );

  render();
})();
