"use strict";

/* ------------------------------------------------------------------ API bridge */
const HIST = {
  ebonholdfr:[{version:"3.1",notes:"Skill tree et affixes retraduits."},{version:"3.0",notes:"Refonte des echoes."},{version:"2.0",notes:"Méthode patch-Z non-destructive."}],
  checkpoints:[{version:"1.2",notes:"Favoris et recherche par nom."},{version:"1.1",notes:"Catégories et tri."},{version:"1.0",notes:"Première version."}],
  "patch-z":[{version:"2026.06",notes:"Synchronisé avec le dernier patch serveur."}],
};
const MOCK = {
  _installed: {ebonholdfr:"3.1", checkpoints:"1.1"},
  get_catalog: async () => {
    const latest = {ebonholdfr:"3.1",checkpoints:"1.2","patch-z":"2026.06"};
    const st = id => MOCK._installed[id]===latest[id] ? "uptodate" : (MOCK._installed[id] ? "update" : "install");
    const mk = (id,name,cat,desc,ver,icon,acc) => ({id,name,category:cat,description:desc,long_description:desc+" — description détaillée pour la fiche.",version:ver,installed_version:MOCK._installed[id]||null,status:st(id),notes:HIST[id][0].notes,history:HIST[id],icon,accent:acc,changelog_url:"#"});
    const products = [
      mk("ebonholdfr","EbonholdFR","traduction","Traduction française complète : echoes, skill tree, affixes, tomes.","3.1","ti-language","purple"),
      mk("checkpoints","EbonholdCheckpoints","interface","Téléportation rapide vers les checkpoints débloqués, avec recherche et favoris.","1.2","ti-map-pin","teal"),
      mk("patch-z","Patch-Z (données custom)","donnees","Données custom du serveur (sorts, echoes, affixes).","2026.06","ti-package","coral"),
    ];
    const byId = Object.fromEntries(products.map(p=>[p.id,p]));
    const packs = [{id:"pack-fr",name:"Pack FR complet",description:"Traduction + données custom.",icon:"ti-flag",accent:"purple",products:["ebonholdfr","patch-z"],total:2,done:["ebonholdfr","patch-z"].filter(i=>byId[i].status==="uptodate").length,status:["ebonholdfr","patch-z"].every(i=>byId[i].status==="uptodate")?"complete":"install"}];
    return {source:"local",launcher_version:"1.0.0",latest_launcher_version:"1.0.0",launcher_update:false,launcher_download_url:"#",launcher_frozen:false,
      categories:[{id:"traduction",label:"Traduction",icon:"ti-language"},{id:"interface",label:"Interface & QoL",icon:"ti-layout-dashboard"},{id:"donnees",label:"Données serveur",icon:"ti-database"}],
      packs, links:[{label:"Discord Ebonhold FR",url:"#",icon:"ti-brand-discord"},{label:"Soul Tree Planner",url:"#",icon:"ti-binary-tree"},{label:"Guides",url:"#",icon:"ti-book"}],
      updates_count:products.filter(p=>p.status!=="uptodate").length, wow_path:"D:\\ebonhold\\Ebonhold", wow_valid:true, products};
  },
  choose_folder: async () => ({ok:true, path:"D:\\ebonhold\\Ebonhold"}),
  install_product: async (id) => { let p=0; const t=setInterval(()=>{p+=25;window.onProgress&&window.onProgress(id,Math.min(p,100),"Téléchargement…");
    if(p>=100){clearInterval(t);MOCK._installed[id]=({ebonholdfr:"3.1",checkpoints:"1.2","patch-z":"2026.06"})[id];window.onDone&&window.onDone(id,true,"Installé.");}},180); return {started:true}; },
  install_all: async () => ({started:true,count:2}),
  install_pack: async (pid) => { ["ebonholdfr","patch-z"].forEach(id=>MOCK.install_product(id)); return {started:true,ids:["ebonholdfr","patch-z"]}; },
  uninstall_product: async (id) => { delete MOCK._installed[id]; return {ok:true}; },
  update_launcher: async () => ({ok:false, mode:"dev", url:"#"}),
  get_fr_status: async () => ({available:true, error:"", pack_present:false, pack_url:"#", pack_installable:true, pack_note:"Pack ~2,4 Go requis pour les menus/quêtes/interface en français (Jeu = FR)."}),
  install_fr_pack: async () => { let p=0; const t=setInterval(()=>{p+=20;window.onPackProgress&&window.onPackProgress(p,"Téléchargement "+p+"%");
    if(p>=100){clearInterval(t);window.onFrLog&&window.onFrLog("Dossier frFR placé dans Data.");window.onPackDone&&window.onPackDone(true,"Pack frFR installé.");}},250); return {started:true}; },
  apply_fr_config: async () => { let i=0; const L=["Construction de patch-Z…","patch-Z.MPQ écrit (1240 fichiers).","Addon EbonholdFRFix installé.","Jeu=EN Voix=EN Sorts=FR Réput=FR."];
    const t=setInterval(()=>{window.onFrLog&&window.onFrLog(L[i++]); if(i>=L.length){clearInterval(t);window.onFrDone&&window.onFrDone(true,"Configuration appliquée.");}},300); return {started:true}; },
  launch_game: async () => ({ok:true}),
  has_game_exe: async () => ({present:true}),
  open_addons_folder: async () => ({ok:true}),
  open_url: async () => ({ok:true}),
};
function api(){ return (window.pywebview && window.pywebview.api) || MOCK; }

/* ------------------------------------------------------------------ état UI */
let CATALOG = null;
let FILTER = {term:"", cat:"all"};
let VIEW = (() => { try { return localStorage.getItem("ebon_view") || "cards"; } catch(e){ return "cards"; } })();
let SORT = {col:"name", dir:1};
const $ = (s,r=document) => r.querySelector(s);
const $$ = (s,r=document) => Array.from(r.querySelectorAll(s));
const TAB_TITLES = {catalog:"Catalogue", installed:"Mes installations", news:"Nouveautés", links:"Liens utiles", settings:"Réglages"};

/* ------------------------------------------------------------------ toasts */
function toast(msg, kind="info", title=""){
  const el = document.createElement("div");
  el.className = "toast "+kind;
  el.innerHTML = (title?`<div class="tt">${title}</div>`:"")+msg;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.opacity="0"; setTimeout(()=>el.remove(),250); }, 3800);
}

/* ------------------------------------------------------------------ onglets */
function switchTab(name){
  $$(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.tab===name));
  $$(".tab").forEach(t => t.classList.add("hidden"));
  $("#tab-"+name).classList.remove("hidden");
  $("#tabTitle").textContent = TAB_TITLES[name];
  if (name==="installed") renderInstalled();
  if (name==="news") renderNews();
  if (name==="links") renderLinks();
  if (name==="settings") loadFrStatus();
}

/* ------------------------------------------------------------------ helpers cartes */
const DEFAULT_ACCENT = {traduction:"purple", interface:"teal", donnees:"coral"};
const thumbAccent = p => "acc-" + (p.accent || DEFAULT_ACCENT[p.category] || "purple");
const thumbIcon   = p => p.icon || "ti-puzzle";
function actionLabel(s){ return s==="uptodate"?"Installé ✓":s==="update"?"Mettre à jour":s==="repair"?"Réparer":"Installer"; }
function metaLine(p){ return p.status==="update"?`v${p.installed_version} → v${p.version}`:p.status==="repair"?`v${p.version} · fichiers manquants`:`v${p.version}`; }

function cardHTML(p){
  const uninstall = p.installed_version!==null ? `<button class="uninstall" data-uid="${p.id}">Désinstaller</button>` : "";
  return `<div class="card" data-id="${p.id}">
    <div class="thumb ${thumbAccent(p)}"><i class="ti ${thumbIcon(p)}"></i></div>
    <div class="body">
      <div class="name">${p.name}</div>
      <div class="desc">${p.description||""}</div>
      <div class="meta">${metaLine(p)}</div>
      <div class="action"><button class="actbtn act-${p.status}" ${p.status==="uptodate"?"disabled":""}>${actionLabel(p.status)}</button></div>
      <div class="progress hidden"><i></i></div>
      <div class="progress-msg hidden"></div>
      ${uninstall}
    </div>
  </div>`;
}
function bindCards(scope){
  $$(scope+" [data-id]").forEach(el => el.addEventListener("click", e => { if (!e.target.closest("button")) openDetail(el.dataset.id); }));
  $$(scope+" .actbtn").forEach(b => b.addEventListener("click", e => { e.stopPropagation(); onAction(b.closest("[data-id]").dataset.id); }));
  $$(scope+" .uninstall").forEach(b => b.addEventListener("click", e => { e.stopPropagation(); onUninstall(b); }));
}

/* ---- vues alternatives : liste compacte + tableau triable ---- */
const catLabel = id => ((CATALOG && CATALOG.categories || []).find(c => c.id===id) || {}).label || id;
const accentName = p => p.accent || DEFAULT_ACCENT[p.category] || "purple";
function rowHTML(p){
  const uninstall = p.installed_version!==null ? `<button class="uninstall" data-uid="${p.id}">Désinstaller</button>` : "";
  return `<div class="row" data-id="${p.id}">
    <div class="thumb ${thumbAccent(p)}"><i class="ti ${thumbIcon(p)}"></i></div>
    <div class="rbody"><div class="name">${p.name}</div><div class="desc">${p.description||""}</div></div>
    <div class="rmeta">${metaLine(p)}</div>
    <div class="ract"><button class="actbtn act-${p.status}" ${p.status==="uptodate"?"disabled":""}>${actionLabel(p.status)}</button>${uninstall}</div>
  </div>`;
}
const TCOLS = [{k:"name",l:"Nom"},{k:"category",l:"Catégorie"},{k:"version",l:"Version"}];
function sortList(list){
  const v = p => SORT.col==="category" ? catLabel(p.category) : SORT.col==="version" ? p.version : p.name;
  return [...list].sort((a,b) => String(v(a)).localeCompare(String(v(b)), "fr", {numeric:true}) * SORT.dir);
}
function tableHTML(list){
  const head = TCOLS.map(c => `<th data-col="${c.k}" class="${SORT.col===c.k?'sorted '+(SORT.dir>0?'asc':'desc'):''}">${c.l}</th>`).join("") + "<th></th>";
  const rows = sortList(list).map(p => `<tr data-id="${p.id}">
    <td class="tn"><i class="ti ${thumbIcon(p)}" style="color:var(--${accentName(p)},#aeb6cc)"></i><span>${p.name}</span></td>
    <td class="tc">${catLabel(p.category)}</td>
    <td class="tv">${metaLine(p)}</td>
    <td class="ta"><button class="actbtn act-${p.status}" ${p.status==="uptodate"?"disabled":""}>${actionLabel(p.status)}</button></td>
  </tr>`).join("");
  return `<table class="cat-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}
function bindSort(){
  $$("#catalogGrid th[data-col]").forEach(th => th.addEventListener("click", () => {
    const k = th.dataset.col;
    if (SORT.col===k) SORT.dir *= -1; else { SORT.col=k; SORT.dir=1; }
    renderGrid();
  }));
}
function setView(v){
  VIEW = v;
  try { localStorage.setItem("ebon_view", v); } catch(e){}
  $$(".view-toggle button").forEach(b => b.classList.toggle("active", b.dataset.view===v));
  renderGrid();
}

/* ------------------------------------------------------------------ catalogue */
function renderChips(){
  const cats = [{id:"all",label:"Tous",icon:"ti-apps"}].concat(CATALOG.categories||[]);
  $("#filterChips").innerHTML = cats.map(c =>
    `<button class="chip ${FILTER.cat===c.id?"active":""}" data-cat="${c.id}">${c.icon?'<i class="ti '+c.icon+'"></i>':''}${c.label}</button>`).join("");
  $$("#filterChips .chip").forEach(ch => ch.addEventListener("click", () => { FILTER.cat=ch.dataset.cat; renderChips(); renderGrid(); }));
}
function renderPacks(){
  const packs = CATALOG.packs||[];
  $("#packsRow").innerHTML = packs.map(pk => `<div class="pack" data-pid="${pk.id}">
    <div class="pico" style="background:var(--${pk.accent||'purple'})"><i class="ti ${pk.icon||'ti-package'}"></i></div>
    <div class="pbody"><div class="pname">${pk.name}</div><div class="pdesc">${pk.description||""}</div>
      <div class="pcount">${pk.done}/${pk.total} installé${pk.total>1?"s":""}</div></div>
    <button class="${pk.status==='complete'?'complete':''}">${pk.status==='complete'?'Complet ✓':'Installer le pack'}</button>
  </div>`).join("");
  $$("#packsRow .pack button").forEach(b => { if (!b.classList.contains("complete"))
    b.addEventListener("click", () => installPack(b.closest(".pack").dataset.pid)); });
}
function filtered(){
  const t = FILTER.term.toLowerCase();
  return CATALOG.products.filter(p =>
    (FILTER.cat==="all" || p.category===FILTER.cat) &&
    (!t || p.name.toLowerCase().includes(t) || (p.description||"").toLowerCase().includes(t)));
}
function renderGrid(){
  const list = filtered();
  const g = $("#catalogGrid");
  g.className = "grid view-" + VIEW;
  if (VIEW==="list") g.innerHTML = list.map(rowHTML).join("");
  else if (VIEW==="table") g.innerHTML = list.length ? tableHTML(list) : "";
  else g.innerHTML = list.map(cardHTML).join("");
  $("#catalogEmpty").classList.toggle("hidden", list.length>0);
  bindCards("#catalogGrid");
  if (VIEW==="table") bindSort();
}
function renderCatalog(){
  const c = CATALOG;
  const bl = $("#bootLoading"); if (bl) bl.classList.add("hidden");
  renderChips(); renderPacks(); renderGrid();

  const upd = c.products.find(p => p.status==="update");
  const banner = $("#banner");
  if (upd){ banner.innerHTML = `<div class="tag">NOUVELLE VERSION</div><div class="txt">${upd.name} v${upd.version} disponible</div>`; banner.classList.remove("hidden"); }
  else banner.classList.add("hidden");

  const lu = $("#launcherUpdate");
  if (c.launcher_update){ $("#launcherUpdateTxt").textContent = `Version ${c.latest_launcher_version} disponible (actuelle ${c.launcher_version}).`; lu.classList.remove("hidden"); }
  else lu.classList.add("hidden");

  const badge = $("#updBadge");
  badge.textContent = c.updates_count; badge.classList.toggle("hidden", c.updates_count===0);
  $("#updateAllBtn").classList.toggle("hidden", c.updates_count===0 || !c.wow_valid);

  $("#wowPath").textContent = c.wow_path || "Choisir le dossier WoW…";
  $("#wowStatus").classList.toggle("invalid", !c.wow_valid);
  $("#sourcePill").textContent = c.source==="remote" ? "Catalogue en ligne" : "Catalogue local";
  $("#folderInput").value = c.wow_path || "";
  const fv = $("#folderValid");
  if (c.wow_path){ fv.textContent = c.wow_valid ? "Dossier Ebonhold valide." : "Ce dossier ne ressemble pas à une install Ebonhold."; fv.className="folder-valid "+(c.wow_valid?"ok":"bad"); }
  else fv.textContent="";
  $("#aboutVersion").textContent = "v"+c.launcher_version;
  $("#aboutSource").textContent = c.source==="remote" ? "catalogue en ligne" : "catalogue local";
  api().has_game_exe().then(r => $("#playBtn").classList.toggle("hidden", !(r.present && c.wow_valid)));
}

function renderInstalled(){
  const items = CATALOG.products.filter(p => p.installed_version!==null);
  $("#installedGrid").innerHTML = items.map(cardHTML).join("");
  $("#installedEmpty").classList.toggle("hidden", items.length>0);
  bindCards("#installedGrid");
}
function renderNews(){
  const items = CATALOG.products.filter(p => p.changelog_url || p.notes);
  $("#newsList").innerHTML = items.map(p => `<div class="item">
    <div><div class="t">${p.name} v${p.version}</div><div class="s">${p.notes || (p.category)}</div></div>
    ${p.changelog_url?`<button class="btn ghost" data-url="${p.changelog_url}"><i class="ti ti-external-link"></i>Changelog</button>`:""}
  </div>`).join("");
  $$("#newsList button[data-url]").forEach(b => b.addEventListener("click", () => api().open_url(b.dataset.url)));
}
function renderLinks(){
  const links = CATALOG.links || [];
  $("#linksGrid").innerHTML = links.map(l => `<div class="link-card" data-url="${l.url}">
    <i class="ti ${l.icon||"ti-link"}"></i><span>${l.label}</span><i class="ti ti-external-link ext"></i></div>`).join("");
  $("#linksEmpty").classList.toggle("hidden", links.length>0);
  $$("#linksGrid .link-card").forEach(c => c.addEventListener("click", () => api().open_url(c.dataset.url)));
}

/* ------------------------------------------------------------------ fiche détaillée */
function openDetail(id){
  const p = CATALOG.products.find(x=>x.id===id); if (!p) return;
  $("#modalName").textContent = p.name;
  $("#modalSub").textContent = (CATALOG.categories.find(c=>c.id===p.category)||{}).label || p.category;
  $("#modalDesc").textContent = p.long_description || p.description || "";
  const th = $("#modalThumb"); th.className = "modal-thumb "+thumbAccent(p); th.innerHTML = `<i class="ti ${thumbIcon(p)}"></i>`;
  $("#modalHistory").innerHTML = (p.history||[]).map(h => `<div class="hist"><div class="hv">v${h.version}</div><div class="hn">${h.notes||""}</div></div>`).join("") || `<div class="hn" style="color:var(--muted);font-size:12px">Pas d'historique.</div>`;
  const acts = [];
  if (p.status!=="uptodate") acts.push(`<button class="act-${p.status}" data-act="install">${actionLabel(p.status)}</button>`);
  if (p.installed_version!==null) acts.push(`<button class="act-update" data-act="uninstall" style="background:#3a1d1d;color:#f0b3b3">Désinstaller</button>`);
  if (p.changelog_url) acts.push(`<button class="act-install" data-act="changelog" style="background:var(--bg3);color:var(--txt)">Changelog ↗</button>`);
  $("#modalActions").innerHTML = acts.join("");
  $$("#modalActions button").forEach(b => b.addEventListener("click", () => {
    const a = b.dataset.act; closeModal();
    if (a==="install") onAction(id);
    else if (a==="uninstall") doUninstall(id);
    else if (a==="changelog") api().open_url(p.changelog_url);
  }));
  $("#modal").classList.remove("hidden");
}
function closeModal(){ $("#modal").classList.add("hidden"); }

/* ------------------------------------------------------------------ actions */
async function onAction(id){
  const p = CATALOG.products.find(x => x.id===id);
  if (!p || p.status==="uptodate") return;
  if (!CATALOG.wow_valid){ switchTab("settings"); toast("Choisis d'abord ton dossier Ebonhold.","err"); return; }
  startCardProgress(id);
  if (VIEW!=="cards") toast("Installation…", "info", p.name);
  const r = await api().install_product(id);
  if (!r.started){ setMsg(id, r.error||"Erreur."); resetAction(id); toast(r.error||"Erreur.","err"); }
}
async function installPack(pid){
  if (!CATALOG.wow_valid){ switchTab("settings"); toast("Choisis d'abord ton dossier Ebonhold.","err"); return; }
  const pk = CATALOG.packs.find(x=>x.id===pid);
  const r = await api().install_pack(pid);
  if (r.started){ (r.ids||pk.products).forEach(startCardProgress); toast("Installation du pack…","ok", pk?pk.name:""); }
  else toast(r.error||"Erreur.","err");
}
function onUninstall(btn){
  const id = btn.dataset.uid;
  if (btn.dataset.confirm){ doUninstall(id); return; }
  btn.dataset.confirm="1"; btn.textContent="Confirmer ?";
  setTimeout(() => { if (btn.isConnected){ btn.removeAttribute("data-confirm"); btn.textContent="Désinstaller"; } }, 3000);
}
async function doUninstall(id){
  const p = CATALOG.products.find(x=>x.id===id);
  const r = await api().uninstall_product(id);
  if (r.ok){ toast("Désinstallé.","ok", p?p.name:""); await reload(); } else toast(r.error||"Erreur.","err");
}
function startCardProgress(id){
  $$(`[data-id="${id}"] .actbtn`).forEach(b => b.disabled = true);
  $$(`.card[data-id="${id}"]`).forEach(card => {
    card.querySelector(".progress").classList.remove("hidden");
    card.querySelector(".progress-msg").classList.remove("hidden");
  });
}
const setBar = (id,pct) => $$(`.card[data-id="${id}"] .progress > i`).forEach(b => b.style.width=pct+"%");
const setMsg = (id,msg) => $$(`.card[data-id="${id}"] .progress-msg`).forEach(m => m.textContent=msg);
const resetAction = id => $$(`[data-id="${id}"] .actbtn`).forEach(b => b.disabled=false);

window.onProgress = (id,pct,msg) => { setBar(id,pct); setMsg(id,msg); };
window.onDone = async (id,ok,msg) => {
  setMsg(id,msg); const p = CATALOG.products.find(x=>x.id===id);
  if (ok){ setBar(id,100); toast(msg,"ok",p?p.name:""); await reload(); } else { resetAction(id); toast(msg,"err",p?p.name:""); }
};
async function updateAll(){
  const r = await api().install_all();
  filtered().filter(p=>p.status!=="uptodate").forEach(p => startCardProgress(p.id));
  if (r.count===0) toast("Tout est déjà à jour.","ok");
}

/* ------------------------------------------------------------------ auto-update launcher */
async function updateLauncher(){
  toast("Vérification…","info","Launcher");
  const r = await api().update_launcher();
  if (r.mode==="dev"){ api().open_url(r.url); toast("Page de téléchargement ouverte (version dev).","ok","Launcher"); }
  else if (r.ok){ toast("Téléchargement de la mise à jour…","ok","Launcher"); }
  else toast(r.error||"Erreur.","err","Launcher");
}
window.onLauncherProgress = (pct,msg) => toast(`${msg} ${pct}%`,"info","Launcher");
window.onLauncherReady = () => toast("Mise à jour prête, redémarrage…","ok","Launcher");
window.onLauncherError = (msg) => toast(msg,"err","Launcher");

/* ------------------------------------------------------------------ config FR */
let FR_PACK_URL = "";
let FR_PACK_INSTALLABLE = false;
async function loadFrStatus(){
  const s = await api().get_fr_status();
  $("#frControls").classList.toggle("hidden", !s.available);
  const warn = $("#frUnavailable");
  if (!s.available){ warn.textContent = s.error || "Configuration FR indisponible."; warn.classList.remove("hidden"); } else warn.classList.add("hidden");
  $("#frPackHint").textContent = (!s.pack_present) ? "Pack frFR requis pour Jeu = FR" : "";
  // Bloc pack : visible seulement si le pack n'est pas deja present (et qu'on a un lien ou une install auto).
  FR_PACK_URL = s.pack_url || "";
  FR_PACK_INSTALLABLE = !!s.pack_installable;
  const show = s.available && !s.pack_present && (FR_PACK_INSTALLABLE || !!FR_PACK_URL);
  $("#frPack").classList.toggle("hidden", !show);
  if (show){
    $("#frPackNote").textContent = s.pack_note || "Pack ~2,4 Go requis pour le français complet.";
    const btn = $("#frPackBtn");
    btn.innerHTML = FR_PACK_INSTALLABLE
      ? '<i class="ti ti-download"></i>Installer le pack FR'
      : '<i class="ti ti-external-link"></i>Télécharger le pack FR';
  }
}
function frSet(v){ ["frBase","frVoices","frSpells","frOther"].forEach(id => $("#"+id).value=v); }
async function applyFr(){
  const log = $("#frLog"); log.textContent=""; log.classList.remove("hidden"); $("#frApply").disabled = true;
  const r = await api().apply_fr_config($("#frBase").value==="FR", $("#frVoices").value==="FR", $("#frSpells").value==="FR", $("#frOther").value==="FR");
  if (!r.started){ $("#frApply").disabled=false; toast(r.error||"Erreur.","err"); }
}
window.onFrLog = (msg) => { const l=$("#frLog"); l.classList.remove("hidden"); l.textContent += msg+"\n"; l.scrollTop=l.scrollHeight; };
window.onFrDone = (ok,msg) => { $("#frApply").disabled=false; window.onFrLog((ok?"✓ ":"✗ ")+msg); toast(msg, ok?"ok":"err", "Config FR"); };

async function installOrOpenPack(){
  if (!FR_PACK_INSTALLABLE){
    if (FR_PACK_URL){ api().open_url(FR_PACK_URL); toast("Page de téléchargement du pack ouverte.","ok","Pack FR"); }
    return;
  }
  const btn = $("#frPackBtn"); btn.disabled = true;
  $("#frPackProgress").textContent = "Préparation…";
  const r = await api().install_fr_pack();
  if (!r.started){ btn.disabled=false; $("#frPackProgress").textContent=""; toast(r.error||"Erreur.","err","Pack FR"); }
}
window.onPackProgress = (pct,msg) => { $("#frPackProgress").textContent = msg; };
window.onPackDone = async (ok,msg) => {
  $("#frPackBtn").disabled = false;
  $("#frPackProgress").textContent = ok ? "" : msg;
  toast(msg, ok?"ok":"err", "Pack FR");
  if (ok){ await loadFrStatus(); }   // le bloc pack disparait si le pack est maintenant present
};

/* ------------------------------------------------------------------ chargement */
// reload(false) = local instantané ; reload(true) = local instantané + check réseau en fond.
async function reload(checkRemote=false){ CATALOG = await api().get_catalog(checkRemote); renderCatalog(); }
// Poussé par le backend quand le catalogue en ligne a été récupéré en arrière-plan.
window.onCatalogUpdate = (cat) => { CATALOG = cat; renderCatalog(); };
async function pickFolder(){
  const r = await api().choose_folder();
  if (r.error){ $("#folderValid").textContent=r.error; $("#folderValid").className="folder-valid bad"; toast(r.error,"err"); }
  await reload(); loadFrStatus();
}
async function play(){ const r = await api().launch_game(); if (!r.ok) toast(r.error||"Lancement impossible.","err"); else toast("Lancement du jeu…","ok"); }
async function openAddons(){ const r = await api().open_addons_folder(); if (!r.ok) toast(r.error||"Erreur.","err"); }

function bind(){
  $$(".nav-item").forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  $("#refreshBtn").addEventListener("click", () => { reload(true); toast("Vérification des nouveautés…","ok"); });
  $("#updateAllBtn").addEventListener("click", updateAll);
  $("#playBtn").addEventListener("click", play);
  $("#folderBtn").addEventListener("click", pickFolder);
  $("#openAddonsBtn").addEventListener("click", openAddons);
  $("#frAllFr").addEventListener("click", () => frSet("FR"));
  $("#frAllEn").addEventListener("click", () => frSet("EN"));
  $("#frApply").addEventListener("click", applyFr);
  $("#frPackBtn").addEventListener("click", installOrOpenPack);
  $("#searchInput").addEventListener("input", e => { FILTER.term = e.target.value; renderGrid(); });
  $$(".view-toggle button").forEach(b => { b.classList.toggle("active", b.dataset.view===VIEW); b.addEventListener("click", () => setView(b.dataset.view)); });
  $("#launcherUpdateBtn").addEventListener("click", updateLauncher);
  $("#modalClose").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", e => { if (e.target.id==="modal") closeModal(); });
}
let _bound = false, _started = false;
function start(){ if (_started) return; _started = true; if (!_bound){ _bound=true; bind(); } reload(true); }

// Le pont pywebview (window.pywebview.api) est injecté de façon asynchrone par WebView2,
// et l'événement "pywebviewready" est lent/peu fiable. On SONDE donc activement la
// disponibilité de l'api et on démarre dès qu'elle répond (au lieu d'attendre l'événement).
(function waitForBridge(){
  let tries = 0;
  const iv = setInterval(() => {
    if (window.pywebview && window.pywebview.api){ clearInterval(iv); start(); }
    else if (++tries >= 150){ clearInterval(iv); start(); }   // ~30s : filet (preview navigateur -> MOCK)
  }, 200);
})();
window.addEventListener("pywebviewready", start);   // ceinture + bretelles
