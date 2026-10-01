(() => {
  const CFG = window.SHOP_CONFIG || {};
  const PAGE = 48;
  const PAY_LABEL = { cod: "Cash on delivery", whish: "Whish", omt: "OMT", card: "Card" };
  const $ = (id) => document.getElementById(id);

  const state = { tab: "shops", q: "", cat: "", pay: "", sort: "new", psort: "rel", shown: PAGE };
  let stores = [], products = [], meta = {};
  let showNewBadges = false; // only meaningful once most shops are older than a week

  // ---------- helpers ----------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
  // Used inside style="..." attributes, so the URL must never contain a double quote.
  const cssUrl = (u) => (safeUrl(u) ? `url('${safeUrl(u).replace(/['"\\\n\r()]/g, encodeURIComponent)}')` : "none");
  const norm = (s) =>
    String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ًͯ-ٟ]/g, "")
      .replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");
  const daysAgo = (iso) => (Date.now() - new Date(iso).getTime()) / 864e5;
  const timeAgo = (iso) => {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 6e4));
    if (m < 1) return "just now";
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  };
  const money = (v, cur) => {
    if (v == null) return "";
    const n = Number(v);
    if (!cur || cur === "USD") return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 2 });
    if (cur === "LBP") return n.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " LBP";
    return `${cur} ${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  };
  const issueUrl = (tpl) => `${CFG.repoUrl}/issues/new?template=${tpl}`;

  // ---------- load ----------
  async function load() {
    const get = (f) => fetch(`data/${f}?v=${Date.now() / 6e5 | 0}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const [s, p, m] = await Promise.all([get("stores.json"), get("products.json"), get("meta.json")]);
    stores = (s || []).map((x, i) => ({ ...x, i, _k: norm([x.n, x.id, x.d, (x.cats || []).join(" "), x.ig].join(" ")) }));
    // Product/image URLs are stored relative to the shop's own site to keep the file small
    const abs = (u, s) => {
      if (!u || /^https?:\/\//i.test(u) || !s || !s.url) return u;
      try { return new URL(u, s.url).href; } catch { return ""; }
    };
    products = (p || []).map((r) => ({
      s: r[0], t: r[1], p: r[2], c: r[3], cur: r[4], img: abs(r[5], stores[r[0]]), u: abs(r[6], stores[r[0]]), in: r[7], _k: norm(r[1]),
    }));
    meta = m || {};
    for (const pr of products) if (stores[pr.s]) pr._k += " " + stores[pr.s]._k.slice(0, 60);
    renderStatic();
    readHash();
    render();
  }

  // ---------- static bits ----------
  function renderStatic() {
    for (const id of ["addShopTop", "addShop", "addShopEmpty"]) $(id).href = issueUrl("add-shop.yml");
    $("removeShop").href = issueUrl("remove-shop.yml");

    const newWeek = stores.filter((s) => s.found && daysAgo(s.found) <= 7).length;
    showNewBadges = newWeek > 0 && newWeek < stores.length * 0.3;
    const last = meta.runs && meta.runs.length ? meta.runs[meta.runs.length - 1] : null;
    $("stats").innerHTML = [
      `<span><b>${stores.length.toLocaleString()}</b> shops</span>`,
      `<span><b>${(meta.products || 0).toLocaleString()}</b> products</span>`,
      newWeek ? `<span><b>${newWeek}</b> new this week</span>` : "",
      last ? `<span><i class="live"></i>Bot last checked ${esc(timeAgo(last.at))}</span>` : "",
    ].join("");

    const plans = [
      ["Featured shop (30 days)", `$${CFG.featurePriceMonthly || 15}`],
      ["Verified badge (1 year)", `$${CFG.verifiedPriceYearly || 20}`],
    ];
    $("plans").innerHTML = plans.map(([a, b]) => `<li><span>${esc(a)}</span><b>${esc(b)}</b></li>`).join("");
    $("payHowto").innerHTML = CFG.whishNumber
      ? `Pay with <b>Whish</b> to <b>${esc(CFG.whishNumber)}</b> and write your website or Instagram handle as the note. Your badge goes live within a few hours.`
      : `Payments open soon. Add your shop for free in the meantime.`;

    const runs = (meta.runs || []).slice().reverse();
    $("runs").innerHTML = runs.length
      ? runs.map((r) => `<div class="run"><time>${esc(timeAgo(r.at))}</time><span>checked <b>${r.probed}</b> sites · +${r.new_candidates} to check</span>${
          r.new_stores && r.new_stores.length ? `<span>🆕 ${r.new_stores.slice(0, 5).map(esc).join(", ")}${r.new_stores.length > 5 ? "…" : ""}</span>` : ""}</div>`).join("")
      : `<p class="muted">No runs yet.</p>`;
  }

  // ---------- filtering ----------
  function matches(key, q) {
    return q.split(/\s+/).filter(Boolean).every((w) => key.includes(w));
  }
  function filteredStores() {
    const q = norm(state.q);
    let list = stores.filter((s) =>
      (!state.cat || (s.cats || []).includes(state.cat)) &&
      (!state.pay || (s.pay || []).includes(state.pay)) &&
      (!q || matches(s._k, q)));
    const by = {
      new: (a, b) => (b.found || "").localeCompare(a.found || ""),
      az: (a, b) => a.n.localeCompare(b.n),
      products: (a, b) => (b.cnt || 0) - (a.cnt || 0),
    }[state.sort];
    list.sort((a, b) => (b.feat - a.feat) || by(a, b));
    return list;
  }
  function filteredProducts() {
    const q = norm(state.q);
    let list = products.filter((p) => {
      const s = stores[p.s];
      if (!s) return false;
      if (state.cat && !(s.cats || []).includes(state.cat)) return false;
      if (state.pay && !(s.pay || []).includes(state.pay)) return false;
      return !q || matches(p._k, q);
    });
    const price = (p) => (p.p == null ? Infinity : p.p);
    if (state.psort === "low") list.sort((a, b) => price(a) - price(b));
    else if (state.psort === "high") list.sort((a, b) => (b.p ?? -1) - (a.p ?? -1));
    else if (state.psort === "sale") list.sort((a, b) => (!!b.c - !!a.c));
    else list = interleave(list.sort((a, b) => (stores[b.s].feat - stores[a.s].feat) || (b.in - a.in)));
    return list;
  }
  // Round-robin across shops so one big catalog doesn't fill the whole first page
  function interleave(list) {
    const byStore = new Map();
    for (const p of list) (byStore.get(p.s) || byStore.set(p.s, []).get(p.s)).push(p);
    const queues = [...byStore.values()], out = [];
    for (let r = 0; out.length < list.length; r++) for (const q of queues) if (q[r]) out.push(q[r]);
    return out;
  }

  // ---------- rendering ----------
  function shopCard(s) {
    const initial = esc((s.n || "?").trim().charAt(0).toUpperCase());
    const isNew = showNewBadges && s.found && daysAgo(s.found) <= 7;
    const tags = (s.cats || []).slice(0, 3).map((c) => `<span class="tag">${esc(c)}</span>`).join("") +
      (s.cnt ? `<span class="tag gray">${s.cnt} products</span>` : "") +
      (s.plat === "instagram" ? `<span class="tag gray">Instagram shop</span>` : "");
    return `<article class="card shop${s.feat ? " featured" : ""}" data-i="${s.i}" tabindex="0">
      <div class="cover" style="background-image:${cssUrl(s.img)}">
        ${s.img ? "" : `<div class="initial">${initial}</div>`}
        ${s.feat ? `<span class="badge feat">★ Featured</span>` : isNew ? `<span class="badge new">New</span>` : ""}
        <div class="ico" style="background-image:${cssUrl(s.ico)}">${s.ico ? "" : initial}</div>
      </div>
      <div class="body">
        <h3>${esc(s.n)}</h3>
        <div class="domain">${esc(s.plat === "instagram" ? "@" + s.ig : s.id)}</div>
        ${s.d ? `<p class="desc">${esc(s.d)}</p>` : ""}
        <div class="tags">${tags}</div>
      </div>
    </article>`;
  }
  function productCard(p) {
    const s = stores[p.s];
    return `<a class="card product" href="${esc(safeUrl(p.u))}" target="_blank" rel="noopener nofollow">
      <div class="pimg" style="background-image:${cssUrl(p.img)}"></div>
      <div class="pbody">
        <div class="ptitle">${esc(p.t)}</div>
        <div class="price">${esc(money(p.p, p.cur))}${p.c ? `<s>${esc(money(p.c, p.cur))}</s>` : ""}</div>
        <div class="pshop">${esc(s ? s.n : "")}</div>
        ${p.in ? "" : `<div class="oos">Out of stock</div>`}
      </div>
    </a>`;
  }
  function renderChips(list) {
    const counts = {};
    for (const s of list) for (const c of s.cats || []) counts[c] = (counts[c] || 0) + 1;
    const cats = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    $("chips").innerHTML = [`<button class="chip${state.cat ? "" : " active"}" data-cat="">All</button>`]
      .concat(cats.map((c) => `<button class="chip${state.cat === c ? " active" : ""}" data-cat="${esc(c)}">${esc(c)}<small>${counts[c]}</small></button>`))
      .join("");
  }
  function render() {
    const shops = filteredStores();
    const prods = filteredProducts();
    renderChips(stores);
    $("shopCount").textContent = shops.length;
    $("productCount").textContent = prods.length;
    const isShops = state.tab === "shops";
    $("shopsView").hidden = !isShops;
    $("productsView").hidden = isShops;
    $("sort").hidden = !isShops;
    $("psort").hidden = isShops;
    const list = isShops ? shops : prods;
    const html = list.slice(0, state.shown).map(isShops ? shopCard : productCard).join("");
    $(isShops ? "shopGrid" : "productGrid").innerHTML = html;
    $("moreBtn").hidden = list.length <= state.shown;
    $("empty").hidden = list.length > 0;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === state.tab));
  }

  function openShop(i) {
    const s = stores[i];
    if (!s) return;
    const items = products.filter((p) => p.s === s.i);
    let shownInShop = PAGE;
    const links = [
      s.url && s.plat !== "instagram" ? `<a class="btn" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">Visit website</a>` : "",
      s.ig ? `<a class="btn btn-ghost" href="https://instagram.com/${encodeURIComponent(s.ig)}" target="_blank" rel="noopener">Instagram</a>` : "",
      s.wa ? `<a class="btn btn-ghost" href="https://wa.me/${encodeURIComponent(s.wa)}" target="_blank" rel="noopener">WhatsApp</a>` : "",
      s.fb ? `<a class="btn btn-ghost" href="https://facebook.com/${encodeURIComponent(s.fb)}" target="_blank" rel="noopener">Facebook</a>` : "",
      s.tt ? `<a class="btn btn-ghost" href="https://tiktok.com/@${encodeURIComponent(s.tt)}" target="_blank" rel="noopener">TikTok</a>` : "",
    ].join("");
    const pay = (s.pay || []).map((k) => `<span class="tag gray">${esc(PAY_LABEL[k] || k)}</span>`).join("");
    $("dlgBody").innerHTML = `
      <div class="dlg-head">
        <div class="ico" style="background-image:${cssUrl(s.ico)}">${s.ico ? "" : esc((s.n || "?").trim().charAt(0).toUpperCase())}</div>
        <div><h2>${esc(s.n)}</h2><div class="domain">${esc(s.plat === "instagram" ? "@" + s.ig : s.id)}${s.ver ? "" : " · self-submitted"}</div></div>
      </div>
      ${s.d ? `<p>${esc(s.d)}</p>` : ""}
      <div class="tags">${(s.cats || []).map((c) => `<span class="tag">${esc(c)}</span>`).join("")}${pay}</div>
      <div class="links">${links}</div>
      ${items.length ? `<h3>Products <span class="muted">(${items.length.toLocaleString()})</span></h3>
        <div class="grid products" id="dlgProducts">${items.slice(0, shownInShop).map(productCard).join("")}</div>
        <div class="more"><button id="dlgMore" class="btn btn-ghost"${items.length > shownInShop ? "" : " hidden"}>Show more</button></div>` : ""}
      <p class="claim">Is this your shop? <a href="#owners" onclick="this.closest('dialog').close()">Get it featured</a> · <a href="${esc(issueUrl("remove-shop.yml"))}" target="_blank" rel="noopener">Request removal</a></p>`;
    const more = $("dlgMore");
    if (more) more.addEventListener("click", () => {
      $("dlgProducts").insertAdjacentHTML("beforeend", items.slice(shownInShop, shownInShop + PAGE).map(productCard).join(""));
      shownInShop += PAGE;
      more.hidden = items.length <= shownInShop;
    });
    $("shopDialog").showModal();
    history.replaceState(null, "", `#shop=${encodeURIComponent(s.id)}`);
  }

  // ---------- URL state ----------
  function writeHash() {
    const h = new URLSearchParams();
    if (state.q) h.set("q", state.q);
    if (state.cat) h.set("cat", state.cat);
    if (state.tab !== "shops") h.set("tab", state.tab);
    history.replaceState(null, "", h.toString() ? `#${h}` : location.pathname);
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    state.q = h.get("q") || "";
    state.cat = h.get("cat") || "";
    state.tab = h.get("tab") === "products" ? "products" : "shops";
    $("q").value = state.q;
    const shop = h.get("shop");
    if (shop) {
      const s = stores.find((x) => x.id === shop);
      if (s) setTimeout(() => openShop(s.i), 0);
    }
  }

  // ---------- events ----------
  let t;
  $("q").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      state.q = e.target.value.trim();
      state.shown = PAGE;
      // A product-looking search with no shop hits jumps to products
      if (state.q && state.tab === "shops" && !filteredStores().length && filteredProducts().length) state.tab = "products";
      writeHash();
      render();
    }, 120);
  });
  document.querySelector(".tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (!b) return;
    state.tab = b.dataset.tab;
    state.shown = PAGE;
    writeHash();
    render();
  });
  $("chips").addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    state.cat = b.dataset.cat;
    state.shown = PAGE;
    writeHash();
    render();
  });
  $("pay").addEventListener("change", (e) => { state.pay = e.target.value; state.shown = PAGE; render(); });
  $("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  $("psort").addEventListener("change", (e) => { state.psort = e.target.value; render(); });
  $("moreBtn").addEventListener("click", () => { state.shown += PAGE; render(); });
  $("shopGrid").addEventListener("click", (e) => {
    const c = e.target.closest(".shop");
    if (c) openShop(+c.dataset.i);
  });
  $("shopGrid").addEventListener("keydown", (e) => {
    const c = e.target.closest(".shop");
    if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openShop(+c.dataset.i); }
  });
  $("shopDialog").addEventListener("close", writeHash);
  $("shopDialog").addEventListener("click", (e) => { if (e.target === $("shopDialog")) $("shopDialog").close(); });

  load();
})();
