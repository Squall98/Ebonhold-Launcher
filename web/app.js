"use strict";
/* =====================================================================
   Ebonhold Launcher v2 — interface.
   Le moteur Python est appelé par window.pywebview.api.<méthode>(…) (promesses) et
   pousse les opérations longues par window.on<Événement>(…).
   Contrat : chantier-maj-2026-10/launcher-v2-contrat.md.
   Règle d'or : tout texte venu du moteur ou du catalogue passe par esc() (ou textContent)
   avant d'entrer dans la page ; icônes et couleurs du catalogue passent par safeIcon/safeAccent.
   Aperçu dans un navigateur (sans moteur) : index.html?apercu  → données d'exemple (MOCK).
   ===================================================================== */

/* ================================================================ 1. Outils */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
// Tout texte venu du catalogue ou du moteur (noms, notes, chemins, messages…) passe par esc()
// avant d'entrer dans du HTML : une release piégée ne peut pas injecter de code dans le launcher.
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ACCENTS = ["purple","teal","coral","blue","amber","pink","green"];
const safeIcon = s => /^ti-[a-z0-9-]+$/.test(s || "") ? s : "";
const safeAccent = s => ACCENTS.includes(s) ? s : "";
// Vignettes : seulement des images encodées (jamais une URL, jamais du SVG venu du moteur).
const safeImg = s => (typeof s === "string" && /^data:image\/(png|jpe?g|gif|webp|bmp);base64,[a-z0-9+/=]+$/i.test(s)) ? s : "";
const sel = s => (window.CSS && CSS.escape) ? CSS.escape(String(s)) : String(s).replace(/["\\\]]/g, "\\$&");
const plural = (n, one, many) => (Math.abs(Number(n) || 0) >= 2 ? many : one);
const baseName = p => String(p || "").split(/[\\/]/).pop() || String(p || "");
const norm = s => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const pct = v => Math.max(0, Math.min(100, Number(v) || 0));
const VIDEO_EXT = /\.(mp4|mkv|webm|avi|mov|wmv|m4v)$/i;
function fmtSize(b){
  b = Number(b); if (!isFinite(b) || b <= 0) return "";
  const u = ["o","Ko","Mo","Go"]; let i = 0;
  while (b >= 1024 && i < u.length - 1){ b /= 1024; i++; }
  return (i ? b.toFixed(b < 10 ? 1 : 0).replace(".", ",") : Math.round(b)) + " " + u[i];
}
function debounce(fn, ms){ let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
// localStorage peut être indisponible (profil verrouillé…) : jamais d'exception.
const store = {
  get(k){ try { return localStorage.getItem(k); } catch(e){ return null; } },
  set(k, v){ try { localStorage.setItem(k, v); } catch(e){} },
};

/* ================================================================ 2. Événements du moteur */
// Chaque window.onX est défini DÈS LE CHARGEMENT : un événement poussé tôt n'est jamais perdu.
// Plusieurs parties de l'interface peuvent écouter le même événement (on / emit).
const BUS = {};
function on(ev, fn){ (BUS[ev] = BUS[ev] || []).push(fn); return () => { BUS[ev] = (BUS[ev] || []).filter(f => f !== fn); }; }
function emit(ev, ...args){
  (BUS[ev] || []).slice().forEach(fn => {
    try { fn(...args); } catch(e){ console.error(e); jsLog("erreur interface (" + ev + ") : " + (e && e.message)); }
  });
}
["onCatalogUpdate","onProgress","onDone","onLauncherProgress","onLauncherReady","onLauncherError",
 "onPackProgress","onPackDone","onFrLog","onFrDone","onFrState","onScanProgress","onScanDone",
 "onFixDone","onReportProgress","onReportDone"].forEach(ev => { window[ev] = (...a) => emit(ev, ...a); });
// Attend un événement (optionnellement filtré). À créer AVANT l'appel qui le déclenche.
function waitEvent(ev, pred = () => true, timeoutMs = 0){
  return new Promise(res => {
    let t = null;
    const off = on(ev, (...a) => { if (!pred(...a)) return; off(); if (t) clearTimeout(t); res({args: a}); });
    if (timeoutMs) t = setTimeout(() => { off(); res({timeout: true, args: []}); }, timeoutMs);
  });
}
window.addEventListener("error", e => jsLog("erreur JS : " + e.message + " (ligne " + e.lineno + ")"));

/* ================================================================ 3. Pont pywebview */
const bridgeReady = () => !!(window.pywebview && window.pywebview.api);
function api(){ return bridgeReady() ? window.pywebview.api : MOCK; }
function jsLog(msg){ try { if (bridgeReady() && window.pywebview.api.js_log) window.pywebview.api.js_log(String(msg)); } catch(e){} }
const hasMethod = name => typeof (api() || {})[name] === "function";
// Appel protégé : une méthode absente (moteur pas encore à jour) ou une exception Python
// renvoie un objet d'erreur au lieu de casser l'interface.
async function call(name, ...args){
  if (!bridgeReady() && !_started) return {ok:false, started:false, error:"Le launcher démarre…"};
  const a = api(), f = a && a[name];
  if (typeof f !== "function"){
    jsLog("méthode absente : " + name);
    return {ok:false, started:false, error:"Fonction pas encore disponible (" + name + ")."};
  }
  try {
    const r = await f.apply(a, args);
    return (r && typeof r === "object") ? r : {value: r};
  } catch(e){
    const m = (e && e.message) || String(e);
    jsLog("échec " + name + " : " + m);
    return {ok:false, started:false, error:"Erreur du launcher : " + m};
  }
}

/* ================================================================ 4. État */
let CATALOG = null;           // dernière réponse de get_catalog
let FR = null;                // dernière réponse de get_fr_settings
let FR_CUR = null;            // réglages FR en cours de modification
let FR_ERR = "";
let FR_APPLYING = false;
let FR_LAST = "";             // dernière ligne du journal FR
let PACK = {busy:false, pct:0, msg:"", err:""};
let PREFS = {};
let HAS_EXE = null, _exePath = null;
let TAB = "home";
let LAUNCHER_MSG = "";
let PLAY_BUSY = null;
let FIX = {running:false};
let WIZ_RUNNING = false;
const BUSY = {};              // id produit -> {pct, msg} pendant une installation
const quiet = () => FIX.running || WIZ_RUNNING;   // pas de notifications en double pendant ces flux
const DISCORD_URL = "https://discord.gg/ebonhold";
const GITHUB_URL = "https://github.com/Squall98/Ebonhold-Launcher";
let _started = false, _real = false, _bound = false;

/* ================================================================ 5. Zoom de l'interface */
const ZMIN = 0.8, ZMAX = 1.6;
const clampZoom = z => { z = Math.round(Number(z) * 10) / 10; return isFinite(z) && z > 0 ? Math.min(ZMAX, Math.max(ZMIN, z)) : 1; };
let ZOOM = clampZoom(parseFloat(store.get("ebon_zoom")) || 1);   // déjà appliqué par le script de <head>
const saveZoomPref = debounce(() => { if (_started) call("set_pref", "zoom", ZOOM); }, 500);
const zoomToast = debounce(() => { if (TAB !== "settings") toast("Zoom : " + Math.round(ZOOM * 100) + " %", "info"); }, 300);
function applyZoom(z, save = true){
  ZOOM = clampZoom(z);
  const root = document.documentElement;
  root.style.zoom = ZOOM;                      // CSS zoom sur la racine : toute la page
  root.style.setProperty("--zoom", ZOOM);      // pour compenser les hauteurs en vh
  $$(".zoom-val").forEach(el => el.textContent = Math.round(ZOOM * 100) + " %");
  $$("[data-zoom='-1']").forEach(b => b.disabled = ZOOM <= ZMIN);
  $$("[data-zoom='1']").forEach(b => b.disabled = ZOOM >= ZMAX);
  layoutClasses();
  if (save){ store.set("ebon_zoom", String(ZOOM)); saveZoomPref(); }
}
function zoomBy(step){
  const before = ZOOM;
  applyZoom(step === 0 ? 1 : ZOOM + step * 0.1);
  if (ZOOM !== before) zoomToast();
}
// Fenêtre étroite ou zoom fort : barre latérale réduite aux icônes, etc.
function layoutClasses(){
  const w = window.innerWidth / ZOOM, h = window.innerHeight / ZOOM, r = document.documentElement;
  r.classList.toggle("compact", w < 780);
  r.classList.toggle("short", h < 560);
}
let _lastWheel = 0;
window.addEventListener("wheel", e => {
  if (!e.ctrlKey) return;
  e.preventDefault();                          // pas de zoom natif de WebView2 en plus du nôtre
  const t = Date.now(); if (t - _lastWheel < 90) return; _lastWheel = t;
  zoomBy(e.deltaY < 0 ? 1 : -1);
}, {passive:false});
window.addEventListener("keydown", e => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const k = e.key, c = e.code;
  if (k === "+" || k === "=" || c === "NumpadAdd"){ e.preventDefault(); zoomBy(1); }
  else if (k === "-" || k === "_" || c === "NumpadSubtract"){ e.preventDefault(); zoomBy(-1); }
  else if (k === "0" || c === "Digit0" || c === "Numpad0"){ e.preventDefault(); zoomBy(0); }   // Digit0 : Ctrl + à en AZERTY
}, true);
window.addEventListener("resize", debounce(layoutClasses, 80));

/* ================================================================ 6. Notifications, onglets, fenêtres */
function toast(msg, kind = "info", title = ""){
  if (!msg) return;
  const el = document.createElement("div");
  el.className = "toast " + kind;
  el.setAttribute("role", kind === "err" ? "alert" : "status");
  el.innerHTML = (title ? `<div class="tt">${esc(title)}</div>` : "") + esc(msg);
  el.addEventListener("click", () => el.remove());
  const box = $("#toasts"); box.appendChild(el);
  while (box.children.length > 4) box.firstChild.remove();
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 260); }, kind === "err" ? 6500 : 4000);
}

const TABS = {
  home:     {t:"Accueil",  s:"Tout ce qu'il faut pour jouer, au même endroit."},
  addons:   {t:"Addons",   s:"Installe et mets à jour tes addons en un clic."},
  fr:       {t:"Français", s:"Choisis ce qui est traduit dans le jeu."},
  help:     {t:"Aide",     s:"Un souci, une idée ? C'est par ici."},
  settings: {t:"Réglages", s:"Dossier du jeu, zoom et infos."},
};
function switchTab(name){
  if (!TABS[name]) name = "home";
  TAB = name;
  $$(".nav-item").forEach(b => {
    const act = b.dataset.tab === name;
    b.classList.toggle("active", act);
    if (act) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  $$(".tab").forEach(t => t.classList.toggle("hidden", t.id !== "tab-" + name));
  $("#tabTitle").textContent = TABS[name].t;
  $("#tabSub").textContent = TABS[name].s;
  $("#tab-" + name).scrollTop = 0;
  renderTopPlay();
  if (name === "fr") loadFr();
}

// Fenêtres modales : pile, Échap, clic sur le fond, focus piégé et rendu à la fermeture.
const MSTACK = [];
const FOCUSABLE = "button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex='-1'])";
function openModal(id){
  const el = $("#" + id); if (!el) return;
  if (!MSTACK.includes(id)){ MSTACK.push(id); el._back = document.activeElement; }
  el.classList.remove("hidden");
  setTimeout(() => {
    const f = $$(FOCUSABLE, el).find(x => !x.classList.contains("dialog-close") && x.offsetParent !== null);
    if (f) f.focus();
  }, 40);
}
function closeModal(id){
  const el = $("#" + id);
  if (!el || el.classList.contains("hidden") || el.dataset.locked === "1") return false;
  el.classList.add("hidden");
  const i = MSTACK.indexOf(id); if (i >= 0) MSTACK.splice(i, 1);
  if (el._back && el._back.isConnected && el._back.focus) el._back.focus();
  return true;
}
function lockModal(id, locked){
  const el = $("#" + id); el.dataset.locked = locked ? "1" : "";
  $$("[data-close]", el).forEach(b => b.disabled = locked);
}
function trapFocus(e, root){
  const f = $$(FOCUSABLE, root).filter(x => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (!root.contains(document.activeElement)){ e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
}
document.addEventListener("keydown", e => {
  const top = MSTACK[MSTACK.length - 1];
  if (top){
    if (e.key === "Escape"){ e.preventDefault(); closeModal(top); }
    else if (e.key === "Tab") trapFocus(e, $("#" + top));
  } else if (e.key === "Tab" && wizardOpen()) trapFocus(e, $("#wizard"));
});

async function openUrl(url){
  if (!url) return;
  const r = await call("open_url", url);
  if (r.ok === false) toast(r.error || "Lien refusé.", "err");
}
async function openLog(){
  const r = await call("open_log");
  if (r.ok === false) toast(r.error || "Impossible d'ouvrir le journal.", "err");
  else toast("Journal ouvert dans le Bloc-notes.", "info");
}
function linkUrl(re, fallback){
  const l = ((CATALOG && CATALOG.links) || []).find(x => x && re.test(String(x.url || "")));
  return (l && l.url) || fallback;
}

/* ================================================================ 7. Catalogue */
async function reload(checkRemote = false){
  const r = await call("get_catalog", !!checkRemote);
  if (r && Array.isArray(r.products)){ CATALOG = r; renderAll(); }
  else { if (!CATALOG) renderAll(); toast((r && r.error) || "Catalogue indisponible.", "err"); }
  return CATALOG;
}
const reloadSoon = debounce(() => reload(false), 350);
// Poussé par le moteur quand le catalogue en ligne (ou la détection du jeu) arrive en arrière-plan.
on("onCatalogUpdate", cat => { if (cat && Array.isArray(cat.products)){ CATALOG = cat; renderAll(); } });

const products = () => (CATALOG && CATALOG.products) || [];
const visibleProducts = () => products().filter(p => !p.managed);   // managed = géré ailleurs (ex. EbonholdFR → onglet Français)
const findProduct = id => products().find(p => p.id === id);
const addonUpdates = () => visibleProducts().filter(p => p.status === "update" || p.status === "repair");
const DEFAULT_ACCENT = {traduction:"purple", carte:"teal", quetes:"amber", metiers:"blue", sacs:"coral", personnage:"pink", interface:"teal", donnees:"coral"};
const accentOf = p => safeAccent(p.accent) || DEFAULT_ACCENT[p.category] || "purple";
const thumbAccent = p => "acc-" + accentOf(p);
const thumbIcon = p => safeIcon(p.icon) || "ti-puzzle";
const catLabel = id => (((CATALOG && CATALOG.categories) || []).find(c => c.id === id) || {}).label || id || "";

function renderAll(){
  renderSidebar(); renderHome(); renderAddons(); renderSettings(); renderHelpLinks(); renderTopPlay();
  if (wizardOpen()) renderWiz();
  refreshExe();
}
async function refreshExe(){
  if (!CATALOG || !CATALOG.wow_valid){ HAS_EXE = null; _exePath = null; return; }
  if (_exePath === CATALOG.wow_path && HAS_EXE !== null) return;
  _exePath = CATALOG.wow_path;
  const r = await call("has_game_exe");
  HAS_EXE = r.present === undefined ? null : !!r.present;
  renderHero();
}

/* ================================================================ 8. Barre latérale */
const SRC = {
  remote: ["ti-cloud", "En ligne", "Catalogue en ligne à jour.", "catalogue en ligne"],
  cache:  ["ti-cloud-off", "Hors ligne", "Pas de connexion : dernier catalogue en ligne gardé.", "dernier catalogue en ligne (hors ligne)"],
  local:  ["ti-package", "Catalogue intégré", "Catalogue livré avec le launcher.", "catalogue intégré au launcher"],
};
function renderSidebar(){
  const c = CATALOG, n = addonUpdates().length;
  const b = $("#badgeAddons"); b.textContent = n; b.classList.toggle("hidden", !n);
  b.title = n + " " + plural(n, "mise à jour", "mises à jour");
  $("#badgeFr").classList.toggle("hidden", !frNeedsReapply());
  const g = $("#sideGame"), t = $("#sideGameTxt");
  if (!c){ g.className = "side-game"; t.textContent = "Recherche du jeu…"; }
  else if (c.wow_valid){ g.className = "side-game ok"; t.textContent = "Jeu trouvé"; g.title = "Dossier du jeu : " + (c.wow_path || ""); }
  else { g.className = "side-game bad"; t.textContent = c.wow_path ? "Dossier invalide" : "Jeu introuvable"; g.title = "Choisir le dossier du jeu"; }
  $("#sideFoot").textContent = c ? "Launcher communautaire · v" + c.launcher_version : "Launcher communautaire";
  const s = c ? (SRC[c.source] || SRC.local) : null, pill = $("#sourcePill");
  pill.className = "source-pill " + (c ? esc(c.source) : "");
  pill.innerHTML = s ? `<i class="ti ${s[0]}" aria-hidden="true"></i><span>${esc(s[1])}</span>` : "";
  pill.title = s ? s[2] : "";
}

/* ================================================================ 9. Accueil */
function frNeedsReapply(){ const s = FR && FR.state; return !!(s && s.applied && !s.up_to_date); }
function renderTopPlay(){
  const b = $("#topPlay");
  b.classList.toggle("hidden", TAB === "home" || !CATALOG || !CATALOG.wow_valid);
  b.disabled = !!PLAY_BUSY;
}
function renderHero(){
  const c = CATALOG, btn = $("#playBtn"), lbl = $("#playLabel"), ic = $("#playIcon"), hint = $("#playHint");
  const title = $("#heroTitle"), sub = $("#heroSub");
  if (!c){ title.textContent = "Bienvenue"; sub.textContent = "Chargement…"; btn.disabled = true; return; }
  if (PLAY_BUSY){ btn.disabled = true; lbl.textContent = PLAY_BUSY; ic.className = "ti ti-loader-2 spin"; return; }
  btn.disabled = false;
  if (!c.wow_valid){
    btn.classList.add("find"); lbl.textContent = "Trouver mon jeu"; ic.className = "ti ti-folder-search";
    title.textContent = "Bienvenue !";
    sub.textContent = c.wow_path ? "Le dossier choisi ne contient pas le jeu. Indique le bon dossier pour commencer."
                                 : "Commence par indiquer où est installé le jeu.";
    hint.textContent = "Le launcher a besoin du dossier qui contient Wow.exe.";
    return;
  }
  btn.classList.remove("find"); lbl.textContent = "Jouer"; ic.className = "ti ti-player-play";
  hint.textContent = HAS_EXE === false ? "Wow.exe est introuvable dans le dossier du jeu."
                                       : "Vérifie le français et les addons, puis lance le jeu.";
  const todo = [], n = addonUpdates().length;
  if (frNeedsReapply()) todo.push("le français à réappliquer");
  if (n) todo.push(n + " " + plural(n, "addon", "addons") + " à mettre à jour");
  title.textContent = todo.length ? "Presque prêt" : "Prêt à jouer";
  sub.textContent = todo.length ? "Avant de jouer : " + todo.join(" et ") + ". Le bouton Jouer s'en occupe."
                                : "Tout est à jour. Bon jeu sur Ebonhold !";
}
function scard(o){
  return `<article class="scard tone-${o.tone || "none"}" id="${o.id}">
    <div class="scard-top"><div class="scard-ico"><i class="ti ${o.icon}" aria-hidden="true"></i></div>
      <div><div class="scard-title">${esc(o.title)}</div><div class="scard-state">${esc(o.state)}</div></div></div>
    <div class="scard-detail" title="${esc(o.detail)}">${esc(o.detail)}</div>
    ${o.btn ? `<button class="btn ${o.btn.cls || "ghost"} sm" data-act="${o.btn.act}"><i class="ti ${o.btn.icon}" aria-hidden="true"></i>${esc(o.btn.label)}</button>` : ""}
  </article>`;
}
function cardGame(){
  const c = CATALOG;
  if (c.wow_valid) return scard({id:"card-game", tone:"ok", icon:"ti-device-gamepad-2", title:"Jeu", state:"Dossier trouvé", detail:c.wow_path,
    btn:{act:"go-settings", icon:"ti-folder", label:"Changer"}});
  return scard({id:"card-game", tone:"bad", icon:"ti-folder-search", title:"Jeu", state: c.wow_path ? "Dossier invalide" : "Dossier introuvable",
    detail: c.wow_path ? "Ce dossier ne contient pas le jeu." : "Indique où est installé le jeu.",
    btn:{act:"find-game", icon:"ti-radar", label:"Trouver mon jeu", cls:"gold"}});
}
function cardFr(){
  if (!FR) return scard({id:"card-fr", tone: FR_ERR ? "bad" : "none", icon:"ti-language", title:"Français",
    state: FR_ERR ? "Indisponible" : "Lecture…", detail: FR_ERR || "Lecture des réglages de langue…", btn:{act:"go-fr", icon:"ti-language", label:"Ouvrir"}});
  const s = FR.state || {};
  if (FR_APPLYING) return scard({id:"card-fr", tone:"info", icon:"ti-loader-2 spin", title:"Français", state:"Application…", detail: FR_LAST || "Ferme le jeu pendant l'opération."});
  if (s.applied && s.up_to_date) return scard({id:"card-fr", tone:"ok", icon:"ti-language", title:"Français", state:"À jour",
    detail: s.server_changed && s.message ? s.message : (s.last_applied ? "Appliqué le " + s.last_applied : "Réglages appliqués."),
    btn:{act:"go-fr", icon:"ti-adjustments", label:"Régler"}});
  if (s.applied) return scard({id:"card-fr", tone:"warn", icon:"ti-refresh-alert", title:"Français", state:"À réappliquer",
    detail: s.message || "Le serveur a été mis à jour.", btn:{act:"fr-reapply", icon:"ti-refresh", label:"Réappliquer", cls:"amber"}});
  return scard({id:"card-fr", tone:"none", icon:"ti-language", title:"Français", state:"Pas encore réglé",
    detail:"Choisis ta langue dans l'onglet Français.", btn:{act:"go-fr", icon:"ti-language", label:"Régler", cls:"gold"}});
}
function cardAddons(){
  const ups = addonUpdates(), n = ups.length, busy = Object.keys(BUSY).length;
  const inst = visibleProducts().filter(p => p.installed_version != null).length;
  if (busy) return scard({id:"card-addons", tone:"info", icon:"ti-loader-2 spin", title:"Addons", state:"Installation…",
    detail: busy + " " + plural(busy, "addon en cours", "addons en cours") + "."});
  if (n) return scard({id:"card-addons", tone:"warn", icon:"ti-arrows-up", title:"Addons",
    state: n + " " + plural(n, "mise à jour", "mises à jour"), detail: ups.slice(0, 3).map(p => p.name).join(", ") + (n > 3 ? "…" : ""),
    btn:{act:"update-all", icon:"ti-arrows-up", label:"Tout mettre à jour", cls:"amber"}});
  return scard({id:"card-addons", tone:"ok", icon:"ti-puzzle", title:"Addons", state:"Tout est à jour",
    detail: inst ? inst + " " + plural(inst, "addon installé", "addons installés") + "." : "Aucun addon installé pour l'instant.",
    btn:{act:"go-addons", icon:"ti-puzzle", label: inst ? "Voir les addons" : "Choisir des addons"}});
}
function cardLauncher(){
  const c = CATALOG;
  if (LAUNCHER_MSG) return scard({id:"card-launcher", tone:"info", icon:"ti-loader-2 spin", title:"Launcher", state:"Mise à jour…", detail: LAUNCHER_MSG});
  if (c.launcher_update) return scard({id:"card-launcher", tone:"warn", icon:"ti-download", title:"Launcher",
    state:"Version " + c.latest_launcher_version + " disponible", detail:"Tu as la version " + c.launcher_version + ".",
    btn:{act:"update-launcher", icon:"ti-download", label:"Mettre à jour", cls:"amber"}});
  return scard({id:"card-launcher", tone:"ok", icon:"ti-rocket", title:"Launcher", state:"À jour", detail:"Version " + c.launcher_version + "."});
}
function renderHome(){
  renderHero();
  const grid = $("#statusGrid");
  if (!CATALOG){ grid.innerHTML = `<div class="boot-loading"><i class="ti ti-loader-2 spin" aria-hidden="true"></i>Chargement…</div>`; return; }
  const focused = document.activeElement && grid.contains(document.activeElement) ? document.activeElement.dataset.act : null;
  grid.innerHTML = [cardGame(), cardFr(), cardAddons(), cardLauncher()].join("");
  if (focused){ const b = grid.querySelector(`[data-act="${sel(focused)}"]`); if (b) b.focus(); }
  renderNews();
}
let NEWS_ALL = false;
function renderNews(){
  const rank = p => (p.status === "update" || p.status === "repair") ? 0 : p.installed_version != null ? 1 : 2;
  const items = products().filter(p => p.notes).sort((a, b) => rank(a) - rank(b));
  const shown = NEWS_ALL ? items : items.slice(0, 5);
  $("#newsList").innerHTML = shown.length ? shown.map(p => `<div class="news-item">
      <div class="news-ico thumb ${thumbAccent(p)}"><i class="ti ${thumbIcon(p)}" aria-hidden="true"></i></div>
      <div class="news-body"><div class="news-t">${esc(p.name)}<span class="ver">v${esc(p.version)}</span>
        ${p.status === "update" ? ' <span class="tag warn">nouvelle version</span>' : ""}</div>
        <div class="news-s">${esc(p.notes)}</div></div>
      ${p.changelog_url ? `<button class="btn ghost sm" data-url="${esc(p.changelog_url)}"><i class="ti ti-external-link" aria-hidden="true"></i>Détails</button>` : ""}
    </div>`).join("") : `<p class="muted">Pas de nouveautés pour l'instant.</p>`;
  const more = $("#newsMore");
  more.classList.toggle("hidden", items.length <= 5);
  more.textContent = NEWS_ALL ? "Voir moins" : "Voir tout (" + items.length + ")";
}
async function homeAction(act){
  if (act === "go-settings") switchTab("settings");
  else if (act === "find-game"){ switchTab("settings"); settingsFinder.detect(); }
  else if (act === "go-fr") switchTab("fr");
  else if (act === "go-addons") switchTab("addons");
  else if (act === "fr-reapply"){ if (FR) applyFr(normFr(FR.settings), "home"); }
  else if (act === "update-all") updateAll();
  else if (act === "update-launcher") updateLauncher();
}

/* ---- mise à jour du launcher ---- */
async function updateLauncher(){
  LAUNCHER_MSG = "Préparation…"; renderHome();
  const r = await call("update_launcher");
  if (r.mode === "dev"){
    LAUNCHER_MSG = ""; renderHome();
    if (r.url) openUrl(r.url);
    toast("Page de téléchargement ouverte (version de développement).", "info", "Launcher");
  } else if (r.ok){
    toast("Téléchargement de la mise à jour…", "info", "Launcher");
  } else { LAUNCHER_MSG = ""; renderHome(); toast(r.error || "Mise à jour impossible.", "err", "Launcher"); }
}
on("onLauncherProgress", (p, msg) => {
  LAUNCHER_MSG = (msg || "Téléchargement") + " " + Math.round(pct(p)) + " %";
  const d = $("#card-launcher .scard-detail");
  if (d && $("#card-launcher").classList.contains("tone-info")) d.textContent = LAUNCHER_MSG; else renderHome();
});
on("onLauncherReady", () => { LAUNCHER_MSG = "Redémarrage…"; renderHome(); toast("Mise à jour prête, le launcher redémarre…", "ok", "Launcher"); });
on("onLauncherError", msg => { LAUNCHER_MSG = ""; renderHome(); toast(msg || "Erreur.", "err", "Launcher"); });

/* ================================================================ 10. Jouer (vérifications + correction) */
function setPlayBusy(t){ PLAY_BUSY = t; renderHero(); renderTopPlay(); }
async function play(){
  if (PLAY_BUSY || FIX.running) return;
  if (!CATALOG || !CATALOG.wow_valid){ switchTab("settings"); settingsFinder.detect(); return; }
  setPlayBusy("Vérification…");
  const r = await call("check_before_play");
  setPlayBusy(null);
  const issues = (Array.isArray(r.issues) ? r.issues : []).filter(i => i && i.label);
  if (r.ok === true || (!issues.length && !r.error)) return launch();
  if (!issues.length) issues.push({id:"", label:"La vérification n'a pas pu se faire. " + (r.error || ""), fix_label:""});
  openPlayModal(issues);
}
async function launch(){
  setPlayBusy("Lancement…");
  const r = await call("launch_game");
  if (r.ok) toast("Le jeu se lance. Bon jeu !", "ok"); else toast(r.error || "Lancement impossible.", "err");
  setTimeout(() => setPlayBusy(null), r.ok ? 3000 : 0);
  return r;
}
let PLAY_ISSUES = [];
const fixable = () => PLAY_ISSUES.filter(i => i.id && i.fix_label);
function openPlayModal(issues){
  PLAY_ISSUES = issues; FIX = {running:false};
  $("#playIntro").textContent = issues.length > 1 ? "Quelques points à régler avant de jouer :" : "Un point à régler avant de jouer :";
  $("#playIssues").innerHTML = issues.map(i => `<li><i class="ti ti-alert-triangle" aria-hidden="true"></i><div>
      <div class="i-lbl">${esc(i.label)}</div>
      ${i.fix_label ? `<div class="i-fix"><i class="ti ti-tools" aria-hidden="true"></i> ${esc(i.fix_label)}</div>` : `<div class="i-fix none">À régler toi-même.</div>`}
    </div></li>`).join("");
  const fb = $("#playFix");
  fb.classList.toggle("hidden", !fixable().length); fb.disabled = false;
  fb.innerHTML = '<i class="ti ti-tools" aria-hidden="true"></i>Corriger et jouer';
  $("#playAnyway").disabled = false;
  $("#playProgress").classList.add("hidden"); $("#playError").classList.add("hidden"); $("#playLog").textContent = "";
  openModal("playModal");
}
async function fixAndPlay(){
  const ids = fixable().map(i => i.id); if (!ids.length || FIX.running) return;
  FIX = {running:true}; lockModal("playModal", true);
  $("#playFix").disabled = true; $("#playAnyway").disabled = true;
  $("#playProgress").classList.remove("hidden"); $("#playError").classList.add("hidden");
  $("#playProgressMsg").textContent = "Correction en cours…"; $("#playLog").textContent = "";
  const r = await call("fix_issues", ids);
  if (!r.started) fixFailed(r.error || "Correction impossible.");
}
function fixFailed(msg){
  FIX = {running:false}; lockModal("playModal", false);
  $("#playProgress").classList.add("hidden");
  const e = $("#playError"); e.innerHTML = `<i class="ti ti-alert-triangle" aria-hidden="true"></i><span>${esc(msg)}</span>`; e.classList.remove("hidden");
  $("#playAnyway").disabled = false;
  const fb = $("#playFix"); fb.disabled = false; fb.innerHTML = '<i class="ti ti-refresh" aria-hidden="true"></i>Réessayer';
}
function fixLine(m){
  if (!FIX.running || !m) return;
  $("#playProgressMsg").textContent = m;
  const l = $("#playLog"); l.textContent += m + "\n"; l.scrollTop = l.scrollHeight;
}
on("onFrLog", m => fixLine(String(m || "")));
on("onPackProgress", (p, m) => { if (FIX.running && m) $("#playProgressMsg").textContent = m; });
on("onProgress", (id, p, m) => { if (!FIX.running) return; const pr = findProduct(id); $("#playProgressMsg").textContent = (pr ? pr.name + " : " : "") + (m || ""); });
on("onDone", (id, ok, m) => { if (!FIX.running) return; const pr = findProduct(id); fixLine((ok ? "✓ " : "✗ ") + (pr ? pr.name + " : " : "") + (m || "")); });
on("onFixDone", async (ok, msg) => {
  if (!FIX.running) return;
  if (ok){
    FIX = {running:false}; lockModal("playModal", false); closeModal("playModal");
    toast(msg || "Tout est corrigé.", "ok");
    reload(); loadFr({reset:true});
    await launch();
  } else fixFailed(msg || "La correction a échoué.");
});

/* ================================================================ 11. Addons */
let FILTER = {term:"", cat:"all", state:"all"};
let VIEW = store.get("ebon_view"); if (!["cards","list","table"].includes(VIEW)) VIEW = "cards";
let SORT = {col:"name", dir:1};
function actionBtn(p){
  const busy = !!BUSY[p.id];
  const st = ["install","update","repair","uptodate"].includes(p.status) ? p.status : "install";
  const cls = busy ? "act-busy" : "act-" + st;
  const icon = busy ? "ti-loader-2 spin" : {uptodate:"ti-check", update:"ti-arrows-up", repair:"ti-tools"}[st] || "ti-download";
  const lbl = busy ? "En cours…" : {uptodate:"Installé", update:"Mettre à jour", repair:"Réparer"}[st] || "Installer";
  return `<button class="actbtn ${cls}" data-install ${busy || st === "uptodate" ? "disabled" : ""}><i class="ti ${icon}" aria-hidden="true"></i>${lbl}</button>`;
}
function metaLine(p){
  const v = esc(p.version), iv = esc(p.installed_version);
  return p.status === "update" ? `v${iv} → v${v}` : p.status === "repair" ? `v${v} · fichiers manquants` : `v${v}`;
}
function progressHTML(p){
  const b = BUSY[p.id];
  return b ? `<div class="progress"><i style="width:${pct(b.pct)}%"></i></div><div class="progress-msg">${esc(b.msg || "")}</div>` : "";
}
function cardHTML(p){
  return `<div class="card" data-id="${esc(p.id)}" tabindex="0" aria-label="${esc(p.name)} : voir la fiche">
    <div class="thumb ${thumbAccent(p)}"><i class="ti ${thumbIcon(p)}" aria-hidden="true"></i></div>
    <div class="body">
      <div class="name">${esc(p.name)}</div>
      <div class="desc">${esc(p.description)}</div>
      <div class="meta">${metaLine(p)} · ${esc(catLabel(p.category))}</div>
      ${actionBtn(p)}${progressHTML(p)}
    </div></div>`;
}
function rowHTML(p){
  return `<div class="row" data-id="${esc(p.id)}" tabindex="0" aria-label="${esc(p.name)} : voir la fiche">
    <div class="thumb ${thumbAccent(p)}"><i class="ti ${thumbIcon(p)}" aria-hidden="true"></i></div>
    <div class="rbody"><div class="name">${esc(p.name)}</div><div class="desc">${esc(p.description)}</div>${progressHTML(p)}</div>
    <div class="rmeta">${metaLine(p)}</div>
    <div class="ract">${actionBtn(p)}</div></div>`;
}
const TCOLS = [{k:"name", l:"Nom"}, {k:"category", l:"Catégorie"}, {k:"version", l:"Version"}];
function sortList(list){
  const v = p => SORT.col === "category" ? catLabel(p.category) : SORT.col === "version" ? p.version : p.name;
  return [...list].sort((a, b) => String(v(a)).localeCompare(String(v(b)), "fr", {numeric:true}) * SORT.dir);
}
function tableHTML(list){
  const head = TCOLS.map(c => `<th data-col="${c.k}" class="${SORT.col === c.k ? "sorted " + (SORT.dir > 0 ? "asc" : "desc") : ""}" tabindex="0">${c.l}</th>`).join("") + "<th></th>";
  const rows = sortList(list).map(p => `<tr data-id="${esc(p.id)}">
      <td class="tn"><span class="tn-in"><i class="ti ${thumbIcon(p)} acc-ic-${accentOf(p)}" aria-hidden="true"></i><span>${esc(p.name)}</span></span></td>
      <td class="tc">${esc(catLabel(p.category))}</td>
      <td class="tv">${BUSY[p.id] ? Math.round(pct(BUSY[p.id].pct)) + " %" : metaLine(p)}</td>
      <td class="ta">${actionBtn(p)}</td></tr>`).join("");
  return `<table class="cat-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}
function filtered(){
  const t = norm(FILTER.term.trim());
  return visibleProducts().filter(p =>
    (FILTER.cat === "all" || p.category === FILTER.cat) &&
    (FILTER.state === "all" || (FILTER.state === "installed" ? p.installed_version != null : (p.status === "update" || p.status === "repair"))) &&
    (!t || norm(p.name).includes(t) || norm(p.description).includes(t)));
}
function renderChips(){
  const used = new Set(visibleProducts().map(p => p.category));
  const cats = [{id:"all", label:"Tous", icon:"ti-apps"}].concat(((CATALOG && CATALOG.categories) || []).filter(c => used.has(c.id)));
  if (!cats.some(c => c.id === FILTER.cat)) FILTER.cat = "all";
  $("#filterChips").innerHTML = cats.map(c => `<button class="chip ${FILTER.cat === c.id ? "active" : ""}" data-cat="${esc(c.id)}" aria-pressed="${FILTER.cat === c.id}">
    ${safeIcon(c.icon) ? `<i class="ti ${safeIcon(c.icon)}" aria-hidden="true"></i>` : ""}${esc(c.label)}</button>`).join("");
}
function renderPacks(){
  const packs = (CATALOG && CATALOG.packs) || [];
  const row = $("#packsRow");
  row.classList.toggle("hidden", !packs.length);
  row.innerHTML = packs.map(pk => {
    const ids = Array.isArray(pk.products) ? pk.products : [];
    const names = ids.map(id => (findProduct(id) || {}).name).filter(Boolean);
    const done = pk.status === "complete", busy = ids.some(id => BUSY[id]);
    const total = Number(pk.total) || ids.length, cnt = Number(pk.done) || 0;
    return `<div class="pack" data-pid="${esc(pk.id)}">
      <div class="pack-ico" style="background:var(--${safeAccent(pk.accent) || "purple"})"><i class="ti ${safeIcon(pk.icon) || "ti-package"}" aria-hidden="true"></i></div>
      <div class="pack-body"><div class="pack-name">${esc(pk.name)}</div><div class="pack-desc">${esc(pk.description)}</div>
        ${names.length ? `<div class="pack-items" title="${esc(names.join(", "))}">${esc(names.join(" · "))}</div>` : ""}
        <div class="pack-count">${cnt}/${total} ${plural(cnt, "installé", "installés")}</div></div>
      <button class="btn sm ${done ? "" : "ice"}" data-pack ${done || busy ? "disabled" : ""}>${done ? '<i class="ti ti-check" aria-hidden="true"></i>Complet'
        : busy ? '<i class="ti ti-loader-2 spin" aria-hidden="true"></i>En cours' : '<i class="ti ti-download" aria-hidden="true"></i>Installer'}</button>
    </div>`;
  }).join("");
}
function renderGrid(){
  const list = filtered(), g = $("#catalogGrid");
  g.className = "grid view-" + VIEW;
  if (VIEW === "list") g.innerHTML = list.map(rowHTML).join("");
  else if (VIEW === "table") g.innerHTML = list.length ? tableHTML(list) : "";
  else g.innerHTML = list.map(cardHTML).join("");
  $("#catalogEmpty").classList.toggle("hidden", list.length > 0 || !CATALOG);
  $$(".view-toggle button").forEach(b => b.classList.toggle("active", b.dataset.view === VIEW));
  $$("#stateFilter button").forEach(b => b.classList.toggle("active", b.dataset.state === FILTER.state));
}
const renderGridSoon = debounce(renderGrid, 120);
function renderAddons(){
  if (!CATALOG){ $("#catalogGrid").innerHTML = `<div class="boot-loading"><i class="ti ti-loader-2 spin" aria-hidden="true"></i>Chargement du catalogue…</div>`; return; }
  renderPacks(); renderChips(); renderGrid();
  const all = visibleProducts(), inst = all.filter(p => p.installed_version != null).length, n = addonUpdates().length;
  $("#addonsCount").textContent = all.length + " " + plural(all.length, "addon", "addons") + " · " + inst + " " + plural(inst, "installé", "installés")
    + (n ? " · " + n + " " + plural(n, "mise à jour", "mises à jour") : "");
  $("#updateAllBtn").classList.toggle("hidden", !n || !CATALOG.wow_valid);
}
function needGame(){ toast("Choisis d'abord le dossier du jeu.", "err"); switchTab("settings"); }
function markBusy(ids){ (ids || []).forEach(id => { if (!BUSY[id]) BUSY[id] = {pct:0, msg:"En attente…"}; }); renderAddons(); renderHome(); }
async function installProduct(id){
  const p = findProduct(id);
  if (!p || BUSY[id] || p.status === "uptodate") return;
  if (!CATALOG.wow_valid) return needGame();
  markBusy([id]);
  const r = await call("install_product", id);
  if (!r.started){ delete BUSY[id]; renderAddons(); renderHome(); toast(r.error || "Installation impossible.", "err", p.name); }
}
async function installPack(pid){
  if (!CATALOG.wow_valid) return needGame();
  const pk = ((CATALOG.packs) || []).find(x => x.id === pid);
  const r = await call("install_pack", pid);
  if (!r.started){ toast(r.error || "Installation impossible.", "err", pk ? pk.name : ""); return; }
  const ids = Array.isArray(r.ids) ? r.ids : [];
  if (!ids.length) toast("Ce pack est déjà installé.", "ok", pk ? pk.name : "");
  else { markBusy(ids); toast("Installation du pack…", "info", pk ? pk.name : ""); }
}
async function updateAll(){
  if (!CATALOG || !CATALOG.wow_valid) return needGame();
  const r = await call("install_all");
  if (r.started === false){ toast(r.error || "Mise à jour impossible.", "err"); return; }
  const ids = Array.isArray(r.ids) ? r.ids : [];
  markBusy(ids);
  if (!ids.length) toast("Tout est déjà à jour.", "ok");
  else toast(ids.length + " " + plural(ids.length, "mise à jour lancée", "mises à jour lancées") + ".", "info");
}
on("onProgress", (id, p, msg) => {
  if (!BUSY[id]) BUSY[id] = {pct:0, msg:""};
  BUSY[id].pct = pct(p); BUSY[id].msg = String(msg || "");
  let missing = false;
  $$(`[data-id="${sel(id)}"]`).forEach(el => {
    const bar = el.querySelector(".progress > i");
    if (!bar){ missing = true; return; }
    bar.style.width = BUSY[id].pct + "%";
    const m = el.querySelector(".progress-msg"); if (m) m.textContent = BUSY[id].msg;
  });
  if (missing || VIEW === "table") renderGridSoon();
});
on("onDone", (id, ok, msg) => {
  delete BUSY[id];
  const p = findProduct(id);
  if (ok && p){ p.status = "uptodate"; p.installed_version = p.version; }   // en attendant le rechargement
  if (!quiet()) toast(msg || (ok ? "Installé." : "Échec de l'installation."), ok ? "ok" : "err", p ? p.name : "");
  renderAddons(); renderHome(); renderSidebar();
  reloadSoon();
});

/* ---- fiche d'un addon ---- */
let PM_ID = null;
function openProduct(id){
  const p = findProduct(id); if (!p) return;
  PM_ID = id;
  $("#pmName").textContent = p.name;
  $("#pmSub").textContent = catLabel(p.category) + " · v" + p.version
    + (p.status === "update" && p.installed_version != null ? " (tu as la v" + p.installed_version + ")" : "");
  $("#pmDesc").textContent = p.long_description || p.description || "";
  const th = $("#pmThumb"); th.className = "pm-thumb thumb " + thumbAccent(p);
  th.innerHTML = `<i class="ti ${thumbIcon(p)}" aria-hidden="true"></i>`;
  const hist = Array.isArray(p.history) ? p.history : [];
  $("#pmHistory").innerHTML = hist.length ? hist.map(h => `<div class="hist"><div class="hv">v${esc(h.version)}</div><div class="hn">${esc(h.notes)}</div></div>`).join("")
    : `<p class="muted">Pas d'historique.</p>`;
  const acts = [];
  if (p.status !== "uptodate" && !BUSY[id]) acts.push(`<button class="btn gold" data-pm="install"><i class="ti ti-download" aria-hidden="true"></i>${{update:"Mettre à jour", repair:"Réparer"}[p.status] || "Installer"}</button>`);
  if (p.installed_version != null) acts.push(`<button class="btn danger" data-pm="uninstall"><i class="ti ti-trash" aria-hidden="true"></i>Désinstaller</button>`);
  if (p.changelog_url) acts.push(`<button class="btn ghost" data-pm="changelog"><i class="ti ti-external-link" aria-hidden="true"></i>Notes de version</button>`);
  $("#pmActions").innerHTML = acts.join("");
  openModal("productModal");
}
async function productAction(btn){
  const id = PM_ID, p = findProduct(id); if (!p) return;
  const a = btn.dataset.pm;
  if (a === "install"){ closeModal("productModal"); installProduct(id); }
  else if (a === "changelog") openUrl(p.changelog_url);
  else if (a === "uninstall"){
    if (!btn.dataset.confirm){
      btn.dataset.confirm = "1"; btn.innerHTML = '<i class="ti ti-alert-triangle" aria-hidden="true"></i>Confirmer la désinstallation';
      setTimeout(() => { if (btn.isConnected){ delete btn.dataset.confirm; btn.innerHTML = '<i class="ti ti-trash" aria-hidden="true"></i>Désinstaller'; } }, 4000);
      return;
    }
    btn.disabled = true;
    const r = await call("uninstall_product", id);
    if (r.ok){ toast("Désinstallé.", "ok", p.name); closeModal("productModal"); reload(); }
    else { btn.disabled = false; toast(r.error || "Désinstallation impossible.", "err", p.name); }
  }
}

/* ================================================================ 12. Français */
const FR_BLOCKS = [
  {id:"jeu", title:"Jeu", icon:"ti-world", desc:"Le jeu d'origine de Blizzard", rows:[
    {k:"jeu", label:"Jeu de base", sub:"Menus, quêtes, PNJ", icon:"ti-world", pack:true},
    {k:"voix", label:"Voix", sub:"Dialogues parlés", icon:"ti-microphone", pack:true},
    {k:"sorts_blizzard", label:"Sorts Blizzard", sub:"Noms et descriptions officiels", icon:"ti-wand", pack:true},
    {k:"reputations", label:"Réputations", sub:"Factions et niveaux", icon:"ti-flag"},
    {k:"hauts_faits", label:"Hauts faits et titres", icon:"ti-trophy"},
    {k:"metiers", label:"Métiers", sub:"Recettes et compétences", icon:"ti-hammer"},
  ]},
  {id:"ebon", title:"Contenu Ebonhold", icon:"ti-snowflake", desc:"Ce que le serveur ajoute", rows:[
    {k:"echoes_desc", label:"Echoes : descriptions", icon:"ti-sparkles"},
    {k:"echoes_noms", label:"Echoes : noms", sub:"Conseillé : anglais", icon:"ti-sparkles"},
    {k:"soultree_desc", label:"Soul Tree : descriptions", icon:"ti-binary-tree"},
    {k:"soultree_noms", label:"Soul Tree : noms", sub:"Conseillé : anglais", icon:"ti-binary-tree"},
    {k:"affixes_desc", label:"Affixes : descriptions", sub:"Et leur effet sur les objets", icon:"ti-diamond"},
    {k:"affixes_noms", label:"Affixes : noms", sub:"Conseillé : anglais", icon:"ti-diamond"},
    {k:"tomes", label:"Tomes", icon:"ti-book-2"},
  ]},
  {id:"ui", title:"Interface", icon:"ti-layout-dashboard", desc:"Les fenêtres du serveur", rows:[
    {k:"interface", label:"Interface du serveur", sub:"Fenêtres Echoes, Soul Tree, Prestige, Callboard, Enclume", icon:"ti-layout-dashboard"},
  ]},
];
const FR_KEYS = FR_BLOCKS.flatMap(b => b.rows.map(r => r.k));
const FR_LABEL = Object.fromEntries(FR_BLOCKS.flatMap(b => b.rows.map(r => [r.k, r.label])));
const PACK_KEYS = ["jeu", "voix", "sorts_blizzard"];       // demandent le pack FR (2,6 Go)
const NAME_KEYS = ["echoes_noms", "soultree_noms", "affixes_noms"];
const PRESETS = [
  {id:"recommande", label:"Recommandé", icon:"ti-star", desc:"Tout en français, sauf les noms Ebonhold (echoes, Soul Tree, affixes), gardés en anglais."},
  {id:"tout_fr", label:"Tout en français", icon:"ti-language", desc:"Le jeu et tout le contenu Ebonhold en français, noms compris."},
  {id:"tout_en", label:"Tout en anglais", icon:"ti-world", desc:"Le jeu d'origine, sans traduction."},
];
function localPreset(id){
  const s = {};
  FR_KEYS.forEach(k => s[k] = id === "tout_en" ? "en" : "fr");
  if (id === "recommande") NAME_KEYS.forEach(k => s[k] = "en");
  s.nom_anglais = id === "tout_fr";
  return s;
}
const presetOf = id => normFr({...localPreset(id), ...((FR && FR.presets && FR.presets[id]) || {})});
function normFr(s){ const o = {}; s = s || {}; FR_KEYS.forEach(k => o[k] = s[k] === "en" ? "en" : "fr"); o.nom_anglais = !!s.nom_anglais; return o; }
const sameFr = (a, b) => FR_KEYS.every(k => a[k] === b[k]);
const matchPreset = s => s ? ((PRESETS.find(p => sameFr(s, presetOf(p.id))) || {}).id || "") : "";
const anyNameFr = s => NAME_KEYS.some(k => s[k] === "fr");
const needsPack = s => !!s && PACK_KEYS.some(k => s[k] === "fr");
function frDirty(){ return !!(FR && FR_CUR) && [...FR_KEYS, "nom_anglais"].some(k => FR_CUR[k] !== normFr(FR.settings)[k]); }

let _frLoading = null;
async function loadFr(opts = {}){
  if (_frLoading){ await _frLoading; if (!opts.reset) return; }
  _frLoading = (async () => {
    const r = await call("get_fr_settings");
    if (r && r.settings){
      const keep = frDirty() && !opts.reset;
      FR = r; FR_ERR = "";
      if (!keep || !FR_CUR) FR_CUR = normFr(r.settings);
    } else {
      FR_ERR = (r && r.error) || "Réglages de langue indisponibles.";
      if (opts.reset || !FR){ FR = null; FR_CUR = null; }   // ne jamais garder des données d'une autre source
    }
    renderFr(); renderHome(); renderSidebar();
    if (wizardOpen()) renderWiz();
  })();
  try { await _frLoading; } finally { _frLoading = null; }
}
function presetsHTML(active){
  return PRESETS.map(p => `<button class="preset ${active === p.id ? "active" : ""}" data-preset="${p.id}" aria-pressed="${active === p.id}">
      <i class="ti ti-circle-check p-check" aria-hidden="true"></i>
      <span class="p-head"><i class="ti ${p.icon}" aria-hidden="true"></i>${esc(p.label)}</span>
      <span class="p-desc">${esc(p.desc)}</span>
      ${p.id === "recommande" ? '<span class="tag gold">conseillé</span>' : ""}
    </button>`).join("");
}
function renderFr(){
  const un = $("#frUnavailable");
  if (!FR || !FR_CUR){
    un.innerHTML = FR_ERR ? `<i class="ti ti-alert-triangle" aria-hidden="true"></i><span>${esc(FR_ERR)}</span>` : "";
    un.classList.toggle("hidden", !FR_ERR);
    $("#frPresets").innerHTML = ""; $("#frState").innerHTML = ""; $("#frPackBox").classList.add("hidden");
    $("#frBlocks").innerHTML = FR_ERR ? "" : `<div class="boot-loading"><i class="ti ti-loader-2 spin" aria-hidden="true"></i>Lecture des réglages…</div>`;
    updateFrBar(); return;
  }
  un.classList.add("hidden");
  // garder le focus clavier sur l'interrupteur cliqué (le bloc est redessiné)
  const ae = document.activeElement, fk = ae && ae.closest && ae.closest(".fr-row") ? ae.closest(".fr-row").dataset.k : null, fv = ae && ae.dataset ? ae.dataset.v : null;
  const fp = ae && ae.dataset ? ae.dataset.preset : null;
  $("#frState").innerHTML = frStateHTML();
  const m = matchPreset(FR_CUR);
  $("#frPresets").innerHTML = presetsHTML(m) + (m ? "" : `<p class="muted" style="grid-column:1/-1">Réglage personnalisé.</p>`);
  renderPackBox(); renderFrBlocks(); updateFrBar();
  if (fk && fv){ const b = $(`.fr-row[data-k="${sel(fk)}"] .switch button[data-v="${sel(fv)}"]`); if (b) b.focus(); }
  else if (fp){ const b = $(`#frPresets [data-preset="${sel(fp)}"]`); if (b) b.focus(); }
}
function frStateHTML(){
  const s = FR.state || {};
  if (s.applied && s.up_to_date) return `<div class="notice ok"><i class="ti ti-circle-check" aria-hidden="true"></i><span>${esc(s.server_changed && s.message ? s.message : "Réglages appliqués" + (s.last_applied ? " le " + s.last_applied : "") + ".")}</span></div>`;
  if (s.applied) return `<div class="notice warn"><i class="ti ti-refresh-alert" aria-hidden="true"></i><span><strong>À réappliquer.</strong> ${esc(s.message || "Le serveur a été mis à jour.")}</span></div>`;
  return `<div class="notice info"><i class="ti ti-info-circle" aria-hidden="true"></i><span>${esc(s.message || "Pas encore appliqué : choisis tes réglages, puis Appliquer.")}</span></div>`;
}
function renderPackBox(){
  const box = $("#frPackBox");
  const show = FR && !FR.pack_present && (needsPack(FR_CUR) || PACK.busy);
  box.classList.toggle("hidden", !show); if (!show) return;
  const which = PACK_KEYS.filter(k => FR_CUR[k] === "fr").map(k => FR_LABEL[k]).join(", ");
  if (PACK.busy){
    box.innerHTML = `<div class="pb-row"><i class="ti ti-cloud-download pb-ico" aria-hidden="true"></i><div class="pb-txt">
        <div class="pb-title">Installation du pack FR (2,6 Go)…</div>
        <div class="pb-sub">Ça peut être long. Laisse le launcher ouvert ; tu peux continuer à l'utiliser.</div></div></div>
      <div class="progress"><i id="frPackBar" style="width:${pct(PACK.pct)}%"></i></div><div class="pb-msg" id="frPackMsg">${esc(PACK.msg)}</div>`;
  } else if (FR.pack_installable){
    box.innerHTML = `<div class="pb-row"><i class="ti ti-language pb-ico" aria-hidden="true"></i><div class="pb-txt">
        <div class="pb-title">Il manque le pack FR</div>
        <div class="pb-sub">Nécessaire pour : ${esc(which)}. Le launcher le télécharge et l'installe pour toi.</div></div>
        <button class="btn gold" data-fr="pack"><i class="ti ti-download" aria-hidden="true"></i>Installer le pack FR (2,6 Go)</button></div>
      ${PACK.err ? `<div class="notice err"><i class="ti ti-alert-triangle" aria-hidden="true"></i><span>${esc(PACK.err)}</span></div>` : ""}`;
  } else {
    box.innerHTML = `<div class="pb-row"><i class="ti ti-cloud-off pb-ico" aria-hidden="true"></i><div class="pb-txt">
        <div class="pb-title">Le pack FR n'est pas disponible pour l'instant</div>
        <div class="pb-sub">${esc(FR.pack_note || "")} En attendant, mets ces lignes en anglais : ${esc(which)}.</div></div>
        <button class="btn ghost" data-fr="pack-en"><i class="ti ti-world" aria-hidden="true"></i>Mettre ces lignes en anglais</button></div>`;
  }
}
function renderFrBlocks(){
  const s = FR_CUR, saved = normFr(FR.settings), dis = FR_APPLYING;
  $("#frBlocks").innerHTML = FR_BLOCKS.map(b => `<section class="fr-block">
      <header class="fr-block-head"><i class="ti ${b.icon}" aria-hidden="true"></i><h3>${esc(b.title)}</h3>
        <span class="fb-desc">${esc(b.desc)}</span>
        ${b.rows.length > 1 ? `<span class="fb-all"><button class="link-btn" data-block="${b.id}" data-v="fr" ${dis ? "disabled" : ""}>Tout FR</button><button class="link-btn" data-block="${b.id}" data-v="en" ${dis ? "disabled" : ""}>Tout EN</button></span>` : ""}
      </header>
      ${b.rows.map(r => frRowHTML(r, s, saved, dis)).join("")}
      ${b.id === "ui" ? nameOptHTML(s, saved, dis) : ""}
    </section>`).join("");
}
function frRowHTML(r, s, saved, dis){
  const v = s[r.k], changed = v !== saved[r.k];
  const tag = r.pack ? `<span class="tag ${FR.pack_present ? "ice" : "warn"}" title="Demande le pack FR (2,6 Go)">pack FR</span>` : "";
  return `<div class="fr-row ${changed ? "changed" : ""}" data-k="${r.k}"><i class="ti ${r.icon}" aria-hidden="true"></i>
    <div class="fr-lbl"><div class="fr-name">${esc(r.label)} ${tag}</div>${r.sub ? `<div class="fr-sub">${esc(r.sub)}</div>` : ""}</div>
    <div class="switch" role="radiogroup" aria-label="${esc(r.label)}">
      <button role="radio" data-v="fr" aria-checked="${v === "fr"}" class="${v === "fr" ? "on" : ""}" ${dis ? "disabled" : ""}>FR</button>
      <button role="radio" data-v="en" aria-checked="${v === "en"}" class="${v === "en" ? "on" : ""}" ${dis ? "disabled" : ""}>EN</button>
    </div></div>`;
}
function nameOptHTML(s, saved, dis){
  const can = anyNameFr(s), off = !can || dis;
  return `<div class="fr-row opt ${s.nom_anglais !== saved.nom_anglais ? "changed" : ""}"><i class="ti ti-letter-case" aria-hidden="true"></i>
    <div class="fr-lbl">
      <label class="check ${off ? "disabled" : ""}"><input type="checkbox" id="frNomEn" ${s.nom_anglais ? "checked" : ""} ${off ? "disabled" : ""}><span>Afficher aussi le nom anglais</span></label>
      <div class="fr-sub" style="margin:3px 0 0 32px">${can ? "Une ligne grise « EN : … » dans les infobulles, pratique pour suivre les guides."
        : "Utile seulement si des noms (echoes, Soul Tree, affixes) sont en français."}</div>
    </div></div>`;
}
function updateFrBar(){
  const d = frDirty(), el = $("#frDirty");
  const blockPack = !!(FR && FR_CUR && needsPack(FR_CUR) && !FR.pack_present);
  el.className = "fr-dirty" + (d || frNeedsReapply() ? " on" : "");
  el.innerHTML = !FR ? "" : FR_APPLYING ? '<i class="ti ti-loader-2 spin" aria-hidden="true"></i>Application en cours…'
    : PACK.busy ? '<i class="ti ti-loader-2 spin" aria-hidden="true"></i>Installation du pack FR en cours…'
    : blockPack ? '<i class="ti ti-alert-triangle" aria-hidden="true"></i>Installe d\'abord le pack FR, ou passe ces lignes en EN.'
    : d ? '<i class="ti ti-point-filled" aria-hidden="true"></i>Modifications pas encore appliquées'
    : frNeedsReapply() ? '<i class="ti ti-refresh-alert" aria-hidden="true"></i>Tes réglages sont à réappliquer'
    : '<i class="ti ti-check" aria-hidden="true"></i>Réglages enregistrés';
  $("#frApply").disabled = !FR || FR_APPLYING || blockPack || PACK.busy;
  $("#frRevert").classList.toggle("hidden", !d || FR_APPLYING);
}
function setFr(k, v, noRender){
  if (FR_APPLYING || !FR_CUR || !FR_KEYS.includes(k)) return;
  const hadNames = anyNameFr(FR_CUR);
  FR_CUR[k] = v === "en" ? "en" : "fr";
  // « Afficher aussi le nom anglais » s'active de lui-même quand un premier nom passe en FR.
  if (NAME_KEYS.includes(k) && FR_CUR[k] === "fr" && !hadNames) FR_CUR.nom_anglais = true;
  if (!noRender) renderFr();
}
function frLog(m){
  if (m == null) return;
  FR_LAST = String(m);
  const w = $("#frLogWrap"), l = $("#frLog");
  w.classList.remove("hidden"); l.textContent += FR_LAST + "\n"; l.scrollTop = l.scrollHeight;
  if (FR_APPLYING){ const d = $("#card-fr .scard-detail"); if (d) d.textContent = FR_LAST; }
}
function frLogClear(){ $("#frLog").textContent = ""; $("#frLogWrap").classList.add("hidden"); }
async function applyFr(settings = FR_CUR, source = "tab"){
  if (!FR || FR_APPLYING) return {started:false, error:"Déjà en cours."};
  if (!CATALOG || !CATALOG.wow_valid){ if (source !== "wizard") needGame(); return {started:false, error:"Dossier du jeu introuvable."}; }
  if (needsPack(settings) && !FR.pack_present){
    if (source !== "wizard"){ toast("Il faut d'abord le pack FR (2,6 Go) pour le jeu de base, les voix et les sorts Blizzard.", "warn", "Français"); switchTab("fr"); }
    return {started:false, error:"Pack FR absent."};
  }
  FR_APPLYING = true; frLogClear(); frLog("Application des réglages…");
  renderFr(); renderHome();
  if (source === "tab") $("#frLogWrap").scrollIntoView({block:"nearest", behavior:"smooth"});
  const r = await call("apply_fr", {...settings});
  if (!r.started){
    FR_APPLYING = false; frLog("✗ " + (r.error || "Erreur."));
    renderFr(); renderHome();
    if (source !== "wizard") toast(r.error || "Impossible d'appliquer.", "err", "Français");
  }
  return r;
}
on("onFrLog", m => frLog(m));
on("onFrDone", (ok, msg) => {
  const mine = FR_APPLYING; FR_APPLYING = false;
  frLog((ok ? "✓ " : "✗ ") + (msg || ""));
  if (mine && !quiet()) toast(msg || (ok ? "Réglages appliqués." : "Échec."), ok ? "ok" : "err", "Français");
  loadFr({reset: !!ok});
});
// Poussé au démarrage quand le serveur a été mis à jour (réglages réappliqués, ou à réappliquer).
on("onFrState", st => {
  if (!st || typeof st !== "object") return;
  if (FR) FR.state = st; else loadFr();
  renderFr(); renderHome(); renderSidebar();
  if (st.message) toast(st.message, st.up_to_date ? "ok" : "warn", "Français");
});
async function installFrPack(){
  if (PACK.busy) return;
  if (!CATALOG || !CATALOG.wow_valid) return needGame();
  PACK = {busy:true, pct:0, msg:"Préparation…", err:""}; renderFr();
  const r = await call("install_fr_pack");
  if (!r.started){ PACK = {busy:false, pct:0, msg:"", err: r.error || "Installation impossible."}; renderFr(); toast(PACK.err, "err", "Pack FR"); }
}
on("onPackProgress", (p, msg) => {
  PACK.busy = true; PACK.pct = pct(p); PACK.msg = String(msg || "");
  const b = $("#frPackBar");
  if (b){ b.style.width = PACK.pct + "%"; $("#frPackMsg").textContent = PACK.msg; } else if (TAB === "fr") renderFr();
});
on("onPackDone", (ok, msg) => {
  PACK = {busy:false, pct: ok ? 100 : 0, msg:"", err: ok ? "" : String(msg || "Erreur.")};
  if (!quiet()) toast(msg || (ok ? "Pack FR installé." : "Échec."), ok ? "ok" : "err", "Pack FR");
  if (ok && FR) FR.pack_present = true;
  renderFr(); loadFr();
});

/* ================================================================ 13. Signaler un bug / proposer une idée */
const REP = {kind:"bug", attach:[], sizes:{}, recent:[], thumbs:{}, info:null, logTouched:false, sending:false};
const LOG_EXPLAIN = "Le journal est le carnet de bord du launcher : il y note ce qu'il fait (installations, erreurs). Il aide à comprendre ton souci. Les chemins de tes dossiers sont anonymisés.";
function showRepView(v){
  $("#repForm").classList.toggle("hidden", v !== "form");
  $("#repSending").classList.toggle("hidden", v !== "sending");
  $("#repDone").classList.toggle("hidden", v !== "done");
  $("#repFail").classList.toggle("hidden", v !== "fail");
}
function openReport(kind = "bug"){
  if (!REP.sending){ showRepView("form"); setRepKind(kind); loadRecent(); renderAttach(); }
  openModal("reportModal");
  setTimeout(() => { if (!REP.sending) $("#repText").focus(); }, 60);
}
function setRepKind(kind){
  REP.kind = kind === "suggestion" ? "suggestion" : "bug";
  const bug = REP.kind === "bug";
  $$("#repKind button").forEach(b => { const act = b.dataset.kind === REP.kind; b.classList.toggle("active", act); b.setAttribute("aria-checked", act); });
  $("#repTitleTxt").textContent = bug ? "Signaler un bug" : "Proposer une idée";
  $("#repTitleIcon").className = "ti " + (bug ? "ti-bug" : "ti-bulb");
  $("#repTextLbl").textContent = bug ? "Que s'est-il passé ?" : "Quelle est ton idée ?";
  $("#repText").placeholder = bug
    ? "Ce que tu faisais, ce que tu attendais, ce qui s'est passé à la place… Plus c'est précis, plus c'est facile à corriger."
    : "Quel outil ou quel ajout te manque, et à quoi il servirait…";
  // Journal coché pour un bug ; décoché pour une idée (sauf si le joueur a choisi lui-même).
  if (!REP.logTouched && !$("#repLog").disabled) $("#repLog").checked = bug;
  $("#repErr").classList.add("hidden"); $("#repText").classList.remove("invalid");
  updateCount(); loadReportInfo();
}
async function loadReportInfo(){
  const kind = REP.kind;
  $("#repPreviewTxt").textContent = "Chargement…";
  const r = await call("report_info", kind);
  if (kind !== REP.kind) return;
  REP.info = r;
  $("#repPreviewTxt").textContent = r.infos_preview || (r.error ? "Infos indisponibles : " + r.error : "—");
  const w = $("#repWait");
  if (r.can_send === false){
    const n = Math.ceil(Number(r.wait_minutes) || 0);
    // Anti-spam : délai d'attente ; sinon envoi indisponible (message du moteur, ex. pas de clé d'envoi).
    w.innerHTML = n > 0
      ? `<i class="ti ti-clock" aria-hidden="true"></i><span>Tu pourras renvoyer un signalement dans ${n} min.</span>`
      : `<i class="ti ti-info-circle" aria-hidden="true"></i><span>${esc(r.message || "Envoi indisponible pour le moment.")}</span>`;
    w.classList.remove("hidden");
  } else w.classList.add("hidden");
  const logOk = r.log_available !== false, lc = $("#repLog");
  lc.disabled = !logOk; if (!logOk) lc.checked = false;
  lc.closest(".check").classList.toggle("disabled", !logOk);
  $("#repLogExplain").textContent = logOk ? LOG_EXPLAIN : "Pas encore de journal sur ce PC : rien à joindre.";
  $("#repSend").disabled = r.can_send === false;
}
function updateCount(){
  const n = $("#repText").value.trim().length, c = $("#repCount");
  c.textContent = n < 10 ? n + " / 10 caractères minimum" : n + " caractères";
  c.classList.toggle("short", n > 0 && n < 10);
  if (n >= 10){ $("#repErr").classList.add("hidden"); $("#repText").classList.remove("invalid"); }
}
async function loadRecent(){
  const r = await call("recent_captures");
  REP.recent = (Array.isArray(r.items) ? r.items : []).filter(it => it && typeof it.path === "string").slice(0, 10);
  REP.recent.forEach(it => { if (it.size) REP.sizes[it.path] = it.size; });
  $("#repRecentWrap").classList.toggle("hidden", !REP.recent.length);
  renderRecent();
  for (const it of REP.recent){                      // vignettes une par une, sans bloquer
    if (it.path in REP.thumbs){ paintThumb(it.path); continue; }
    REP.thumbs[it.path] = "";
    const t = await call("thumbnail", it.path);
    REP.thumbs[it.path] = safeImg(t && t.data_url);
    paintThumb(it.path);
  }
}
function renderRecent(){
  $("#repRecent").innerHTML = REP.recent.map((it, i) => {
    const onn = REP.attach.includes(it.path), name = it.name || baseName(it.path);
    const tip = name + (it.date ? " · " + it.date : "") + (it.size ? " · " + fmtSize(it.size) : "");
    return `<button class="rthumb ${onn ? "on" : ""}" data-ri="${i}" aria-pressed="${onn}" title="${esc(tip)}" aria-label="${esc(tip)}">
      <i class="ti ${VIDEO_EXT.test(it.path) ? "ti-movie" : "ti-photo"}" aria-hidden="true"></i>
      <span class="rcheck" aria-hidden="true"><i class="ti ti-check"></i></span><span class="rname">${esc(name)}</span></button>`;
  }).join("");
  REP.recent.forEach(it => paintThumb(it.path));
}
function paintThumb(path){
  const u = REP.thumbs[path]; if (!u) return;
  REP.recent.forEach((it, i) => {
    if (it.path !== path) return;
    const b = $(`#repRecent [data-ri="${i}"]`), ic = b && b.querySelector(":scope > i");
    if (ic){ const im = document.createElement("img"); im.alt = ""; im.src = u; ic.replaceWith(im); }   // src posé par propriété
  });
}
function toggleRecent(i){
  const it = REP.recent[i]; if (!it) return;
  const k = REP.attach.indexOf(it.path);
  if (k >= 0) REP.attach.splice(k, 1); else REP.attach.push(it.path);
  const b = $(`#repRecent [data-ri="${i}"]`);
  if (b){ b.classList.toggle("on", k < 0); b.setAttribute("aria-pressed", k < 0); }
  renderAttach();
}
async function pickAttachments(){
  const r = await call("pick_attachments");
  const paths = Array.isArray(r.paths) ? r.paths : [];
  if (r.error && !paths.length){ toast(r.error, "err"); return; }
  paths.forEach(p => { if (typeof p === "string" && p && !REP.attach.includes(p)) REP.attach.push(p); });
  renderAttach(); syncRecent();
}
function syncRecent(){ REP.recent.forEach((it, i) => { const b = $(`#repRecent [data-ri="${i}"]`); if (b){ const o = REP.attach.includes(it.path); b.classList.toggle("on", o); b.setAttribute("aria-pressed", o); } }); }
function renderAttach(){
  const ul = $("#repAttach");
  ul.innerHTML = REP.attach.map((p, i) => `<li><i class="ti ${VIDEO_EXT.test(p) ? "ti-movie" : "ti-photo"}" aria-hidden="true"></i>
      <span class="a-name" title="${esc(baseName(p))}">${esc(baseName(p))}</span><span class="a-size">${esc(fmtSize(REP.sizes[p]))}</span>
      <button class="btn ghost sm" data-ai="${i}" aria-label="Retirer ${esc(baseName(p))}"><i class="ti ti-x" aria-hidden="true"></i>Retirer</button></li>`).join("");
  ul.classList.toggle("hidden", !REP.attach.length);
  const n = REP.attach.length;
  $("#repAttachCount").textContent = n ? n + " " + plural(n, "fichier joint", "fichiers joints") : "";
}
function repError(msg){
  const e = $("#repErr");
  e.innerHTML = `<i class="ti ti-alert-circle" aria-hidden="true"></i>${esc(msg)}`;
  e.classList.remove("hidden");
}
async function sendReport(){
  if (REP.sending) return;
  const ta = $("#repText"), text = ta.value, n = text.trim().length;
  if (n < 10){ repError("Écris au moins 10 caractères (il en manque " + (10 - n) + ")."); ta.classList.add("invalid"); showRepView("form"); ta.focus(); return; }
  if (REP.info && REP.info.can_send === false) return;
  const lc = $("#repLog");
  REP.sending = true; lockModal("reportModal", true); showRepView("sending");
  $("#repSendMsg").textContent = "Préparation…"; $("#repBar").style.width = "0%";
  const r = await call("send_report", REP.kind, text, REP.attach.slice(), lc.checked && !lc.disabled);
  if (!r.started){ REP.sending = false; lockModal("reportModal", false); showRepView("form"); repError(r.error || "Envoi impossible."); }
}
on("onReportProgress", (p, msg) => { $("#repBar").style.width = pct(p) + "%"; if (msg) $("#repSendMsg").textContent = String(msg); });
on("onReportDone", (ok, number, msg) => {
  if (!REP.sending) return;
  REP.sending = false; lockModal("reportModal", false);
  if (ok){
    const num = String(number ?? "").replace(/\D/g, ""), tag = num ? "#" + num : "";
    $("#repDoneTitle").textContent = REP.kind === "bug" ? `Signalement ${tag} envoyé, merci !`.replace("  ", " ") : `Idée ${tag} envoyée, merci !`.replace("  ", " ");
    $("#repDoneSub").textContent = tag ? `Cite ${tag} sur le Discord si tu veux en parler.` : String(msg || "");
    $("#repText").value = ""; REP.attach = []; REP.logTouched = false; renderAttach(); updateCount();
    showRepView("done");
    if ($("#reportModal").classList.contains("hidden")) toast($("#repDoneTitle").textContent, "ok");
  } else { $("#repFailMsg").textContent = String(msg || "Erreur inconnue."); showRepView("fail"); }
});

/* ================================================================ 14. Aide */
function renderHelpLinks(){
  const links = ((CATALOG && CATALOG.links) || []).filter(l => l && l.url && l.label);
  const hasGit = links.some(l => /github\.com/.test(l.url));
  $("#helpLinks").innerHTML = links.map((l, i) => `<button class="btn ghost" data-link="${i}"><i class="ti ${safeIcon(l.icon) || "ti-link"}" aria-hidden="true"></i>${esc(l.label)}</button>`).join("")
    + (hasGit ? "" : `<button class="btn ghost" data-link="git"><i class="ti ti-brand-github" aria-hidden="true"></i>Code source (GitHub)</button>`)
    + `<button class="btn ghost" data-openlog="1"><i class="ti ti-file-text" aria-hidden="true"></i>Ouvrir le journal</button>`;
}
function helpLink(k){
  if (k === "git") return openUrl(GITHUB_URL);
  const links = ((CATALOG && CATALOG.links) || []).filter(l => l && l.url && l.label);
  const l = links[Number(k)]; if (l) openUrl(l.url);
}
function setHelpView(v){
  $$("#helpSeg button").forEach(b => b.classList.toggle("active", b.dataset.help === v));
  $("#helpFaq").classList.toggle("hidden", v !== "faq");
  $("#helpGuide").classList.toggle("hidden", v !== "guide");
}
function setGuidePage(p){
  $$("#guideNav button").forEach(b => b.classList.toggle("active", b.dataset.page === p));
  $$(".gpage").forEach(g => g.classList.toggle("hidden", g.dataset.page !== p));
}
// Capture absente (pas encore faite) : cadre « Capture à venir » à la place.
function bindShots(){
  $$(".shot img").forEach(img => {
    const miss = () => img.closest(".shot").classList.add("missing");
    img.addEventListener("error", miss);
    if (img.complete && !img.naturalWidth) miss();
  });
}

/* ================================================================ 15. Réglages et recherche du jeu */
function renderSettings(){
  const c = CATALOG; if (!c) return;
  $("#folderInput").value = c.wow_path || "";
  const fv = $("#folderValid");
  if (c.wow_valid){ fv.className = "folder-valid ok"; fv.innerHTML = '<i class="ti ti-circle-check" aria-hidden="true"></i>Dossier du jeu valide.'; }
  else if (c.wow_path){ fv.className = "folder-valid bad"; fv.innerHTML = '<i class="ti ti-alert-triangle" aria-hidden="true"></i>Ce dossier ne contient pas le jeu.'; }
  else { fv.className = "folder-valid bad"; fv.innerHTML = '<i class="ti ti-alert-triangle" aria-hidden="true"></i>Aucun dossier choisi.'; }
  $("#aboutVersion").textContent = "v" + c.launcher_version + (c.launcher_update ? " (v" + c.latest_launcher_version + " disponible)" : "");
  $("#aboutSource").textContent = (SRC[c.source] || SRC.local)[3];
}
// Composant réutilisé dans Réglages et dans l'assistant : détection rapide → consentement → scan → choix.
function createFinder(root, opts = {}){
  const S = {phase:"idle", cands:[], msg:"", err:"", none:false, source:""};
  const sortC = list => (Array.isArray(list) ? list : []).filter(c => c && typeof c.path === "string" && c.path)
    .sort((a, b) => (!!b.is_ebonhold - !!a.is_ebonhold) || (!!b.has_exe - !!a.has_exe));
  const browseBtn = `<button class="btn ghost" data-f="browse"><i class="ti ti-folder-open" aria-hidden="true"></i>Je le choisis moi-même</button>`;
  function candsHTML(){
    const cur = String((CATALOG && CATALOG.wow_path) || "").toLowerCase();
    return `<div class="cands">${S.cands.map((c, i) => {
      const isCur = cur && c.path.toLowerCase() === cur;
      return `<button class="cand ${c.is_ebonhold ? "" : "other"} ${isCur ? "current" : ""}" data-ci="${i}">
        <i class="ti ${isCur ? "ti-circle-check" : c.is_ebonhold ? "ti-snowflake" : "ti-folder"}" aria-hidden="true"></i>
        <span class="cand-body">
          <span class="cand-label">${esc(c.label || baseName(c.path))}
            ${c.is_ebonhold ? '<span class="tag gold">Ebonhold</span>' : '<span class="tag grey">Autre serveur</span>'}
            ${c.has_exe === false ? '<span class="tag warn">Wow.exe absent</span>' : ""}${isCur ? '<span class="tag ok">choisi</span>' : ""}</span>
          <span class="cand-path">${esc(c.path)}</span>${c.reason ? `<span class="cand-reason">${esc(c.reason)}</span>` : ""}
        </span>
        ${isCur ? "" : `<span class="btn sm ${c.is_ebonhold ? "gold" : "ghost"}">Choisir</span>`}
      </button>`; }).join("")}</div>`;
  }
  function consentHTML(){
    return (S.none ? `<div class="finder-status"><i class="ti ti-info-circle" aria-hidden="true"></i>Aucun jeu trouvé aux emplacements habituels.</div>` : "")
      + `<div class="consent"><h4><i class="ti ti-device-desktop-search" aria-hidden="true"></i>Rechercher le jeu sur ton PC ?</h4>
        <p>Le launcher va parcourir tes disques pour trouver <code>Wow.exe</code>. Ça peut prendre une minute ou deux, et rien n'est envoyé sur Internet.</p>
        <div class="btn-row"><button class="btn gold" data-f="scan"><i class="ti ti-radar" aria-hidden="true"></i>Rechercher sur mon PC</button>${browseBtn}</div></div>`;
  }
  function render(){
    let h = "";
    if (S.phase === "detecting") h = `<div class="finder-status"><i class="ti ti-loader-2 spin" aria-hidden="true"></i>Recherche aux emplacements habituels…</div>`;
    else if (S.phase === "results") h = `<div class="finder-status"><i class="ti ti-circle-check" aria-hidden="true"></i>${S.cands.length > 1 ? "Plusieurs jeux trouvés : choisis le bon." : "Jeu trouvé :"}</div>`
      + candsHTML() + `<div class="muted">${S.source === "quick" ? `<button class="link-btn" data-f="consent">Ce n'est pas le bon ? Rechercher sur mon PC</button> ou ` : "Pas dans la liste ? "}<button class="link-btn" data-f="browse">choisis-le toi-même</button></div>`;
    else if (S.phase === "consent") h = consentHTML();
    else if (S.phase === "scanning") h = `<div class="scan-box"><i class="ti ti-radar" aria-hidden="true"></i><div style="flex:1;min-width:0">
        <div style="font-weight:600">Recherche sur ton PC…</div><div class="scan-msg">${esc(S.msg)}</div></div>
        ${hasMethod("cancel_scan") ? '<button class="btn ghost sm" data-f="cancel">Arrêter</button>' : '<i class="ti ti-loader-2 spin" aria-hidden="true"></i>'}</div>`;
    else if (S.phase === "scan-none") h = `<div class="notice warn"><i class="ti ti-alert-triangle" aria-hidden="true"></i><span>Aucun jeu trouvé sur ton PC. Choisis le dossier toi-même.</span></div>
        <div class="btn-row" style="margin-top:0"><button class="btn gold" data-f="browse"><i class="ti ti-folder-open" aria-hidden="true"></i>Parcourir…</button></div>`;
    if (S.err) h += `<div class="notice err"><i class="ti ti-alert-triangle" aria-hidden="true"></i><span>${esc(S.err)}</span></div>`;
    root.innerHTML = h;
  }
  async function detect(){
    S.phase = "detecting"; S.err = ""; S.none = false; render();
    const r = await call("quick_detect"), c = sortC(r.candidates);
    if (c.length){ S.cands = c; S.phase = "results"; S.source = "quick"; }
    else { S.phase = "consent"; S.none = true; if (r.error) S.err = r.error; }
    render();
  }
  async function scan(){
    S.phase = "scanning"; S.msg = "Préparation…"; S.err = ""; render();
    const r = await call("scan_games");
    if (!r.started){ S.phase = "consent"; S.err = r.error || "Recherche impossible."; render(); }
  }
  on("onScanProgress", m => { if (S.phase !== "scanning") return; S.msg = String(m || ""); const el = root.querySelector(".scan-msg"); if (el) el.textContent = S.msg; });
  on("onScanDone", list => { if (S.phase !== "scanning") return; S.cands = sortC(list); S.source = "scan"; S.phase = S.cands.length ? "results" : "scan-none"; render(); });
  async function done(path){ S.err = ""; toast("Dossier du jeu enregistré.", "ok"); await reload(); loadFr(); render(); if (opts.onPicked) opts.onPicked(path); }
  async function pick(i){
    const c = S.cands[i]; if (!c) return;
    const r = await call("set_wow_path", c.path);
    if (r.ok === false){ S.err = r.error || "Ce dossier ne convient pas."; render(); return; }
    done(c.path);
  }
  async function browse(){
    const r = await call("choose_folder");
    if (r.ok) done(r.path);
    else if (r.error){ S.err = r.error; render(); toast(r.error, "err"); }
  }
  root.addEventListener("click", e => {
    const c = e.target.closest("[data-ci]"); if (c) return pick(Number(c.dataset.ci));
    const f = e.target.closest("[data-f]"); if (!f) return;
    const a = f.dataset.f;
    if (a === "scan") scan();
    else if (a === "browse") browse();
    else if (a === "consent"){ S.phase = "consent"; S.none = false; S.err = ""; render(); }
    else if (a === "cancel"){ call("cancel_scan"); S.phase = "consent"; S.none = false; render(); }
  });
  return {detect, scan, browse, render};
}
let settingsFinder = null;

/* ================================================================ 16. Assistant de démarrage */
const WIZ = {step:1, preset:"recommande", dlPack:true, packs:null, finder:null, run:[]};
const wizardOpen = () => !$("#wizard").classList.contains("hidden");
function openWizard(){
  if (wizardOpen()) return;
  WIZ.step = 1; WIZ.packs = null; WIZ.dlPack = true;
  WIZ.preset = (FR && FR.state && FR.state.applied && matchPreset(normFr(FR.settings))) || "recommande";
  MSTACK.slice().forEach(id => closeModal(id));
  $("#wizard").classList.remove("hidden"); $("#app").inert = true;
  WIZ.needDetect = true;      // détection lancée dès que le catalogue (dossier actuel) est connu
  renderWiz();
  setTimeout(() => { const b = $("#wizNext"); if (b && !b.disabled) b.focus(); else { const f = $$(FOCUSABLE, $("#wizard")).find(x => x.offsetParent !== null); if (f) f.focus(); } }, 60);
}
function closeWizard(){ $("#wizard").classList.add("hidden"); $("#app").inert = false; }
function renderWiz(){
  if (!wizardOpen()) return;
  const st = WIZ.step;
  $$("#wizSteps li").forEach(li => { const n = Number(li.dataset.step); li.classList.toggle("current", n === st); li.classList.toggle("done", st === "run" || n < st); });
  $$(".wiz-step").forEach(s => s.classList.toggle("hidden", String(s.dataset.step) !== String(st)));
  $("#wizFoot").classList.toggle("hidden", st === "run");
  $("#wizSkip").classList.toggle("hidden", st === "run");
  $("#wizBack").style.visibility = st === 1 ? "hidden" : "visible";
  $("#wizNext").innerHTML = st === 3 ? 'Terminer<i class="ti ti-check" aria-hidden="true"></i>' : 'Suivant<i class="ti ti-arrow-right" aria-hidden="true"></i>';
  if (st === 1) renderWiz1(); else if (st === 2) renderWiz2(); else if (st === 3) renderWiz3();
}
function renderWiz1(){
  const c = CATALOG, ok = !!(c && c.wow_valid), cur = $("#wizCurrent");
  if (WIZ.needDetect && c){ WIZ.needDetect = false; if (!ok) WIZ.finder.detect(); }
  cur.innerHTML = ok
    ? `<div class="notice ok"><i class="ti ti-circle-check" aria-hidden="true"></i><span><strong>Jeu trouvé :</strong> <span class="selectable">${esc(c.wow_path)}</span></span></div>
       <div class="btn-row"><button class="btn ghost sm" data-w="detect"><i class="ti ti-radar" aria-hidden="true"></i>Chercher un autre dossier</button>
       <button class="btn ghost sm" data-w="browse"><i class="ti ti-folder-open" aria-hidden="true"></i>Parcourir…</button></div>`
    : "";
  cur.classList.toggle("hidden", !ok);
  $("#wizNext").disabled = !ok;
  $("#wizHint").textContent = ok ? "" : "Choisis le dossier du jeu pour continuer.";
}
function renderWiz2(){
  $("#wizPresets").innerHTML = presetsHTML(WIZ.preset);
  const s = presetOf(WIZ.preset), opt = $("#wizPackOpt");
  if (FR && !FR.pack_present && needsPack(s)){
    opt.innerHTML = FR.pack_installable
      ? `<div class="pack-box wiz-packopt"><div class="pb-row"><i class="ti ti-cloud-download pb-ico" aria-hidden="true"></i><div class="pb-txt">
           <div class="pb-title">Pack FR (2,6 Go)</div>
           <div class="pb-sub">Le jeu de base, les voix et les sorts Blizzard en français en ont besoin. Il sera téléchargé à la fin.</div></div></div>
           <label class="check"><input type="checkbox" id="wizDlPack" ${WIZ.dlPack ? "checked" : ""}><span>Télécharger le pack FR maintenant</span></label>
           <p class="muted">Sinon, ces trois lignes restent en anglais : tu pourras installer le pack plus tard, dans l'onglet Français.</p></div>`
      : `<div class="notice info wiz-packopt"><i class="ti ti-info-circle" aria-hidden="true"></i><span>Le pack FR n'est pas disponible pour l'instant : le jeu de base, les voix et les sorts Blizzard resteront en anglais.</span></div>`;
  } else opt.innerHTML = "";
  $("#wizNext").disabled = false; $("#wizHint").textContent = "";
}
function renderWiz3(){
  const packs = (CATALOG && CATALOG.packs) || [];
  if (!WIZ.packs) WIZ.packs = new Set(packs.filter(p => p.status !== "complete").map(p => p.id));   // packs conseillés : cochés
  $("#wizPacks").innerHTML = packs.length ? packs.map(pk => {
    const done = pk.status === "complete", onn = done || WIZ.packs.has(pk.id);
    const names = (Array.isArray(pk.products) ? pk.products : []).map(id => (findProduct(id) || {}).name).filter(Boolean);
    return `<div class="wpack ${onn ? "on" : ""} ${done ? "disabled" : ""}" data-wp="${esc(pk.id)}" role="checkbox" aria-checked="${onn}" aria-disabled="${done}" tabindex="${done ? -1 : 0}">
      <span class="check"><input type="checkbox" tabindex="-1" ${onn ? "checked" : ""} ${done ? "disabled" : ""}></span>
      <div class="pack-ico" style="background:var(--${safeAccent(pk.accent) || "purple"})"><i class="ti ${safeIcon(pk.icon) || "ti-package"}" aria-hidden="true"></i></div>
      <div class="wp-body"><div class="wp-name">${esc(pk.name)} ${done ? '<span class="tag ok">déjà installé</span>' : ""}</div>
        <div class="wp-desc">${esc(pk.description)}</div>${names.length ? `<div class="wp-items">${esc(names.join(" · "))}</div>` : ""}</div></div>`;
  }).join("") : `<div class="notice info"><i class="ti ti-info-circle" aria-hidden="true"></i><span>Pas de pack proposé pour l'instant : tu choisiras tes addons dans l'onglet Addons.</span></div>`;
  const n = packs.filter(pk => pk.status !== "complete" && WIZ.packs.has(pk.id)).length;
  $("#wizNext").disabled = false;
  $("#wizHint").textContent = n ? n + " " + plural(n, "pack sera installé", "packs seront installés") + "." : "Aucun pack choisi.";
}
function toggleWizPack(el){
  if (!el || el.classList.contains("disabled") || !WIZ.packs) return;
  const id = el.dataset.wp;
  if (WIZ.packs.has(id)) WIZ.packs.delete(id); else WIZ.packs.add(id);
  renderWiz3();
  const again = $(`#wizPacks [data-wp="${sel(id)}"]`); if (again) again.focus();
}
function wizNext(){
  if (WIZ.step === 1){ if (CATALOG && CATALOG.wow_valid){ WIZ.step = 2; renderWiz(); } }
  else if (WIZ.step === 2){ WIZ.step = 3; renderWiz(); }
  else if (WIZ.step === 3) runWizard();
}
function wizBack(){ if (typeof WIZ.step === "number" && WIZ.step > 1){ WIZ.step--; renderWiz(); } }
async function skipWizard(){
  if (WIZ_RUNNING) return;
  closeWizard();
  await call("set_pref", "first_run_done", true); PREFS.first_run_done = true;
  toast("Tu peux relancer l'assistant depuis les Réglages.", "info", "Assistant");
}
const RUN_ICON = {wait:"ti-circle-dashed", running:"ti-loader-2 spin", ok:"ti-circle-check", err:"ti-alert-triangle", skip:"ti-player-skip-forward"};
function renderRun(){
  $("#wizRun").innerHTML = WIZ.run.map((st, i) => `<li class="${st.state}" data-ri="${i}"><i class="ti ${RUN_ICON[st.state]}" aria-hidden="true"></i>
    <div class="r-body"><div class="r-lbl">${esc(st.label)}</div><div class="r-msg">${esc(st.msg || (st.state === "wait" ? "En attente" : ""))}</div>
    ${st.state === "running" && st.bar ? `<div class="progress"><i style="width:${pct(st.pct)}%"></i></div>` : ""}</div></li>`).join("");
}
function paintRun(st){
  const li = $(`#wizRun [data-ri="${WIZ.run.indexOf(st)}"]`); if (!li) return;
  li.querySelector(".r-msg").textContent = st.msg || "";
  const b = li.querySelector(".progress > i"); if (b) b.style.width = pct(st.pct) + "%";
}
async function runWizard(){
  if (WIZ_RUNNING) return;
  WIZ_RUNNING = true; WIZ.step = "run"; renderWiz();
  const s = presetOf(WIZ.preset);
  const steps = [];
  if (FR && !FR.pack_present && needsPack(s) && FR.pack_installable && WIZ.dlPack) steps.push({id:"pack", label:"Pack FR (2,6 Go)", bar:true});
  steps.push({id:"fr", label:"Langue : " + (PRESETS.find(p => p.id === WIZ.preset) || PRESETS[0]).label});
  ((CATALOG && CATALOG.packs) || []).filter(pk => WIZ.packs && WIZ.packs.has(pk.id) && pk.status !== "complete")
    .forEach(pk => steps.push({id:"pk", pid:pk.id, label:"Pack " + pk.name, bar:true}));
  WIZ.run = steps.map(x => ({...x, state:"wait", msg:"", pct:0}));
  $("#wizRunTitle").textContent = "Installation…";
  $("#wizRunSub").textContent = "Laisse le launcher ouvert, ça ne prend que quelques instants.";
  $("#wizDone").classList.add("hidden");
  renderRun();
  let errors = 0;
  for (const st of WIZ.run){
    st.state = "running"; renderRun();
    let ok = false;
    try { ok = await runStep(st, s); } catch(e){ st.msg = String((e && e.message) || e); ok = false; }
    st.state = ok ? "ok" : "err"; if (!ok) errors++;
    renderRun();
  }
  await call("set_pref", "first_run_done", true); PREFS.first_run_done = true;
  WIZ_RUNNING = false;
  $("#wizRunTitle").textContent = errors ? "C'est presque prêt" : "Tout est prêt !";
  $("#wizRunSub").textContent = errors ? "Certaines étapes n'ont pas abouti : tu pourras les refaire depuis les onglets du launcher."
                                       : "Bon jeu sur Ebonhold !";
  $("#wizDone").classList.remove("hidden");
  setTimeout(() => $("#wizPlay").focus(), 40);
  reload(); loadFr({reset:true});
}
async function runStep(st, s){
  if (st.id === "pack"){
    const done = waitEvent("onPackDone");
    const offP = on("onPackProgress", (p, m) => { st.pct = pct(p); st.msg = String(m || ""); paintRun(st); });
    PACK = {busy:true, pct:0, msg:"", err:""};
    const r = await call("install_fr_pack");
    if (!r.started){ offP(); PACK.busy = false; st.msg = r.error || "Impossible de lancer le téléchargement."; return false; }
    const res = await done; offP();
    st.msg = String(res.args[1] || ""); return !!res.args[0];
  }
  if (st.id === "fr"){
    const settings = {...s};
    if (!(FR && FR.pack_present)) PACK_KEYS.forEach(k => settings[k] = "en");    // sans pack : ces lignes restent en anglais
    const done = waitEvent("onFrDone", () => true, 10 * 60e3);
    const offL = on("onFrLog", m => { st.msg = String(m || ""); paintRun(st); });
    st.msg = "Application des réglages…"; paintRun(st);
    const r = await applyFr(settings, "wizard");
    if (!r.started){ offL(); st.msg = r.error || "Impossible d'appliquer."; return false; }
    const res = await done; offL();
    if (res.timeout){ st.msg = "Pas de réponse du launcher."; return false; }
    st.msg = String(res.args[1] || ""); return !!res.args[0];
  }
  if (st.id === "pk"){
    // On écoute AVANT l'appel : un addon déjà prêt peut répondre tout de suite.
    const seen = new Map(), prog = {};
    let ids = null, finish = null;
    const check = () => { if (ids && finish && ids.every(i => seen.has(i))) finish(); };
    const tick = () => { if (!ids) return; st.pct = ids.reduce((a, i) => a + (seen.has(i) ? 100 : (prog[i] || 0)), 0) / ids.length; paintRun(st); };
    const offP = on("onProgress", (id, p, m) => { prog[id] = pct(p); if (ids && ids.includes(id)){ const pr = findProduct(id); st.msg = (pr ? pr.name + " : " : "") + (m || ""); tick(); } });
    const offD = on("onDone", (id, ok, m) => { seen.set(id, {ok, m}); tick(); check(); });
    const r = await call("install_pack", st.pid);
    if (!r.started){ offP(); offD(); st.msg = r.error || "Installation impossible."; return false; }
    ids = Array.isArray(r.ids) ? r.ids : [];
    if (!ids.length){ offP(); offD(); st.msg = "Déjà installé."; return true; }
    markBusy(ids);
    st.msg = "En attente…"; paintRun(st);
    const timedOut = await new Promise(res => { finish = () => res(false); setTimeout(() => res(true), 20 * 60e3); check(); });
    offP(); offD();
    if (timedOut){ st.msg = "Pas de réponse du launcher."; return false; }
    const fails = ids.filter(i => !seen.get(i).ok);
    st.msg = fails.length ? String(seen.get(fails[0]).m || "Échec de l'installation.")
                          : ids.length + " " + plural(ids.length, "addon installé", "addons installés") + ".";
    return !fails.length;
  }
  return false;
}

/* ================================================================ 17. Préférences */
async function initPrefs(late){
  const p = await call("get_prefs");
  if (!p || p.error) return;
  PREFS = p;
  if (typeof p.zoom === "number" && isFinite(p.zoom)){ applyZoom(p.zoom, false); store.set("ebon_zoom", String(ZOOM)); }
  if (p.first_run_done === false) openWizard();
  else if (late && wizardOpen() && !WIZ_RUNNING) closeWizard();
}

/* ================================================================ 18. Liaisons (clics, clavier) */
function bind(){
  $$(".nav-item").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#sideGame").addEventListener("click", () => switchTab("settings"));
  $("#refreshBtn").addEventListener("click", () => { reload(true); loadFr(); toast("Recherche des nouveautés…", "info"); });
  $("#playBtn").addEventListener("click", play);
  $("#topPlay").addEventListener("click", play);
  $("#statusGrid").addEventListener("click", e => { const b = e.target.closest("[data-act]"); if (b) homeAction(b.dataset.act); });
  $("#newsList").addEventListener("click", e => { const b = e.target.closest("[data-url]"); if (b) openUrl(b.dataset.url); });
  $("#newsMore").addEventListener("click", () => { NEWS_ALL = !NEWS_ALL; renderNews(); });

  // Addons
  $("#searchInput").addEventListener("input", e => { FILTER.term = e.target.value; renderGrid(); });
  $("#filterChips").addEventListener("click", e => { const c = e.target.closest("[data-cat]"); if (c){ FILTER.cat = c.dataset.cat; renderChips(); renderGrid(); } });
  $("#stateFilter").addEventListener("click", e => { const b = e.target.closest("[data-state]"); if (b){ FILTER.state = b.dataset.state; renderGrid(); } });
  $$(".view-toggle button").forEach(b => b.addEventListener("click", () => { VIEW = b.dataset.view; store.set("ebon_view", VIEW); renderGrid(); }));
  $("#packsRow").addEventListener("click", e => { const b = e.target.closest("[data-pack]"); if (b && !b.disabled) installPack(b.closest("[data-pid]").dataset.pid); });
  const grid = $("#catalogGrid");
  grid.addEventListener("click", e => {
    const th = e.target.closest("th[data-col]");
    if (th){ const k = th.dataset.col; if (SORT.col === k) SORT.dir *= -1; else { SORT.col = k; SORT.dir = 1; } renderGrid(); return; }
    const item = e.target.closest("[data-id]"); if (!item) return;
    if (e.target.closest("[data-install]")) installProduct(item.dataset.id); else openProduct(item.dataset.id);
  });
  grid.addEventListener("keydown", e => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const th = e.target.closest("th[data-col]"); if (th){ e.preventDefault(); th.click(); return; }
    if (e.target.matches(".card, .row")){ e.preventDefault(); openProduct(e.target.dataset.id); }
  });
  $("#updateAllBtn").addEventListener("click", updateAll);
  $("#openAddonsBtn").addEventListener("click", async () => { const r = await call("open_addons_folder"); if (r.ok === false) toast(r.error || "Dossier introuvable.", "err"); });
  $("#pmActions").addEventListener("click", e => { const b = e.target.closest("[data-pm]"); if (b) productAction(b); });

  // Français
  $("#frPresets").addEventListener("click", e => { const b = e.target.closest("[data-preset]"); if (b && FR && !FR_APPLYING){ FR_CUR = presetOf(b.dataset.preset); renderFr(); } });
  $("#frBlocks").addEventListener("click", e => {
    const sb = e.target.closest(".switch button");
    if (sb && !sb.disabled){ setFr(sb.closest(".fr-row").dataset.k, sb.dataset.v); return; }
    const bb = e.target.closest("[data-block]");
    if (bb && !bb.disabled){ const blk = FR_BLOCKS.find(b => b.id === bb.dataset.block); if (blk){ blk.rows.forEach(r => setFr(r.k, bb.dataset.v, true)); renderFr(); } }
  });
  $("#frBlocks").addEventListener("change", e => { if (e.target.id === "frNomEn" && FR_CUR){ FR_CUR.nom_anglais = e.target.checked; renderFr(); } });
  $("#frPackBox").addEventListener("click", e => {
    const b = e.target.closest("[data-fr]"); if (!b) return;
    if (b.dataset.fr === "pack") installFrPack();
    else if (b.dataset.fr === "pack-en"){ PACK_KEYS.forEach(k => setFr(k, "en", true)); renderFr(); }
  });
  $("#frApply").addEventListener("click", () => applyFr());
  $("#frRevert").addEventListener("click", () => { if (FR){ FR_CUR = normFr(FR.settings); renderFr(); } });
  $("#frLogClear").addEventListener("click", frLogClear);

  // Aide
  $("#btnBug").addEventListener("click", () => openReport("bug"));
  $("#btnIdea").addEventListener("click", () => openReport("suggestion"));
  $("#helpSeg").addEventListener("click", e => { const b = e.target.closest("[data-help]"); if (b) setHelpView(b.dataset.help); });
  $("#guideNav").addEventListener("click", e => { const b = e.target.closest("[data-page]"); if (b) setGuidePage(b.dataset.page); });
  $("#helpLinks").addEventListener("click", e => { const b = e.target.closest("[data-link]"); if (b) helpLink(b.dataset.link); });
  document.addEventListener("click", e => {
    const t = e.target.closest("[data-goto], [data-wizard], [data-openlog], [data-report]"); if (!t) return;
    if (t.dataset.goto) switchTab(t.dataset.goto);
    else if (t.dataset.wizard) openWizard();
    else if (t.dataset.openlog) openLog();
    else if (t.dataset.report) openReport(t.dataset.report);
  });
  bindShots();

  // Réglages
  settingsFinder = createFinder($("#settingsFinder"));
  $("#folderBtn").addEventListener("click", () => settingsFinder.browse());
  $("#detectBtn").addEventListener("click", () => settingsFinder.detect());
  $$("[data-zoom]").forEach(b => b.addEventListener("click", () => zoomBy(Number(b.dataset.zoom))));
  $("#aboutGithub").addEventListener("click", () => openUrl(GITHUB_URL));

  // Fenêtres
  $$(".overlay").forEach(o => o.addEventListener("mousedown", e => { if (e.target === o) closeModal(o.id); }));
  document.addEventListener("click", e => { const c = e.target.closest("[data-close]"); if (c && !c.disabled){ const o = c.closest(".overlay"); if (o) closeModal(o.id); } });
  $("#playFix").addEventListener("click", fixAndPlay);
  $("#playAnyway").addEventListener("click", () => { closeModal("playModal"); launch(); });

  // Signalement
  $("#repKind").addEventListener("click", e => { const b = e.target.closest("[data-kind]"); if (b && b.dataset.kind !== REP.kind) setRepKind(b.dataset.kind); });
  $("#repText").addEventListener("input", updateCount);
  $("#repPick").addEventListener("click", pickAttachments);
  $("#repRecent").addEventListener("click", e => { const b = e.target.closest("[data-ri]"); if (b) toggleRecent(Number(b.dataset.ri)); });
  $("#repAttach").addEventListener("click", e => {
    const b = e.target.closest("[data-ai]"); if (!b) return;
    REP.attach.splice(Number(b.dataset.ai), 1); renderAttach(); syncRecent();
  });
  $("#repLog").addEventListener("change", () => { REP.logTouched = true; });
  $("#repSend").addEventListener("click", sendReport);
  $("#repRetry").addEventListener("click", sendReport);
  $("#repDiscord").addEventListener("click", () => openUrl(linkUrl(/discord\.(gg|com)/, DISCORD_URL)));

  // Assistant
  WIZ.finder = createFinder($("#wizFinder"), {onPicked: () => renderWiz()});
  $("#wizCurrent").addEventListener("click", e => { const b = e.target.closest("[data-w]"); if (!b) return; if (b.dataset.w === "detect") WIZ.finder.detect(); else WIZ.finder.browse(); });
  $("#wizNext").addEventListener("click", wizNext);
  $("#wizBack").addEventListener("click", wizBack);
  $("#wizSkip").addEventListener("click", skipWizard);
  $("#wizPresets").addEventListener("click", e => { const b = e.target.closest("[data-preset]"); if (b){ WIZ.preset = b.dataset.preset; renderWiz2(); const again = $(`#wizPresets [data-preset="${sel(WIZ.preset)}"]`); if (again) again.focus(); } });
  $("#wizPackOpt").addEventListener("change", e => { if (e.target.id === "wizDlPack") WIZ.dlPack = e.target.checked; });
  $("#wizPacks").addEventListener("click", e => toggleWizPack(e.target.closest("[data-wp]")));
  $("#wizPacks").addEventListener("keydown", e => { if (e.key === " " || e.key === "Enter"){ const el = e.target.closest("[data-wp]"); if (el){ e.preventDefault(); toggleWizPack(el); } } });
  $("#wizPlay").addEventListener("click", () => { closeWizard(); switchTab("home"); play(); });
  $("#wizHome").addEventListener("click", () => { closeWizard(); switchTab("home"); });
}

/* ================================================================ 19. MOCK — aperçu dans un navigateur
   Simule TOUTES les méthodes du contrat, avec délais et événements, pour tester l'interface
   sans le moteur Python. Scénarios à ajouter à l'adresse (ex. index.html?apercu&sansjeu) :
     apercu     démarre tout de suite sur ces données (sinon après 30 s sans pont)
     assistant  force l'assistant de démarrage        sansjeu   aucun jeu détecté (consentement + scan)
     sanspack   pack FR absent                        sanslien  pack FR non téléchargeable
     ok         tout est à jour (Jouer lance direct)  auto      onFrState « réappliqué » au démarrage
     attente    anti-spam actif (signalement)         echec     l'envoi du signalement échoue
     jeuouvert  le jeu est déjà ouvert                echecfix  « Corriger et jouer » échoue
   ===================================================================== */
const MOCK = (() => {
  const Q = new URLSearchParams(location.search), flag = k => Q.has(k);
  const fire = (ev, ...a) => { try { if (window[ev]) window[ev](...a); } catch(e){ console.error(e); } };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const now = () => { const d = new Date(), p = n => String(n).padStart(2, "0"); return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`; };
  const PRODUCTS = [
    // id, nom, catégorie, description, version, icône, couleur, managed, notes
    ["ebonholdfr", "EbonholdFR", "traduction", "Traduit le contenu d'Ebonhold : echoes, Soul Tree, affixes, tomes et interface du serveur.", "4.0", "ti-language", "purple", true,
      "Interface du serveur traduite en direct, infobulles pour ceux sans patch, EbonholdFRFix intégré."],
    ["checkpoints", "EbonholdCheckpoints", "carte", "Téléportation rapide vers les checkpoints débloqués, avec recherche et favoris.", "1.3", "ti-map-pin", "teal", false, "Corrections."],
    ["gathermate", "GatherMate", "carte", "Affiche herbes, minerais, gaz et poissons sur la carte.", "1.25", "ti-leaf", "green", false, "Version figée pour Ebonhold."],
    ["gatherhud", "GatherHud", "carte", "HUD de récolte en vue 3D : les gisements affichés autour de toi.", "1.2.0", "ti-3d-cube-sphere", "teal", false, "Corrections."],
    ["ackisrecipelist", "Ackis Recipe List", "metiers", "Liste les recettes qui te manquent et où les apprendre.", "2.01", "ti-notebook", "amber", false, "Version figée pour Ebonhold."],
    ["advancedtradeskillwindow2", "Métiers+", "metiers", "Fenêtre de métiers améliorée : file d'attente, recherche avancée, catégories perso.", "1.2", "ti-hammer", "blue", false, "Corrections."],
    ["questie", "Questie", "quetes", "Affiche les quêtes disponibles et leurs objectifs sur la carte.", "1.6.4", "ti-route", "amber", false, "Version figée pour Ebonhold."],
    ["ebon-builds", "EbonBuilds", "personnage", "Gère tes builds d'echoes simplement.", "1.3.6", "ti-wand", "blue", false, ""],
    ["ebon-clearance", "EbonClearance", "sacs", "Nettoie tes sacs à la vitesse de l'éclair.", "2.76.0", "ti-trash", "coral", false, ""],
    ["transmog-wardrob", "Wardrobe", "personnage", "Visualise tes transmogrifications facilement.", "1.29", "ti-shirt", "pink", false, ""],
  ];
  const LATEST = Object.fromEntries(PRODUCTS.map(p => [p[0], p[4]]));
  const PACKS = [
    {id:"pack-recolte", name:"Récolte", description:"Herbes, minerais et gisements sur la carte et autour de toi.", icon:"ti-leaf", accent:"green", products:["gathermate", "gatherhud"]},
    {id:"pack-metiers", name:"Métiers", description:"Recettes manquantes et fenêtre de métiers améliorée.", icon:"ti-hammer", accent:"blue", products:["ackisrecipelist", "advancedtradeskillwindow2"]},
  ];
  const keys = ["jeu","voix","sorts_blizzard","reputations","hauts_faits","metiers","echoes_desc","echoes_noms","soultree_desc","soultree_noms","affixes_desc","affixes_noms","tomes","interface"];
  const preset = id => { const s = {}; keys.forEach(k => s[k] = id === "tout_en" ? "en" : "fr"); if (id === "recommande") ["echoes_noms","soultree_noms","affixes_noms"].forEach(k => s[k] = "en"); s.nom_anglais = id === "tout_fr"; return s; };
  const S = {
    installed: flag("ok") ? {ebonholdfr:"4.0", checkpoints:"1.3", gathermate:"1.25"} : {ebonholdfr:"3.1", checkpoints:"1.2", gathermate:"1.25", advancedtradeskillwindow2:"1.1"},
    wow: flag("sansjeu") ? "" : "D:\\Jeux\\Ebonhold",
    pack: !flag("sanspack"),
    fr: preset("recommande"),
    frState: flag("ok") ? {applied:true, up_to_date:true, server_changed:false, last_applied:"19/10 21:40", message:""}
                        : {applied:true, up_to_date:false, server_changed:true, last_applied:"19/10 21:40", message:"Mise à jour officielle détectée : tes réglages FR sont à réappliquer."},
    launcherDone: flag("ok"), remote:false, sent:0, number:41, scans:0, cancel:false, frStatePushed:false,
  };
  const prefs = (() => { try { return JSON.parse(localStorage.getItem("ebon_mock_prefs")) || {}; } catch(e){ return {}; } })();
  const P = {zoom: Number(prefs.zoom) || 1, first_run_done: flag("assistant") ? false : prefs.first_run_done === true};
  const savePrefs = () => { try { localStorage.setItem("ebon_mock_prefs", JSON.stringify(P)); } catch(e){} };
  const status = id => !S.installed[id] ? "install" : S.installed[id] === LATEST[id] ? "uptodate" : "update";
  function build(source){
    const products = PRODUCTS.map(([id, name, category, description, version, icon, accent, managed, notes]) => ({
      id, name, category, description, long_description: description + "\n\nFiche détaillée de démonstration (aperçu sans moteur).",
      version, installed_version: S.installed[id] || null, status: status(id), notes, icon, accent, managed,
      changelog_url: "https://github.com/Squall98/Ebonhold-Launcher",
      history: [{version, notes: notes || "Mise à jour."}, {version: "1.0", notes: "Première version."}],
    }));
    const packs = PACKS.map(pk => { const done = pk.products.filter(i => status(i) === "uptodate").length;
      return {...pk, total: pk.products.length, done, status: done === pk.products.length ? "complete" : "install"}; });
    return {source, launcher_version:"2.0.0", latest_launcher_version: S.launcherDone ? "2.0.0" : "2.0.1", launcher_update: !S.launcherDone,
      launcher_download_url:"https://github.com/Squall98/Ebonhold-Launcher/releases", launcher_frozen:true,
      categories:[{id:"traduction", label:"Traduction", icon:"ti-language"}, {id:"carte", label:"Carte & voyage", icon:"ti-map-pin"},
        {id:"quetes", label:"Quêtes", icon:"ti-list-check"}, {id:"metiers", label:"Métiers", icon:"ti-tools"},
        {id:"sacs", label:"Sacs & inventaire", icon:"ti-briefcase"}, {id:"personnage", label:"Personnage", icon:"ti-user"}],
      packs, links:[{label:"Discord Ebonhold FR", url:"https://discord.gg/ebonhold", icon:"ti-brand-discord"},
        {label:"Soul Tree Planner", url:"https://squall98.github.io/ebonhold-skilltree/", icon:"ti-binary-tree"},
        {label:"Code source", url:"https://github.com/Squall98/Ebonhold-Launcher", icon:"ti-brand-github"}],
      updates_count: products.filter(p => p.status === "update").length, wow_path: S.wow, wow_valid: !!S.wow, products};
  }
  // File d'installation : un addon à la fois, comme le moteur.
  const queue = []; let working = false;
  async function work(){
    working = true;
    while (queue.length){
      const id = queue.shift();
      for (let p = 0; p <= 100; p += 20){ fire("onProgress", id, p, p < 100 ? "Téléchargement… " + p + " %" : "Installation…"); await wait(170); }
      S.installed[id] = LATEST[id];
      fire("onDone", id, true, "Installé (v" + LATEST[id] + ").");
    }
    working = false;
  }
  const enqueue = id => { if (!queue.includes(id)) queue.push(id); if (!working) work(); };
  const idle = async () => { while (working || queue.length) await wait(100); };
  function fakeShot(seed){
    const c = document.createElement("canvas"); c.width = 192; c.height = 120;
    const g = c.getContext("2d"); let h = 7;
    for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const hue = h % 360, grd = g.createLinearGradient(0, 0, 0, 120);
    grd.addColorStop(0, `hsl(${hue},45%,42%)`); grd.addColorStop(1, `hsl(${(hue + 40) % 360},40%,14%)`);
    g.fillStyle = grd; g.fillRect(0, 0, 192, 120);
    g.fillStyle = `hsla(${(hue + 180) % 360},30%,8%,.85)`; g.beginPath(); g.moveTo(0, 120);
    for (let x = 0; x <= 192; x += 24) g.lineTo(x, 62 + ((h >>> (x % 17)) % 34));
    g.lineTo(192, 120); g.fill();
    g.fillStyle = "rgba(255,255,255,.7)"; g.fillRect(8, 8, 46, 6); g.fillRect(150, 100, 34, 10);
    return c.toDataURL("image/jpeg", .75);
  }
  return {
    get_catalog: async (check_remote) => {
      await wait(120);
      if (check_remote && !S.remote) setTimeout(() => { S.remote = true; fire("onCatalogUpdate", build("remote")); }, 1500);
      if (flag("auto") && !S.frStatePushed){ S.frStatePushed = true; setTimeout(() => {
        S.frState = {applied:true, up_to_date:true, server_changed:true, last_applied: now(), message:"Mise à jour officielle détectée : tes réglages FR ont été réappliqués."};
        fire("onFrState", {...S.frState}); }, 2500); }
      return build(S.remote ? "remote" : "cache");
    },
    choose_folder: async () => { await wait(400); S.wow = "D:\\Jeux\\Ebonhold"; return {ok:true, path:S.wow}; },
    install_product: async id => { if (!S.wow) return {started:false, error:"Choisis d'abord le dossier du jeu."}; enqueue(id); return {started:true}; },
    uninstall_product: async id => { await wait(200); delete S.installed[id]; return {ok:true}; },
    install_all: async () => { const ids = Object.keys(S.installed).filter(id => status(id) === "update"); ids.forEach(enqueue); return {started:true, count:ids.length, ids}; },
    install_pack: async pid => { const pk = PACKS.find(p => p.id === pid); if (!pk) return {started:false, error:"Pack inconnu."};
      const ids = pk.products.filter(id => status(id) !== "uptodate"); ids.forEach(enqueue); return {started:true, ids}; },
    update_launcher: async () => { (async () => { for (let p = 0; p <= 100; p += 10){ fire("onLauncherProgress", p, "Téléchargement"); await wait(200); }
      S.launcherDone = true; fire("onLauncherReady"); })(); return {ok:true, mode:"exe"}; },
    install_fr_pack: async () => {
      if (!S.wow) return {started:false, error:"Choisis d'abord le dossier du jeu."};
      (async () => {
        fire("onFrLog", "Téléchargement du pack frFR (~2,6 Go, ça peut être long)…");
        for (let p = 0; p <= 100; p += 5){ fire("onPackProgress", p, "Téléchargement : " + (2.6 * p / 100).toFixed(1).replace(".", ",") + " / 2,6 Go"); await wait(220); }
        fire("onFrLog", "Extraction dans Data\\frFR…"); await wait(500);
        fire("onFrLog", "Dossier frFR placé dans Data."); S.pack = true;
        fire("onPackDone", true, "Pack FR installé.");
      })();
      return {started:true};
    },
    launch_game: async () => { await wait(300); return flag("jeuouvert") ? {ok:false, error:"Le jeu est déjà ouvert."} : {ok:true}; },
    has_game_exe: async () => ({present: !!S.wow}),
    open_addons_folder: async () => S.wow ? {ok:true} : {ok:false, error:"Dossier du jeu introuvable."},
    open_url: async url => { console.info("[aperçu] ouverture du lien :", url); return {ok:true}; },
    js_log: async msg => { console.debug("[aperçu] journal :", msg); return {ok:true}; },
    open_log: async () => ({ok:true}),
    // Préférences
    get_prefs: async () => ({...P}),
    set_pref: async (key, value) => { if (key === "zoom") P.zoom = Number(value); else if (key === "first_run_done") P.first_run_done = !!value; savePrefs(); return {ok:true}; },
    // Dossier du jeu
    quick_detect: async () => { await wait(700);
      if (flag("sansjeu") && !S.scans) return {candidates:[]};
      return {candidates:[{path:"D:\\Jeux\\Ebonhold", is_ebonhold:true, label:"Ebonhold", has_exe:true, reason:"Wow.exe et ebonhold.dll trouvés"}]}; },
    scan_games: async () => { S.scans++; S.cancel = false;
      (async () => {
        for (const d of ["C:\\Program Files (x86)", "C:\\Jeux", "D:\\", "D:\\Jeux", "D:\\Jeux\\Ebonhold", "E:\\", "E:\\Serveurs-prives"]){
          if (S.cancel) return; fire("onScanProgress", "Recherche dans " + d + "…"); await wait(450); }
        if (S.cancel) return;
        fire("onScanDone", [
          {path:"C:\\Games\\Warmane", is_ebonhold:false, label:"Warmane", has_exe:true, reason:"Autre serveur privé (realmlist)"},
          {path:"D:\\Jeux\\Ebonhold", is_ebonhold:true, label:"Ebonhold", has_exe:true, reason:"Wow.exe et ebonhold.dll trouvés"},
          {path:"E:\\Serveurs-prives\\ChromieCraft", is_ebonhold:false, label:"ChromieCraft", has_exe:true, reason:"Autre serveur privé"},
          {path:"E:\\Ebonhold-copie", is_ebonhold:true, label:"Ebonhold (copie)", has_exe:false, reason:"ebonhold.dll trouvé, Wow.exe absent"},
        ]);
      })();
      return {started:true}; },
    cancel_scan: async () => { S.cancel = true; return {ok:true}; },          // hors contrat : à demander au moteur (optionnel)
    set_wow_path: async path => { await wait(150); S.wow = path; return {ok:true}; },
    // Français
    get_fr_settings: async () => { await wait(150);
      return {settings:{...S.fr}, presets:{recommande:preset("recommande"), tout_fr:preset("tout_fr"), tout_en:preset("tout_en")},
        pack_present:S.pack, pack_installable:!flag("sanslien"), pack_note: flag("sanslien") ? "Le lien de téléchargement du pack est en cours de remplacement." : "",
        state:{...S.frState}}; },
    apply_fr: async settings => {
      if (!S.wow) return {started:false, error:"Choisis d'abord le dossier du jeu."};
      if (flag("jeuouvert")) return {started:false, error:"Ferme d'abord le jeu (Wow.exe), puis recommence."};
      (async () => {
        const L = ["Lecture des réglages…", "Jeu de base : " + String(settings.jeu).toUpperCase() + (S.pack ? " (pack présent)" : " (pack absent)"),
          "Construction du patch (1 240 fichiers)…", "patch-Z.MPQ écrit.", "Addon EbonholdFR 4.0 réglé (noms des echoes : " + String(settings.echoes_noms).toUpperCase() + ").", "Terminé."];
        for (const l of L){ await wait(380); fire("onFrLog", l); }
        S.fr = {...settings}; S.frState = {applied:true, up_to_date:true, server_changed:false, last_applied: now(), message:""};
        S.installed.ebonholdfr = LATEST.ebonholdfr;
        fire("onFrDone", true, "Réglages appliqués. Tu peux lancer le jeu.");
      })();
      return {started:true};
    },
    // Jouer
    check_before_play: async () => { await wait(600);
      const issues = [];
      if (!S.frState.up_to_date) issues.push({id:"fr", label:"Le français doit être réappliqué (mise à jour du serveur).", fix_label:"Réappliquer le français"});
      const ups = Object.keys(S.installed).filter(id => status(id) === "update" && id !== "ebonholdfr");
      if (ups.length) issues.push({id:"addons", label: ups.length + (ups.length > 1 ? " addons à mettre à jour." : " addon à mettre à jour."), fix_label:"Mettre à jour"});
      if (flag("jeuouvert")) issues.push({id:"running", label:"Le jeu est déjà ouvert.", fix_label:""});
      return {ok: !issues.length, issues}; },
    fix_issues: async ids => {
      (async () => {
        if (flag("echecfix")){ await wait(900); fire("onFixDone", false, "Le jeu est ouvert : ferme-le, puis réessaie."); return; }
        if (ids.includes("fr")){ for (const l of ["Réapplication du français…", "patch-Z.MPQ écrit.", "Français réappliqué."]){ await wait(400); fire("onFrLog", l); }
          S.frState = {applied:true, up_to_date:true, server_changed:false, last_applied: now(), message:""}; S.installed.ebonholdfr = LATEST.ebonholdfr; }
        if (ids.includes("addons")){ Object.keys(S.installed).filter(id => status(id) === "update").forEach(enqueue); await idle(); }
        await wait(300); fire("onFixDone", true, "Tout est corrigé.");
      })();
      return {started:true}; },
    // Signalement
    report_info: async kind => { await wait(250);
      const blocked = flag("attente") || S.sent >= 3;
      return {can_send: !blocked, wait_minutes: blocked ? 17 : 0, log_available: true, infos_preview: [
        "Type : " + (kind === "bug" ? "bug" : "idée"),
        "Launcher : 2.0.0 (catalogue en ligne)",
        "Jeu : Wow.exe 3.3.5a (12340) · ebonhold.dll présent",
        "Dossier du jeu : <JEU>  (chemins anonymisés)",
        "Patchs MPQ : patch-Z.MPQ, patch-frFR-Z.MPQ",
        "Pack FR : " + (S.pack ? "présent" : "absent"),
        "Réglages FR : " + Object.entries(S.fr).map(([k, v]) => k + "=" + v).join(" "),
        "Addons : " + Object.entries(S.installed).map(([k, v]) => k + " " + v).join(", "),
        "Journaux du jeu : Logs\\FrameXML.log (12 dernières lignes)"].join("\n")}; },
    pick_attachments: async () => { await wait(500); return {paths:["C:\\Users\\Joueur\\Videos\\Captures\\bug-echoes.mp4", "C:\\Users\\Joueur\\Pictures\\Screenshots\\Capture d'écran 2026-10-20 101530.png"]}; },
    recent_captures: async () => { await wait(300);
      const items = [];
      for (let i = 0; i < 6; i++) items.push({path:"D:\\Jeux\\Ebonhold\\Screenshots\\WoWScrnShot_102026_10" + (12 + i) + "33.jpg", name:"WoWScrnShot_102026_10" + (12 + i) + "33.jpg", date:"20/10 10:" + (12 + i), size: 380000 + i * 61000});
      for (let i = 0; i < 4; i++) items.push({path:"C:\\Users\\Joueur\\Pictures\\Screenshots\\Capture d'écran 2026-10-19 2" + i + "0512.png", name:"Capture d'écran 2026-10-19 2" + i + "0512.png", date:"19/10 2" + i + ":05", size: 920000 + i * 40000});
      return {items}; },
    thumbnail: async path => { await wait(80 + Math.random() * 150); return VIDEO_EXT.test(path) ? {data_url:null} : {data_url: fakeShot(path)}; },
    send_report: async (kind, text, attachments, include_log) => {
      if (S.sent >= 3) return {started:false, error:"Tu as déjà envoyé 3 signalements cette heure-ci."};
      (async () => {
        fire("onReportProgress", 5, "Préparation des infos…"); await wait(500);
        const n = (attachments || []).length;
        for (let i = 0; i < n; i++){ fire("onReportProgress", 15 + Math.round(60 * i / Math.max(1, n)), "Envoi des pièces jointes (" + (i + 1) + "/" + n + ")…"); await wait(600); }
        if (include_log){ fire("onReportProgress", 80, "Ajout du journal…"); await wait(400); }
        fire("onReportProgress", 90, "Création du signalement…"); await wait(600);
        if (flag("echec")){ fire("onReportDone", false, 0, "GitHub ne répond pas. Réessaie dans quelques minutes."); return; }
        S.sent++; S.number++;
        fire("onReportProgress", 100, "Envoyé.");
        fire("onReportDone", true, S.number, "Signalement créé.");
      })();
      return {started:true}; },
  };
})();

/* ================================================================ 20. Démarrage */
// Démarrage instantané : catalogue local tout de suite, catalogue en ligne en arrière-plan
// (onCatalogUpdate), état FR et préférences en parallèle.
const T0 = Date.now();
const PREVIEW = /[?&](apercu|mock)(=|&|$)/.test(location.search);
function start(){
  if (_started) return;
  _started = true; _real = bridgeReady();
  if (!_bound){ _bound = true; bind(); }
  applyZoom(parseFloat(store.get("ebon_zoom")) || 1, false);
  switchTab("home");
  reload(true); loadFr(); initPrefs(false);
  jsLog(_real ? `pont prêt en ${((Date.now() - T0) / 1000).toFixed(1)} s` : "pont absent : aperçu (données d'exemple)");
}
// Le pont est arrivé APRÈS un démarrage en mode aperçu (PC lent, WebView2 qui s'initialise) :
// on recharge tout avec la vraie API, catalogue en ligne compris.
function onBridge(){
  if (!_started){ start(); return; }
  if (!_real){
    _real = true;
    jsLog(`pont arrivé en retard (${((Date.now() - T0) / 1000).toFixed(1)} s) : rechargement`);
    reload(true); loadFr({reset:true}); initPrefs(true);
  }
}
// Le pont pywebview (window.pywebview.api) est injecté de façon asynchrone par WebView2 et
// l'événement « pywebviewready » est lent/peu fiable : on SONDE la disponibilité de l'api.
(function waitForBridge(){
  layoutClasses();
  if (PREVIEW && !bridgeReady()) start();
  let tries = 0;
  const iv = setInterval(() => {
    tries++;
    if (bridgeReady()){ clearInterval(iv); onBridge(); }
    else if (tries === 150 && !_started) start();   // ~30 s : aperçu dans un navigateur (MOCK)
    else if (tries >= 1500) clearInterval(iv);      // ~5 min : on arrête de sonder
  }, 200);
})();
window.addEventListener("pywebviewready", onBridge);
