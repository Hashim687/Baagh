const state={token:localStorage.getItem('baagh_token')||'',user:JSON.parse(localStorage.getItem('baagh_user')||'null'),activeTab:'overview',searchTimer:null,marketCache:[],modalBusy:false};
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=value=>'₹'+Number(value||0).toLocaleString('en-IN',{maximumFractionDigits:2});
const num=value=>Number(value||0).toLocaleString('en-IN',{maximumFractionDigits:1});
const cropEmoji={Apple:'🍎',Walnut:'🌰',Almond:'🥜',Saffron:'🌸'};
function toast(message,type='success'){const root=$('toastRoot');root.innerHTML=`<div class="toast ${type==='error'?'error':'success'}" role="status">${esc(message)}</div>`;clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>{root.innerHTML=''},3600)}
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(state.token)headers.Authorization='Bearer '+state.token;let response;try{response=await fetch(path,{...options,headers})}catch(e){throw new Error('Could not connect to Baagh API. Start the backend using the setup instructions and reload this page.')}let data;try{data=await response.json()}catch{data={}}if(!response.ok){if(response.status===401&&state.token){state.token='';state.user=null;localStorage.removeItem('baagh_token');localStorage.removeItem('baagh_user')}throw new Error(data.detail||'Something went wrong. Please try again.')}return data}
function closeMenu(){$('navLinks').classList.remove('open')};function toggleMenu(){$('navLinks').classList.toggle('open')};function goHome(e){if(e)e.preventDefault();showHome();window.scrollTo({top:0,behavior:'smooth'});return false}
function jumpToMarketplace(){showHome();$('marketplace').scrollIntoView({behavior:'smooth'})}
function setCropAndJump(crop){showHome();$('cropFilter').value=crop;loadMarketplace();$('marketplace').scrollIntoView({behavior:'smooth'})}
function debouncedMarketplace(){clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadMarketplace,250)}
function resetMarketFilters(){$('marketSearch').value='';$('cropFilter').value='All';$('districtFilter').value='All';loadMarketplace()}
function cardImage(crop){return ({Apple:'https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?auto=format&fit=crop&w=850&q=80',Walnut:'https://images.unsplash.com/photo-1603048719539-9ecb4aa395e3?auto=format&fit=crop&w=850&q=80',Almond:'https://images.unsplash.com/photo-1508061253366-f7da158b6d46?auto=format&fit=crop&w=850&q=80'})[crop]||''}
function pillStatus(status){const klass=['pending','rejected','declined','removed'].includes(String(status).toLowerCase())?'pending':String(status).toLowerCase().includes('transit')?'transit':'';return `<span class="status ${klass}">${esc(status||'—')}</span>`}
async function loadSummary(){try{const s=await api('/api/summary');$('statListings').textContent=num(s.open_listings);$('statMembers').textContent=num(s.verified_members);$('statDistricts').textContent=num(s.districts)}catch(e){$('statListings').textContent='—';$('statMembers').textContent='—';$('statDistricts').textContent='—'}}
function favoriteListing(button,id){button.textContent=button.textContent==='♡'?'♥':'♡';button.style.color=button.textContent==='♥'?'#d45b45':'';toast(button.textContent==='♥'?'Saved for this visit':'Removed from saved list')}
async function loadRates(){try{const rows=await api('/api/rates');$('ratesRows').innerHTML=rows.slice(0,5).map(r=>`<div class="rate-row"><span class="rate-crop"><span class="crop-mini">${cropEmoji[r.crop]||'🌿'}</span>${esc(r.crop)}</span><span class="rate-location">${esc(r.mandi)}</span><span class="rate-price">${money(r.price_per_kg)}</span></div>`).join('')||'<div class="empty-mini">No rates have been published yet.</div>'}catch(e){$('ratesRows').innerHTML=`<div class="small">${esc(e.message)}</div>`}}
async function loadStoragePreview(){try{const rows=await api('/api/storage');$('storagePreview').innerHTML=rows.slice(0,3).map(s=>`<div style="padding:15px 16px;border:1px solid var(--line);background:white;border-radius:15px;display:flex;justify-content:space-between;align-items:center;gap:12px"><div style="display:flex;gap:12px;align-items:center;min-width:0"><span style="width:39px;height:39px;background:#e9f0e4;border-radius:12px;display:grid;place-items:center;font-size:19px;flex:none">❄️</span><span style="min-width:0"><strong style="display:block;font-size:12px">${esc(s.name)}</strong><span class="small">${esc(s.district)} · ${num(s.free_tonnes)} t free</span></span></div><strong style="font:800 13px Manrope;white-space:nowrap">${money(s.rate_per_kg_month)}<small style="font:400 9px 'DM Sans';color:var(--muted)">/kg/mo</small></strong></div>`).join('')}catch(e){$('storagePreview').innerHTML=`<div class="small">${esc(e.message)}</div>`}}
function closeModal(){$('modalRoot').innerHTML='';document.body.classList.remove('modal-open')}
function setSession(data){state.token=data.access_token;state.user=data.user;localStorage.setItem('baagh_token',state.token);localStorage.setItem('baagh_user',JSON.stringify(state.user));syncNav()}
function syncNav(){const logged=!!state.user;$('accountChip').classList.toggle('hidden',!logged);document.querySelectorAll('.nav-actions>.btn').forEach(el=>el.classList.toggle('hidden',logged));if(logged){$('navAvatar').textContent=(state.user.name||'B').trim().charAt(0).toUpperCase();$('navUserName').textContent=state.user.name.split(' ')[0];}}
function logout(){state.token='';state.user=null;state.activeTab='overview';localStorage.removeItem('baagh_token');localStorage.removeItem('baagh_user');syncNav();showHome();toast('You have logged out securely')}
function handleStorageCTA(){if(!state.user){openAuth('login');return}openDashboard('storage')}
function sideItems(role){if(state.user.must_change_password)return [['security','⚙','Change initial password']];let items=[['overview','▦','Overview']];if(role==='seller')items.push(['listings','🧺','My listings'],['offers','↔','Offers received'],['orders','🚚','Orders & tracking'],['buyers','🇮🇳','Find buyers'],['storage','❄','Cold storage'],['audit','▤','GST & audit reports']);if(role==='buyer')items.push(['market','⌕','Find produce'],['offers','↔','My offers'],['orders','🚚','Orders & tracking'],['disputes','⚑','Disputes'],['audit','▤','GST & audit reports']);if(role==='admin')items.push(['users','♙','Members'],['buyers','🇮🇳','Buyers by location'],['listings','🧺','All listings'],['offers','↔','Offer activity'],['orders','🚚','Orders'],['rates','📈','Market rates'],['storage','❄','Storage bookings'],['disputes','⚑','Disputes']);if(role==='inspector')items.push(['inspection','✓','Inspection queue']);items.push(['security','⚙','Security settings']);return items}
function renderSidebar(){const u=state.user;$('appSidebar').innerHTML=`<div class="sidebar-person"><span class="avatar">${esc((u.name||'B')[0].toUpperCase())}</span><span><strong>${esc(u.name)}</strong><small>${esc(u.role)} account · ${esc(u.member_code||'ID pending')}</small></span></div>${sideItems(u.role).map(([id,icon,label])=>`<button class="side-link ${state.activeTab===id?'active':''}" onclick="renderDashboard('${id}')"><span>${icon}</span>${label}</button>`).join('')}`}
function metric(label,value,icon,note=''){return `<div class="metric"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><strong>${value}</strong><small>${note}</small></div>`}
function panel(title,body,action=''){return `<section class="panel"><div class="panel-head"><div><h2>${title}</h2></div>${action}</div>${body}</section>`}
function table(headers,rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):`<tr><td colspan="${headers.length}"><div class="empty-mini"><strong>Nothing here just yet</strong>When there is activity, it will appear here.</div></td></tr>`}</tbody></table></div>`}
function actionButton(label,fn,kind='primary'){return `<button class="mini-btn ${kind}" onclick="${fn}">${label}</button>`}
function emptyPanel(title,body,action=''){return `<div class="empty-mini"><strong>${title}</strong>${body}${action?`<div style="margin-top:13px">${action}</div>`:''}</div>`}
async function renderDashboard(tab='overview'){if(state.user.must_change_password&&tab!=='security')tab='security';state.activeTab=tab;renderSidebar();$('appEyebrow').textContent=state.user.role==='admin'?'Marketplace control centre':'Your Baagh workspace';$('appTitle').textContent=tabTitle(tab);$('appSubtitle').textContent=tabSubtitle(tab);if(location.hash!=='#/app/'+tab)history.replaceState(null,'','#/app/'+tab);$('verificationAlert').classList.toggle('hidden',!!state.user.verified||state.user.role==='admin');if(!state.user.verified&&state.user.role!=='admin')$('verificationAlert').textContent='Your account has been suspended by a Baagh administrator. You can browse, but listing, offers and bookings are locked. Please contact support.';const content=$('appContent');content.innerHTML='<div class="loading"><div class="spinner"></div>Loading your workspace…</div>';try{if(!REFSYNC)REFSYNC=await loadRef();let html='';const role=state.user.role;
 if(tab==='overview')html=await overviewHTML();
 else if(tab==='listings')html=await listingsHTML();
 else if(tab==='market')html=marketDashboardHTML();
 else if(tab==='offers')html=await offersHTML();
 else if(tab==='orders')html=await ordersHTML();
 else if(tab==='rates')html=await ratesAdminHTML();
 else if(tab==='storage')html=await storageHTML();
 else if(tab==='users')html=await usersHTML();
 else if(tab==='audit')html=await auditHTML();
 else if(tab==='buyers')html=await buyersHTML();
 else if(tab==='security')html=securityHTML();
 else if(tab==='disputes')html=await disputesHTML();
 else html=await inspectionHTML();
 content.innerHTML=html; if(tab==='listings')wireListingForm(); if(tab==='rates'){} if(tab==='storage')wireStorageForm();if(tab==='market')wireDashboardSearch();if(tab==='buyers')loadBuyers();
 }catch(e){content.innerHTML=`<section class="panel">${emptyPanel('We could not load this section',esc(e.message),'<button class="btn btn-outline btn-sm" onclick="renderDashboard(\''+tab+'\')">Try again</button>')}</section>`}}
function tabTitle(tab){return ({overview:'Your overview',listings:state.user.role==='admin'?'All listings':'Your produce listings',market:'Find your next harvest',offers:state.user.role==='seller'?'Offers on your produce':'Your offers',orders:'Orders & tracking',rates:'Market rate management',storage:state.user.role==='admin'?'Storage bookings':'Cold storage',users:'Members',buyers:'Buyers across India',audit:'GST & audit reports',security:'Security settings',disputes:'Resolve trade issues',inspection:'Inspection queue'})[tab]||'Your dashboard'}
function tabSubtitle(tab){return ({overview:'A clear view of your orchard-to-market activity.',listings:'Manage listings, stock and produce details.',market:'Browse produce listed by verified growers.',offers:'Review proposals and move good deals forward.',orders:'Follow dispatch and delivery milestones.',rates:'Keep indicative rate references current.',storage:'Review storage availability and booking requests.',users:'Members are verified automatically by phone code. Suspend or reinstate when needed.',buyers:'Find verified buyers by state, district and pincode.',audit:'Download Tally-ready GST reports in Excel, then review your trade ledger and activity.',security:'Update your password and protect access to your Baagh account.',disputes:'Review reported issues with orders.',inspection:'Review listings waiting for inspection.'})[tab]||''}
async function overviewHTML(){const u=state.user;let metrics='',body='';if(u.role==='admin'){const d=await api('/api/admin/overview');const s=d.stats;metrics=metric('Community members',num(s.users),'🤝','excluding admin')+metric('Suspended members',num(s.pending_users),'🪪','locked accounts')+metric('Open produce listings',num(s.open_listings),'🍎','available to buyers')+metric('Pending offers',num(s.pending_offers),'↔','awaiting seller decision')+metric('Orders created',num(s.orders),'📦','accepted offers')+metric('Open disputes',num(s.open_disputes),'⚑','needs review');body=panel('Needs your attention',`<div class="dashboard-cards"><div class="record-card"><h3>Members</h3><p>See every buyer and seller; suspend or reinstate accounts.</p><div class="record-actions">${actionButton('Review members',"renderDashboard('users')")}</div></div><div class="record-card"><h3>Market rate board</h3><p>Update indicative reference prices.</p><div class="record-actions">${actionButton('Manage rates',"renderDashboard('rates')")}</div></div><div class="record-card"><h3>Storage requests</h3><p>Approve or reject capacity requests.</p><div class="record-actions">${actionButton('View bookings',"renderDashboard('storage')")}</div></div><div class="record-card"><h3>Trade disputes</h3><p>Review open buyer-reported issues.</p><div class="record-actions">${actionButton('Review disputes',"renderDashboard('disputes')")}</div></div></div>`)}
 else if(u.role==='seller'){const [ls,offers,orders,bookings]=await Promise.all([api('/api/my/listings'),api('/api/my/offers'),api('/api/orders'),api('/api/storage/bookings').catch(()=>[])]);metrics=metric('Active listings',ls.filter(x=>x.status==='open').length,'🧺','currently available')+metric('Pending offers',offers.filter(x=>x.status==='pending').length,'↔','awaiting your decision')+metric('Orders',orders.length,'📦','accepted offers')+metric('Storage requests',bookings.length,'❄','booking activity');body=panel('Quick actions',`<div class="dashboard-cards"><div class="record-card"><h3>List fresh produce</h3><p>Add crop, grade, quantity and asking price.</p><div class="record-actions">${actionButton('Create listing',"renderDashboard('listings')")}</div></div><div class="record-card"><h3>Review offers</h3><p>Compare buyer offers and accept a proposal.</p><div class="record-actions">${actionButton('View offers',"renderDashboard('offers')")}</div></div><div class="record-card"><h3>Reserve cold storage</h3><p>Request storage and check estimated costs.</p><div class="record-actions">${actionButton('Explore storage',"renderDashboard('storage')")}</div></div><div class="record-card"><h3>Track an order</h3><p>Update dispatch or delivery milestones.</p><div class="record-actions">${actionButton('Track orders',"renderDashboard('orders')")}</div></div></div>`)}
 else if(u.role==='buyer'){const [offers,orders]=await Promise.all([api('/api/my/offers'),api('/api/orders')]);metrics=metric('Offers sent',offers.length,'↔','across listings')+metric('Offers accepted',offers.filter(x=>x.status==='accepted').length,'✓','deals confirmed')+metric('Pending offers',offers.filter(x=>x.status==='pending').length,'⏳','seller response awaited')+metric('Orders',orders.length,'📦','your transactions');body=panel('Find good produce',`<div class="record-card"><h3>Explore the marketplace</h3><p>Compare crop, grade, asking price and available quantity, then send an offer.</p><div class="record-actions">${actionButton('Browse produce',"renderDashboard('market')")}</div></div>`)}
 else {const q=await api('/api/listings');metrics=metric('Open listings',q.length,'🧺','public produce listings')+metric('Awaiting inspection',q.filter(x=>x.inspection_status!=='inspected').length,'🔎','review queue');body=panel('Inspection workflow',`<div class="record-card"><h3>Review inspection requests</h3><p>Inspect listing details and update grade or inspection status through your inspection process.</p><div class="record-actions">${actionButton('Open inspection queue',"renderDashboard('inspection')")}</div></div>`)}return `<div class="dashboard-grid">${metrics}</div>${body}`}
async function listingsHTML(){if(state.user.role==='admin'){const d=await api('/api/admin/overview');return panel('All marketplace listings',table(['Produce','Seller','District','Available','Price / kg','Status','Action'],d.listings.map(l=>`<tr><td><strong>${esc(l.variety)}</strong><br><span class="small">${esc(l.crop)} · Grade ${esc(l.grade)}</span></td><td>${esc(l.seller_name)}</td><td>${esc(l.district)}</td><td>${num(l.available_kg)} kg</td><td>${money(l.price_per_kg)}</td><td>${pillStatus(l.status)}</td><td>${l.status==='open'?actionButton('Remove',`removeListing(${l.id})`,'danger'):'—'}</td></tr>`)))}const ls=await api('/api/my/listings');const form=state.user.role==='seller'?listingFormHTML():'';return `${form}${panel('Your listings',table(['Produce','Crop & grade','Available','Price / kg','Status','Offers','Action'],ls.map(l=>`<tr><td><strong>${esc(l.variety)}</strong><br><span class="small">${esc(l.district)}</span></td><td>${esc(l.crop)} · ${esc(l.grade)}</td><td>${num(l.available_kg)} kg</td><td>${money(l.price_per_kg)}</td><td>${pillStatus(l.status)}</td><td>${num(l.offer_count)}</td><td>${l.status==='open'?actionButton('Remove',`removeListing(${l.id})`,'danger'):'—'}</td></tr>`)))}`}
async function removeListing(id){if(!confirm('Remove this listing from the marketplace?'))return;try{await api('/api/listings/'+id,{method:'DELETE'});toast('Listing removed');renderDashboard(state.activeTab);loadMarketplace();loadSummary()}catch(e){toast(e.message,'error')}}
function wireDashboardSearch(){if($('dashboardSearch'))$('dashboardSearch').addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadDashboardMarket,220)});loadDashboardMarket()}
async function startOffer(id){if(!state.user){openAuth('login');return}if(state.user.role!=='buyer'){toast('Log in with a buyer account to make an offer.','error');return}try{if(!state.user.verified){toast('Your account is suspended, so offers are locked.','error');return}const l=await api('/api/listings/'+id);$('modalRoot').innerHTML=`<div class="overlay" onclick="if(event.target===this)closeModal()"><section class="modal" role="dialog" aria-modal="true"><div class="modal-head"><div><span class="eyebrow">Start a trade</span><h2>Make an offer</h2><span class="small">${esc(l.variety)} · ${esc(l.district)}</span></div><button class="icon-btn" onclick="closeModal()">✕</button></div><div class="modal-body"><div style="display:flex;justify-content:space-between;gap:10px;background:#eff4e9;padding:14px;border-radius:12px;margin-bottom:17px"><span><small class="muted">Asking price</small><strong style="display:block;font:800 20px Manrope">${money(l.price_per_kg)}<small style="font:400 11px 'DM Sans'">/kg</small></strong></span><span style="text-align:right"><small class="muted">Available</small><strong style="display:block;font:800 20px Manrope">${num(l.available_kg)} kg</strong></span></div><form onsubmit="submitOffer(event,${id},${l.available_kg},${l.price_per_kg})"><div class="form-group"><label>Offer price (₹ / kg)</label><input class="form-control" id="offerPrice" type="number" min="1" step="0.01" value="${l.price_per_kg}" required></div><div class="form-group"><label>Quantity (kg)</label><input class="form-control" id="offerQty" type="number" min="1" max="${l.available_kg}" value="${Math.min(500,l.available_kg)}" required></div><p class="form-help">Your offer is sent to the grower. No payment is collected by this prototype.</p><button class="btn btn-primary" style="width:100%" type="submit">Send offer ↗</button></form></div></section></div>`;document.body.classList.add('modal-open')}catch(e){toast(e.message,'error')}}
async function submitOffer(event,id,maxQty,ask){event.preventDefault();try{await api(`/api/listings/${id}/offers`,{method:'POST',body:JSON.stringify({offered_price:Number($('offerPrice').value),quantity_kg:Number($('offerQty').value)})});closeModal();toast('Offer sent to grower');if($('appView').classList.contains('hidden'))loadMarketplace();else renderDashboard(state.activeTab)}catch(e){toast(e.message,'error')}}
async function offersHTML(){const rows=await api('/api/my/offers');if(state.user.role==='admin')return panel('Marketplace offer activity',table(['Produce','Buyer','Seller','Offer / kg','Qty','Status',''],rows.map(o=>`<tr><td><strong>${esc(o.variety)}</strong><br><span class="small">${esc(o.crop)} · Grade ${esc(o.grade)}</span></td><td>${esc(o.buyer_name||'—')}</td><td>${esc(o.seller_name||'—')}</td><td>${money(o.offered_price)}</td><td>${num(o.quantity_kg)} kg</td><td>${pillStatus(o.status)}</td><td>—</td></tr>`)));if(state.user.role==='buyer')return panel('Your submitted offers',table(['Produce','Grower','Offer / kg','Quantity','Status',''],rows.map(o=>`<tr><td><strong>${esc(o.variety)}</strong><br><span class="small">${esc(o.crop)} · ${esc(o.district)}</span></td><td>${esc(o.seller_name)}</td><td>${money(o.offered_price)}</td><td>${num(o.quantity_kg)} kg</td><td>${pillStatus(o.status)}</td><td>—</td></tr>`)));return panel('Offers on your produce',table(['Produce','Buyer','Offered / kg','Quantity','Status','Decision'],rows.map(o=>`<tr><td><strong>${esc(o.variety)}</strong><br><span class="small">${esc(o.crop)} · Grade ${esc(o.grade)}</span></td><td>${esc(o.buyer_name||'Buyer')}</td><td>${money(o.offered_price)}</td><td>${num(o.quantity_kg)} kg</td><td>${pillStatus(o.status)}</td><td>${o.status==='pending'?`<div class="table-actions">${actionButton('Accept',`decideOffer(${o.id},'accept')`)}${actionButton('Decline',`decideOffer(${o.id},'decline')`,'danger')}</div>`:'—'}</td></tr>`)))}
async function decideOffer(id,decision){if(!confirm(`${decision==='accept'?'Accept':'Decline'} this offer?`))return;try{const r=await api(`/api/offers/${id}/decision?decision=${decision}`,{method:'POST'});toast(decision==='accept'?`Offer accepted. Order #${r.order_id} created.`:'Offer declined');renderDashboard('offers');loadSummary()}catch(e){toast(e.message,'error')}}
async function ordersHTML(){const rows=await api('/api/orders');return panel('Trade orders',table(['Order','Produce','Buyer','Grower','Qty','Value','Status','Payment','Action'],rows.map(o=>{let actions='—';if((state.user.role==='seller'||state.user.role==='admin')&&o.status==='Accepted')actions=actionButton('Dispatch',`orderAction(${o.id},'dispatch')`);else if((state.user.role==='seller'||state.user.role==='admin')&&o.status==='In transit')actions=actionButton('Mark delivered',`orderAction(${o.id},'deliver')`);else if(state.user.role==='buyer'&&o.status==='Delivered')actions=actionButton('Raise dispute',`raiseDispute(${o.id})`,'danger');return `<tr><td><strong>#${o.id}</strong><br><span class="small">${esc(String(o.created_at||'').slice(0,10))}</span></td><td>${esc(o.variety)}<br><span class="small">${esc(o.crop)}</span></td><td>${esc(o.buyer_name)}</td><td>${esc(o.seller_name)}</td><td>${num(o.quantity_kg)} kg</td><td>${money(o.quantity_kg*o.price_per_kg)}</td><td>${pillStatus(o.status)} ${o.status==='In transit'?`<div class="small">Demo progress ${Math.round((o.progress||0)*100)}%</div>`:''}</td><td>${pillStatus(o.payment_status)}</td><td>${actions}</td></tr>`})),`<span class="pill gold">PAYMENTS NOT CONNECTED</span>`)}
async function orderAction(id,action){try{const r=await api(`/api/orders/${id}/${action}`,{method:'POST'});toast(action==='dispatch'?'Order marked in transit': 'Order marked delivered');renderDashboard('orders')}catch(e){toast(e.message,'error')}}
function raiseDispute(id){$('modalRoot').innerHTML=`<div class="overlay" onclick="if(event.target===this)closeModal()"><section class="modal" role="dialog" aria-modal="true"><div class="modal-head"><div><span class="eyebrow">Order #${id}</span><h2>Raise a dispute</h2><span class="small">Tell us what was different from the agreed produce.</span></div><button class="icon-btn" onclick="closeModal()">✕</button></div><div class="modal-body"><form onsubmit="submitDispute(event,${id})"><div class="form-group"><label>Grade received</label><select id="disputeGrade" class="form-control"><option>A</option><option>B</option><option>C</option></select></div><div class="form-group"><label>Describe the issue</label><textarea class="form-control" id="disputeReason" required minlength="5" maxlength="1500" rows="4" placeholder="e.g. Several crates arrived bruised…"></textarea></div><p class="form-help">This creates a review request. No actual payment is held or adjusted by the prototype.</p><button class="btn btn-primary" style="width:100%">Submit dispute</button></form></div></section></div>`;document.body.classList.add('modal-open')}
async function submitDispute(event,id){event.preventDefault();try{await api(`/api/orders/${id}/disputes`,{method:'POST',body:JSON.stringify({received_grade:$('disputeGrade').value,reason:$('disputeReason').value.trim()})});closeModal();toast('Dispute submitted for review');renderDashboard('orders')}catch(e){toast(e.message,'error')}}
async function saveRate(event){event.preventDefault();try{await api('/api/rates',{method:'POST',body:JSON.stringify({crop:$('rateCrop').value,mandi:$('rateMandi').value.trim(),price_per_kg:Number($('ratePrice').value)})});toast('Market rate saved');renderDashboard('rates');loadRates()}catch(e){toast(e.message,'error')}}
async function storageHTML(){const sites=await api('/api/storage');let bookings=[];if(state.user.role!=='buyer'&&state.user.role!=='inspector')bookings=await api('/api/storage/bookings').catch(()=>[]);const siteCards=sites.map(s=>`<div class="record-card"><div style="display:flex;align-items:start;justify-content:space-between;gap:12px"><div><h3>❄️ ${esc(s.name)}</h3><p>📍 ${esc(s.district)} · ${esc(s.temperature)}</p></div><span class="pill">${esc(s.suitable_for)}</span></div><div style="height:7px;background:#edf1e8;border-radius:10px;margin:15px 0 7px;overflow:hidden"><div style="height:100%;width:${Math.min(100,(s.occupied_tonnes/s.capacity_tonnes)*100)}%;background:var(--leaf);border-radius:10px"></div></div><p>${num(s.free_tonnes)} t available out of ${num(s.capacity_tonnes)} t</p><div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px"><strong style="font:800 17px Manrope">${money(s.rate_per_kg_month)}<small style="font:400 10px 'DM Sans';color:var(--muted)"> / kg / month</small></strong>${state.user.role==='seller'?actionButton('Request space',`selectStorage(${s.id})`):''}</div></div>`).join('');let form='';if(state.user.role==='seller')form=panel('Request storage space',`<form id="storageForm" class="listing-form" onsubmit="submitBooking(event)"><div class="form-group"><label>Storage site</label><select class="form-control" id="storageSite">${sites.map(s=>`<option value="${s.id}">${esc(s.name)} — ${esc(s.district)} · ${money(s.rate_per_kg_month)}/kg/month</option>`).join('')}</select></div><div class="form-group"><label>Quantity (kg)</label><input class="form-control" id="storageQty" type="number" min="1" required value="1000" oninput="estimateStorage()"></div><div class="form-group"><label>Duration (months)</label><input class="form-control" id="storageMonths" type="number" min="1" max="24" required value="2" oninput="estimateStorage()"></div><div class="form-group"><label>Estimated cost</label><div id="storageEstimate" style="font:800 22px Manrope;color:var(--forest);padding:11px 0">${money(4000)}</div></div><div class="form-group" style="grid-column:1/-1"><button class="btn btn-primary" type="submit">Request booking ↗</button><p class="form-help">Estimate only. Booking requests are reviewed by the administrator; no storage contract or payment is created here.</p></div></form>`);let rows=bookings.length?table(['Storage','Seller','Quantity','Duration','Estimate','Status','Decision'],bookings.map(b=>`<tr><td><strong>${esc(b.storage_name)}</strong><br><span class="small">${esc(b.district)}</span></td><td>${esc(b.seller_name)}</td><td>${num(b.quantity_kg)} kg</td><td>${b.months} mo</td><td>${money(b.estimated_cost)}</td><td>${pillStatus(b.status)}</td><td>${state.user.role==='admin'&&b.status==='pending'?`${actionButton('Approve',`bookingDecision(${b.id},'approve')`)} ${actionButton('Reject',`bookingDecision(${b.id},'reject')`,'danger')}`:'—'}</td></tr>`)):'<div class="empty-mini"><strong>No booking requests yet</strong>Seller booking requests will appear here.</div>';return `${panel('Storage directory',`<div class="dashboard-cards">${siteCards}</div>`)}${form}${panel(state.user.role==='admin'?'Booking requests':'Your booking requests',rows)}`}
function wireStorageForm(){estimateStorage()}
function selectStorage(id){$('storageSite').value=id;estimateStorage();$('storageForm').scrollIntoView({behavior:'smooth',block:'center'})}
function estimateStorage(){if(!$('storageSite'))return;const options=[...$('storageSite').options];const selected=options.find(o=>o.value===$('storageSite').value);const siteName=selected?selected.textContent:'';const rateMatch=siteName.match(/₹([\d,.]+)/);const rate=rateMatch?Number(rateMatch[1].replace(/,/g,'')):0;$('storageEstimate').textContent=money(rate*(Number($('storageQty').value)||0)*(Number($('storageMonths').value)||0))}
async function submitBooking(event){event.preventDefault();try{const data=await api('/api/storage/bookings',{method:'POST',body:JSON.stringify({storage_id:Number($('storageSite').value),quantity_kg:Number($('storageQty').value),months:Number($('storageMonths').value)})});toast('Storage booking requested. Estimate: '+money(data.estimated_cost));renderDashboard('storage')}catch(e){toast(e.message,'error')}}
async function bookingDecision(id,decision){try{await api(`/api/storage/bookings/${id}/decision?decision=${decision}`,{method:'POST'});toast('Booking '+(decision==='approve'?'approved':'rejected'));renderDashboard('storage')}catch(e){toast(e.message,'error')}}
async function auditBaseHTML(){if(!['seller','buyer'].includes(state.user.role))return panel('Business audit report',emptyPanel('Available to buyers and sellers','Sign in with a buyer or seller account to view a personal trade ledger.'));const d=await api('/api/my/audit-summary');const s=d.summary;const summaryCards=metric(state.user.role==='seller'?'Total sales value':'Total purchase value',money(s.total_trade_value),'₹','All accepted orders; payment not verified')+metric('Delivered trade value',money(s.delivered_trade_value),'✓','Delivered orders only')+metric('Trade orders',num(s.orders),'📦',`${num(s.delivered_orders)} delivered`)+metric('Quantity traded',num(s.total_quantity_kg)+' kg','⚖','Across all orders');const tradeRows=d.trades.map(t=>`<tr><td><strong>#${t.id}</strong><br><span class="small">${esc(String(t.created_at||'').replace('T',' ').slice(0,16))}</span></td><td>${esc(t.crop)}<br><span class="small">${esc(t.variety)}</span></td><td>${esc(t.counterparty_name||'—')}<br><span class="small">${esc(t.counterparty_member_code||'')}</span></td><td>${num(t.quantity_kg)} kg</td><td>${money(t.price_per_kg)}</td><td><strong>${money(t.trade_value)}</strong></td><td>${pillStatus(t.status)}</td><td>${pillStatus(t.payment_status)}</td></tr>`);const offerRows=d.offers.map(o=>`<tr><td>#${o.id}</td><td>${esc(o.crop)} · ${esc(o.variety)}</td><td>${esc(o.counterparty_name||'—')}<br><span class="small">${esc(o.counterparty_member_code||'')}</span></td><td>${num(o.quantity_kg)} kg</td><td>${money(o.offered_price)}</td><td>${money(Number(o.quantity_kg)*Number(o.offered_price))}</td><td>${pillStatus(o.status)}</td><td>${esc(String(o.created_at||'').slice(0,10))}</td></tr>`);const listingRows=d.listings.map(l=>`<tr><td>#${l.id}</td><td>${esc(l.crop)} · ${esc(l.variety)}</td><td>${esc(l.grade)}</td><td>${num(l.quantity_kg)} / ${num(l.available_kg)} kg</td><td>${money(l.price_per_kg)}</td><td>${pillStatus(l.status)}</td><td>${esc(String(l.created_at||'').slice(0,10))}</td></tr>`);const bookingRows=d.storage_bookings.map(b=>`<tr><td>#${b.id}</td><td>${esc(b.storage_name)} · ${esc(b.storage_district)}</td><td>${num(b.quantity_kg)} kg</td><td>${b.months}</td><td>${money(b.estimated_cost)}</td><td>${pillStatus(b.status)}</td><td>${esc(String(b.created_at||'').slice(0,10))}</td></tr>`);const activityRows=d.activity.map(a=>`<tr><td>${esc(String(a.created_at||'').replace('T',' ').slice(0,16))}</td><td><strong>${esc(a.event_type.replaceAll('_',' '))}</strong><br><span class="small">${esc(a.entity_type)} #${esc(a.entity_id)}</span></td><td>${esc(a.actor_name||'System')}</td><td>${esc(a.target_name||'—')}</td><td style="white-space:normal;max-width:250px">${esc(JSON.stringify(a.details||{}))}</td></tr>`);const note=`<div class="alert"><strong>Important accounting note:</strong> Trade value is calculated from accepted order quantity × agreed unit price. The prototype does not process or verify actual payments, so this is a business ledger—not a bank statement, GST invoice or proof of payment.</div>`;return `<div class="dashboard-grid">${summaryCards}</div>${note}${panel('Business audit report',`<p class="form-help">Unique member ID: <strong>${esc(d.member.member_code)}</strong> · ${esc(d.member.name)} · ${esc(d.member.role)} · Generated ${esc(new Date().toLocaleString())}</p><div class="record-actions"><button class="btn btn-primary btn-sm" onclick="downloadAuditReport()">Download complete CSV report ↓</button><button class="btn btn-outline btn-sm" onclick="renderDashboard('audit')">Refresh report ↻</button></div>`)}${panel('Trade ledger',table(['Order / date','Produce','Counterparty / member ID','Quantity','Unit price','Agreed value','Order status','Payment status'],tradeRows))}${panel('Offer history',table(['Offer','Produce','Counterparty / member ID','Quantity','Offer price','Calculated offer value','Status','Date'],offerRows))}${state.user.role==='seller'?panel('Produce listing ledger',table(['Listing','Produce','Grade','Original / available qty','Asking price','Status','Created'],listingRows)):''}${state.user.role==='seller'?panel('Cold storage booking ledger',table(['Booking','Storage / district','Quantity','Months','Estimate','Status','Created'],bookingRows)):''}${panel('Dispute ledger',table(['Dispute','Order','Produce','Reason','Grade received','Status','Resolution'],d.disputes.map(x=>`<tr><td>#${x.id}</td><td>#${x.order_id}</td><td>${esc(x.crop)} · ${esc(x.variety)}</td><td style="white-space:normal;max-width:240px">${esc(x.reason)}</td><td>${esc(x.received_grade)}</td><td>${pillStatus(x.status)}</td><td>${esc(x.resolution||'—')}</td></tr>`)))}${panel('Account activity audit trail',table(['Timestamp (UTC)','Event / reference','Actor','Related member','Details'],activityRows))}`}
async function downloadAuditReport(){try{const response=await fetch('/api/my/audit-report.csv',{headers:{Authorization:'Bearer '+state.token}});if(!response.ok){let err={};try{err=await response.json()}catch{}throw new Error(err.detail||'Could not generate audit report')}const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`baagh-audit-${(state.user.member_code||'member').toLowerCase()}.csv`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Audit report downloaded')}catch(e){toast(e.message,'error')}}
function securityHTML(){const force=!!state.user.must_change_password;return (force?'<div class="alert"><strong>First sign-in security step required.</strong><br>Change the one-time bootstrap administrator password before using any protected Baagh feature.</div>':'')+panel(force?'Set your private administrator password':'Change password',`<p class="form-help">Use a unique password with at least 12 characters. Do not reuse a password from another website.</p><form class="listing-form" onsubmit="submitPasswordChange(event)"><div class="form-group full"><label>Current password</label><input class="form-control" id="currentPassword" type="password" autocomplete="current-password" required maxlength="128"></div><div class="form-group"><label>New password</label><input class="form-control" id="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required placeholder="At least 12 characters"></div><div class="form-group"><label>Confirm new password</label><input class="form-control" id="confirmPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></div><div class="full"><button class="btn btn-primary" type="submit">Update password ↗</button></div></form>`)}
async function submitPasswordChange(event){event.preventDefault();const current=$('currentPassword').value,newPassword=$('newPassword').value;if(newPassword!==$('confirmPassword').value){toast('The new passwords do not match.','error');return}try{await api('/api/auth/change-password',{method:'POST',body:JSON.stringify({current_password:current,new_password:newPassword})});const wasForced=!!state.user.must_change_password;state.user.must_change_password=false;localStorage.setItem('baagh_user',JSON.stringify(state.user));$('currentPassword').value='';$('newPassword').value='';$('confirmPassword').value='';toast(wasForced?'Initial admin password changed. Full access is now enabled.':'Password changed successfully');if(wasForced)renderDashboard('overview');else renderDashboard('security')}catch(e){toast(e.message,'error')}}
async function disputesHTML(){const ds=await api('/api/disputes');const rows=ds.map(d=>{const action=state.user.role==='admin'&&d.status==='open'?`${actionButton('Suggest 10% adjustment',`resolveDispute(${d.id},'price_adjustment')`)} ${actionButton('Dismiss',`resolveDispute(${d.id},'dismiss')`,'danger')}`:esc(d.resolution||'—');return `<tr><td><strong>#${d.id}</strong></td><td>#${d.order_id}</td><td>${esc(d.variety)}<br><span class="small">${esc(d.crop)}</span></td><td>${esc(d.buyer_name)}</td><td>${esc(d.seller_name)}</td><td style="white-space:normal;min-width:150px">${esc(d.reason)}</td><td>${pillStatus(d.status)}</td><td>${action}</td></tr>`});return panel('Dispute review',table(['Dispute','Order','Produce','Buyer','Seller','Reason','Status','Resolution'],rows))}
async function resolveDispute(id,resolution){if(!confirm(resolution==='price_adjustment'?'Record a recommended 10% price adjustment? No payment will be transferred.':'Dismiss this dispute?'))return;try{await api(`/api/disputes/${id}/resolve?resolution=${resolution}`,{method:'POST'});toast('Dispute updated');renderDashboard('disputes')}catch(e){toast(e.message,'error')}}
async function inspectionHTML(){const ls=await api('/api/inspections');const pending=ls.filter(l=>l.inspection_status!=='inspected');return panel('Inspection queue',pending.length?`<div class="dashboard-cards">${pending.map(l=>`<div class="record-card"><h3>${esc(l.variety)} · ${esc(l.crop)}</h3><p>Seller: ${esc(l.seller_name)}</p><p>${num(l.available_kg)} kg · Grade ${esc(l.grade)} · ${esc(l.district)}</p><p>Listing #${l.id} · ${esc(l.inspection_status)}</p><div class="record-actions">${actionButton('Mark inspected',`markInspection(${l.id},'inspected')`)}</div></div>`).join('')}</div>`:emptyPanel('Inspection queue is clear','All listings have been marked inspected.'))}
async function markInspection(id,status){try{await api(`/api/inspections/${id}?status=${status}`,{method:'POST'});toast('Inspection status updated');renderDashboard('inspection');loadMarketplace()}catch(e){toast(e.message,'error')}}
/* ===================== v2: reference data, routing, sign-up with OTP, catalog, GST ===================== */
let REF=null;
function loadRef(){
  if(!REF){
    REF=Promise.all([api('/api/catalog'),api('/api/geo/kashmir'),api('/api/geo/states'),api('/api/geo/countries'),api('/api/auth/config')])
      .then(([catalog,kashmir,states,countries,auth])=>{
        const jk=kashmir.districts.map(d=>d.district).concat(kashmir.ladakh);
        return {catalog,kashmir,states,countries,auth,jkDistricts:[...new Set(jk)].sort()};
      }).catch(e=>{REF=null;throw e});
  }
  return REF;
}
function cropInfo(ref,crop){return ref.catalog.crops.find(c=>c.crop===crop)}
function gstLabel(rate){return Number(rate)===0?'GST nil':'GST '+Number(rate)+'%'}
function fillSelect(el,items,{all=false,selected=''}={}){if(!el)return;el.innerHTML=(all?'<option>All</option>':'')+items.map(i=>{const v=typeof i==='string'?i:i.value,t=typeof i==='string'?i:i.label;return `<option value="${esc(v)}" ${v===selected?'selected':''}>${esc(t)}</option>`}).join('')}
function productPhoto(l){
  const src=cardImage(l.crop);
  const fallback=`<div class="photo-fallback" style="height:100%;display:grid;place-items:center;font-size:64px;background:linear-gradient(135deg,#dce8d7,#f4d7b6)">${cropEmoji[l.crop]||'🌿'}</div>`;
  return src?`<img src="${src}" alt="${esc(l.crop)} produce" loading="lazy" onerror="this.outerHTML=this.dataset.fb" data-fb="${esc(fallback)}">`:fallback;
}
function listingCardHTML(l){
  return `<article class="product-card"><div class="product-photo">${productPhoto(l)}<span class="pill quality ${l.inspection_status==='inspected'?'':'gold'}">${l.inspection_status==='inspected'?'✓ Inspected':'● '+esc(l.inspection_status||'unverified')}</span></div><div class="product-body"><span class="product-type">${cropEmoji[l.crop]||'🌿'} ${esc(l.crop)} · ${esc(l.grade_label||('Grade '+l.grade))}</span><h3>${esc(l.variety)}</h3><div class="loc">⌖ ${esc(l.district)} &nbsp;·&nbsp; ${esc(l.seller_name)} ${l.seller_verified?'✓':''}</div><div class="product-meta"><span class="pill">${num(l.available_kg)} kg available</span>${l.product_form?`<span class="pill gray">${esc(l.product_form)}</span>`:''}<span class="pill gold" title="HSN ${esc(l.hsn_code||'')}">${gstLabel(l.gst_rate||0)}</span></div><div class="product-bottom"><div class="product-price"><strong>${money(l.price_per_kg)}</strong><small>per kilogram</small></div><button class="btn btn-dark btn-sm" onclick="startOffer(${l.id})">Make an offer ↗</button></div></div></article>`;
}
async function loadMarketplace(){
  const target=$('marketListings');if(!target)return;
  target.innerHTML='<div class="empty-state"><div class="spinner" style="margin:0 auto 12px"></div>Finding the best of the harvest…</div>';
  const q=new URLSearchParams({crop:$('cropFilter').value,district:$('districtFilter').value,search:$('marketSearch').value.trim()});
  try{const rows=await api('/api/listings?'+q.toString());state.marketCache=rows;
    target.innerHTML=rows.length?rows.map(listingCardHTML).join(''):'<div class="empty-state"><b>No listings found just yet</b>Try another crop, district or search term.</div>';
  }catch(e){target.innerHTML=`<div class="empty-state"><b>We couldn't load listings</b>${esc(e.message)}<br><button class="btn btn-outline btn-sm" style="margin-top:13px" onclick="loadMarketplace()">Try again</button></div>`}
}
async function loadDashboardMarket(){
  const target=$('dashboardMarketGrid');if(!target)return;
  const q=new URLSearchParams({crop:$('dashboardCrop').value,district:$('dashboardDistrict').value,search:$('dashboardSearch').value.trim()});
  try{const ls=await api('/api/listings?'+q.toString());target.innerHTML=ls.length?ls.map(listingCardHTML).join(''):'<div class="empty-state"><b>No matching listings</b>Try changing your filters.</div>'}
  catch(e){target.innerHTML=`<div class="empty-state">${esc(e.message)}</div>`}
}
function marketDashboardHTML(){
  return `<section class="panel"><div class="panel-head"><div><h2>Marketplace</h2><p>Offers are available to buyer accounts.</p></div><button class="mini-btn" onclick="jumpToMarketplace()">Open full marketplace ↗</button></div><div class="market-toolbar"><label class="searchbox"><span>⌕</span><input id="dashboardSearch" type="search" placeholder="Search crop, variety…"></label><select id="dashboardCrop" onchange="loadDashboardMarket()"><option>All</option>${REFSYNC.catalog.crops.map(c=>`<option>${esc(c.crop)}</option>`).join('')}</select><select id="dashboardDistrict" onchange="loadDashboardMarket()"><option>All</option>${REFSYNC.jkDistricts.map(d=>`<option>${esc(d)}</option>`).join('')}</select></div><div id="dashboardMarketGrid" class="listing-grid"><div class="loading"><div class="spinner"></div>Loading listings…</div></div></section>`;
}
let REFSYNC=null;

/* ---------- Home page sections driven by the catalog ---------- */
async function initHomeData(){
  try{
    const ref=await loadRef();REFSYNC=ref;
    cropEmoji.Saffron='🌸';
    fillSelect($('cropFilter'),ref.catalog.crops.map(c=>c.crop),{all:true});
    const kash=ref.kashmir.districts.filter(d=>d.division==='Kashmir').map(d=>d.district);
    const other=ref.jkDistricts.filter(d=>!kash.includes(d));
    $('districtFilter').innerHTML='<option>All</option><optgroup label="Kashmir Division">'+kash.map(d=>`<option>${esc(d)}</option>`).join('')+'</optgroup><optgroup label="Other J&K / Ladakh">'+other.map(d=>`<option>${esc(d)}</option>`).join('')+'</optgroup>';
    if($('statCrops'))$('statCrops').textContent=ref.catalog.crops.length;
    renderKashmirMap(ref);
  }catch(e){console.warn('reference data failed',e)}
}
function renderKashmirMap(ref){
  const box=$('kashmirMap');if(!box)return;
  const rows=ref.kashmir.districts.filter(d=>d.division==='Kashmir');
  box.innerHTML=rows.map(d=>`<article class="record-card"><h3>📍 ${esc(d.district)}</h3><div class="product-meta" style="margin-top:10px">${Object.keys(d.crops).length?Object.entries(d.crops).map(([c,lvl])=>`<span class="pill ${lvl==='major'?'orange':''}">${cropEmoji[c]||'🌿'} ${esc(c)}${lvl==='major'?' ★':''}</span>`).join(''):'<span class="small">Mostly other produce</span>'}</div></article>`).join('');
  const note=$('kashmirNote');if(note)note.textContent=ref.kashmir.note+' ★ = leading producing district. Saffron is also grown in Kishtwar (Jammu division).';
}

/* ---------- Routing: the URL always says where you are, so refresh never jumps home ---------- */
const SITE_SECTIONS=['home','where-it-grows','marketplace','market-rates','storage','how-it-works'];
function routeFromHash(){
  const h=location.hash||'#home';
  if(h.startsWith('#/app/')){
    if(!state.user){history.replaceState(null,'','#home');showHome(false);openAuth('login');return}
    const tab=h.slice(6)||'overview';
    $('mainContent').classList.add('hidden');$('appView').classList.remove('hidden');document.querySelector('footer').classList.add('hidden');
    renderDashboard(tab);window.scrollTo({top:0});
  }else{
    const id=h.replace('#','')||'home';
    showHome(false);
    const el=document.getElementById(id);
    if(el)setTimeout(()=>el.scrollIntoView({behavior:'auto'}),60);
  }
}
window.addEventListener('hashchange',routeFromHash);
function showHome(scroll=true){
  $('appView').classList.add('hidden');$('mainContent').classList.remove('hidden');document.querySelector('footer').classList.remove('hidden');
  if(scroll){if((location.hash||'').startsWith('#/app/'))history.replaceState(null,'','#home');window.scrollTo({top:0,behavior:'smooth'})}
}
function openDashboard(tab){
  if(!state.user){openAuth('login');return}
  closeModal();
  const target='#/app/'+(state.user.must_change_password?'security':(tab||'overview'));
  if(location.hash===target)routeFromHash();else location.hash=target;
}
function watchSections(){
  if(!('IntersectionObserver' in window))return;
  const seen=new Map();
  const io=new IntersectionObserver(entries=>{
    entries.forEach(e=>seen.set(e.target.id,e.isIntersecting?e.intersectionRatio:0));
    if(!$('appView').classList.contains('hidden'))return;
    let best='',score=0;seen.forEach((v,k)=>{if(v>score){score=v;best=k}});
    if(best&&('#'+best)!==location.hash)history.replaceState(null,'','#'+best);
    document.querySelectorAll('.nav-links a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+best));
  },{threshold:[0.15,0.4,0.7]});
  SITE_SECTIONS.forEach(id=>{const el=document.getElementById(id);if(el)io.observe(el)});
}
async function loadInitial(){
  $('year').textContent=new Date().getFullYear();syncNav();
  if(state.token){try{const user=await api('/api/auth/me');state.user=user;localStorage.setItem('baagh_user',JSON.stringify(user));syncNav()}catch(e){state.user=null;syncNav()}}
  await Promise.all([initHomeData(),loadSummary(),loadMarketplace(),loadRates(),loadStoragePreview()]);
  routeFromHash();watchSections();
}

/* ---------- Sign up / log in with phone OTP ---------- */
function countryOptions(ref,selected='IN'){return ref.countries.map(c=>`<option value="${c.iso}" ${c.iso===selected?'selected':''}>${c.flag} ${esc(c.name)} (${c.dial})</option>`).join('')}
function phoneRule(ref,iso){const c=ref.countries.find(x=>x.iso===iso)||ref.countries[0];const len=c.lengths&&c.lengths.length?(c.lengths.length===1?`exactly ${c.lengths[0]} digits`:`${c.lengths[0]}–${c.lengths[c.lengths.length-1]} digits`):'a valid number';const extra=iso==='IN'?', starting with 6, 7, 8 or 9':'';return {c,text:`${c.name}: ${len}${extra}. Example: ${c.example||''}`}}
function openAuth(mode='login'){
  closeMenu();
  if(mode==='register'){openRegister();return}
  $('modalRoot').innerHTML=`<div class="overlay" role="presentation" onclick="if(event.target===this)closeModal()"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="authTitle"><div class="modal-head"><div><span class="eyebrow">Welcome back</span><h2 id="authTitle">Log in to Baagh</h2><span class="small">Pick up where your orchard-to-market journey left off.</span></div><button class="icon-btn" onclick="closeModal()" aria-label="Close">✕</button></div><div class="modal-body"><form id="authForm" onsubmit="submitLogin(event)"><div class="form-group"><label for="authPhone">Phone number or admin username</label><input class="form-control" id="authPhone" required minlength="3" maxlength="100" autocomplete="username" placeholder="10-digit mobile, +country-code number, or username"></div><div class="form-group"><label for="authPassword">Password</label><input class="form-control" type="password" id="authPassword" required maxlength="128" autocomplete="current-password" placeholder="Enter your password"></div><button class="btn btn-primary" style="width:100%" type="submit" id="authSubmit">Log in securely <span>↗</span></button></form><p class="form-help" style="margin-top:13px">New to Baagh? <a href="#" style="font-weight:800;color:var(--forest)" onclick="openAuth('register');return false">Create an account</a></p><div class="demo-logins"><b>Account security</b><p class="form-help">Outside India, start the number with + and your country code (for example +971501234567). Never share passwords or OTPs.</p></div></div></section></div>`;
  document.body.classList.add('modal-open');setTimeout(()=>{const f=$('authPhone');if(f)f.focus()},30);
}
async function submitLogin(event){
  event.preventDefault();const submit=$('authSubmit');submit.disabled=true;submit.textContent='Please wait…';
  try{const data=await api('/api/auth/login',{method:'POST',body:JSON.stringify({phone:$('authPhone').value.trim(),password:$('authPassword').value})});
    setSession(data);closeModal();toast('Welcome back, '+data.user.name);openDashboard('overview')}
  catch(e){toast(e.message,'error');submit.disabled=false;submit.textContent='Log in securely ↗'}
}
async function openRegister(){
  let ref;try{ref=await loadRef()}catch(e){toast(e.message,'error');return}
  const demoNote=ref.auth.sms==='unavailable'?'<div class="alert"><strong>SMS verification is not set up on this server.</strong> New accounts cannot be created until the administrator configures an SMS provider.</div>':ref.auth.sms==='demo'?'<div class="alert"><strong>Demo mode.</strong> No real SMS is sent. Your verification code will be shown on screen so you can test sign-up.</div>':'';
  $('modalRoot').innerHTML=`<div class="overlay" role="presentation" onclick="if(event.target===this)closeModal()"><section class="modal" style="width:min(560px,100%)" role="dialog" aria-modal="true" aria-labelledby="authTitle"><div class="modal-head"><div><span class="eyebrow">Join the valley network</span><h2 id="authTitle">Create your Baagh account</h2><span class="small">Verify your phone with a one-time code. No waiting for approval.</span></div><button class="icon-btn" onclick="closeModal()" aria-label="Close">✕</button></div><div class="modal-body" id="authBody">${demoNote}<form id="authForm" onsubmit="submitRegister(event)">
  <div class="form-row"><div class="form-group"><label for="authRole">I want to</label><select class="form-control" id="authRole" onchange="onRoleChange()"><option value="seller">Sell produce (J&K grower)</option><option value="buyer">Buy produce</option></select></div><div class="form-group"><label for="authCountry">Country</label><select class="form-control" id="authCountry" onchange="onCountryChange()">${countryOptions(ref)}</select></div></div>
  <div class="form-group"><label for="authName">Full name or business name</label><input class="form-control" id="authName" required minlength="2" maxlength="100" placeholder="e.g. Bashir Ahmad"></div>
  <div class="form-group"><label for="authPhone">Mobile number</label><div style="display:flex;gap:8px"><span id="dialPrefix" class="form-control" style="width:auto;display:grid;place-items:center;font-weight:800">+91</span><input class="form-control" id="authPhone" required inputmode="numeric" autocomplete="tel-national" maxlength="15" oninput="this.value=this.value.replace(/[^0-9]/g,'')" placeholder="Mobile number"></div><div class="form-help" id="phoneHint"></div></div>
  <div id="geoIndia"><div class="form-row"><div class="form-group"><label for="authState">State / UT</label><select class="form-control" id="authState" onchange="onStateChange()"></select></div><div class="form-group"><label for="authDistrict">District</label><select class="form-control" id="authDistrict" onchange="onDistrictChange()"></select></div></div>
  <div class="form-group"><label for="authPincode">Pincode <span class="muted" id="pinReq"></span></label><input class="form-control" id="authPincode" inputmode="numeric" maxlength="6" list="pinList" oninput="this.value=this.value.replace(/[^0-9]/g,'');onPincodeInput()" placeholder="6-digit pincode"><datalist id="pinList"></datalist><div class="form-help" id="pinHint"></div></div></div>
  <div id="geoForeign" class="hidden"><div class="form-row"><div class="form-group"><label for="authCity">City / region</label><input class="form-control" id="authCity" maxlength="80" placeholder="e.g. Dubai"></div><div class="form-group"><label for="authPostal">Postal code (optional)</label><input class="form-control" id="authPostal" maxlength="10"></div></div></div>
  <div class="form-group" id="gstinGroup"><label for="authGstin">GSTIN <span class="muted">(optional, needed to charge or claim GST)</span></label><input class="form-control" id="authGstin" maxlength="15" style="text-transform:uppercase" placeholder="07ABCDE1234F1Z5"><div class="form-help">Checked for format, checksum and that its state code matches your state.</div></div>
  <div class="form-group"><label for="authAddress">Address (optional)</label><input class="form-control" id="authAddress" maxlength="200" placeholder="Street / market / orchard location"></div>
  <div class="form-group"><label for="authPassword">Password</label><input class="form-control" type="password" id="authPassword" required minlength="12" maxlength="128" autocomplete="new-password" placeholder="At least 12 characters"></div>
  <button class="btn btn-primary" style="width:100%" type="submit" id="authSubmit" ${ref.auth.sms==='unavailable'?'disabled':''}>Send verification code <span>↗</span></button></form>
  <p class="form-help" style="margin-top:13px">Already registered? <a href="#" style="font-weight:800;color:var(--forest)" onclick="openAuth('login');return false">Log in</a></p></div></section></div>`;
  document.body.classList.add('modal-open');
  onRoleChange();setTimeout(()=>$('authName')&&$('authName').focus(),30);
}
function onRoleChange(){
  const seller=$('authRole').value==='seller';
  const ref=REFSYNC;if(!ref)return;
  if(seller){$('authCountry').value='IN'}
  $('authCountry').disabled=seller;
  $('pinReq').textContent=seller?'(optional)':'(required)';
  onCountryChange();
}
function onCountryChange(){
  const ref=REFSYNC,iso=$('authCountry').value,seller=$('authRole').value==='seller';
  const r=phoneRule(ref,iso);$('dialPrefix').textContent=r.c.dial;$('phoneHint').textContent=r.text;$('authPhone').maxLength=Math.max(r.c.max_len||15,8)+2;
  const india=iso==='IN';
  $('geoIndia').classList.toggle('hidden',!india);$('geoForeign').classList.toggle('hidden',india);$('gstinGroup').classList.toggle('hidden',!india);
  if(india){
    const states=ref.states.map(s=>s.name).filter(s=>!seller||s==='Jammu and Kashmir'||s==='Ladakh');
    fillSelect($('authState'),states,{selected:seller?'Jammu and Kashmir':'Delhi'});onStateChange();
  }
}
async function onStateChange(){
  const st=$('authState').value;
  try{const ds=await api('/api/geo/districts?state='+encodeURIComponent(st));fillSelect($('authDistrict'),ds);onDistrictChange()}catch(e){toast(e.message,'error')}
}
async function onDistrictChange(){
  $('pinHint').textContent='';$('authPincode').value='';
  try{const pins=await api(`/api/geo/pincodes?state=${encodeURIComponent($('authState').value)}&district=${encodeURIComponent($('authDistrict').value)}`);$('pinList').innerHTML=pins.map(p=>`<option value="${p}">`).join('');$('pinHint').textContent=pins.length?`${pins.length} pincodes in this district. Type yours or pick from the list.`:''}catch(e){}
}
let pinTimer=null;
function onPincodeInput(){
  clearTimeout(pinTimer);const pin=$('authPincode').value;
  if(pin.length!==6){$('pinHint').style.color='';return}
  pinTimer=setTimeout(async()=>{
    try{const found=await api('/api/geo/pincode/'+pin);const here=found.find(f=>f.state===$('authState').value&&f.district===$('authDistrict').value);
      if(here){$('pinHint').style.color='#2f7a3b';$('pinHint').textContent=`✓ ${here.district}, ${here.state}`;return}
      const f=found[0];$('authState').value=f.state;
      const ds=await api('/api/geo/districts?state='+encodeURIComponent(f.state));fillSelect($('authDistrict'),ds,{selected:f.district});
      $('pinHint').style.color='#2f7a3b';$('pinHint').textContent=`✓ Set to ${f.district}, ${f.state} from this pincode`;
    }catch(e){$('pinHint').style.color='#a53f31';$('pinHint').textContent=e.message}
  },250);
}
async function submitRegister(event){
  event.preventDefault();const submit=$('authSubmit');submit.disabled=true;submit.textContent='Sending code…';
  const iso=$('authCountry').value,india=iso==='IN';
  const body={name:$('authName').value.trim(),phone:$('authPhone').value.trim(),country:iso,password:$('authPassword').value,role:$('authRole').value,
    state:india?$('authState').value:'',district:india?$('authDistrict').value:$('authCity').value.trim(),pincode:india?$('authPincode').value.trim():$('authPostal').value.trim(),
    address:$('authAddress').value.trim(),gstin:india?$('authGstin').value.trim():''};
  try{const info=await api('/api/auth/register',{method:'POST',body:JSON.stringify(body)});state.pendingReg={phone:body.phone,country:iso};showOtpStep(info)}
  catch(e){toast(e.message,'error');submit.disabled=false;submit.textContent='Send verification code ↗'}
}
let resendTimer=null;
function showOtpStep(info){
  const demo=info.dev_otp?`<div class="alert"><strong>Demo code: ${esc(info.dev_otp)}</strong><br>No SMS was sent because no SMS provider is configured. This code is only shown in demo mode.</div>`:'';
  $('authBody').innerHTML=`<div class="alert" style="background:#eff4e9;border-color:#d2e2cb"><strong>Check your phone.</strong> ${esc(info.message)} Sent to ${esc(info.phone)}. The code expires in ${Math.round(info.expires_in_seconds/60)} minutes.</div>${demo}<form onsubmit="submitOtp(event)"><div class="form-group"><label for="otpInput">6-digit verification code</label><input class="form-control" id="otpInput" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" minlength="6" maxlength="6" required placeholder="000000" style="font:800 24px Manrope;letter-spacing:8px;text-align:center" oninput="this.value=this.value.replace(/[^0-9]/g,'')"></div><button class="btn btn-primary" style="width:100%" type="submit" id="otpSubmit">Verify &amp; create account <span>↗</span></button></form><p class="form-help" style="margin-top:13px"><button class="mini-btn" id="resendBtn" onclick="resendOtp()" disabled>Resend code</button> <span id="resendInfo"></span></p><p class="form-help"><a href="#" style="font-weight:800;color:var(--forest)" onclick="openRegister();return false">← Change my details or phone number</a></p>`;
  setTimeout(()=>$('otpInput')&&$('otpInput').focus(),30);startResendCountdown(info.resend_after_seconds||0);
}
function startResendCountdown(sec){
  clearInterval(resendTimer);let left=sec;const btn=()=>$('resendBtn'),lab=()=>$('resendInfo');
  const tick=()=>{if(!btn())return clearInterval(resendTimer);if(left>0){btn().disabled=true;lab().textContent=`You can request a new code in ${left}s`;left--}else{btn().disabled=false;lab().textContent='';clearInterval(resendTimer)}};
  tick();resendTimer=setInterval(tick,1000);
}
async function resendOtp(){
  try{const info=await api('/api/auth/resend-otp',{method:'POST',body:JSON.stringify(state.pendingReg)});toast('A new code was sent');showOtpStep(info)}catch(e){toast(e.message,'error')}
}
async function submitOtp(event){
  event.preventDefault();const b=$('otpSubmit');b.disabled=true;b.textContent='Checking…';
  try{const data=await api('/api/auth/verify-otp',{method:'POST',body:JSON.stringify({...state.pendingReg,otp:$('otpInput').value.trim()})});
    clearInterval(resendTimer);state.pendingReg=null;setSession(data);closeModal();toast('Welcome to Baagh! Member ID: '+data.user.member_code);openDashboard('overview');loadSummary()}
  catch(e){toast(e.message,'error');b.disabled=false;b.innerHTML='Verify &amp; create account <span>↗</span>'}
}

/* ---------- Seller listing form driven by the catalog ---------- */
function listingFormHTML(){
  const ref=REFSYNC;
  return `<section class="panel"><div class="panel-head"><div><h2>Post a produce listing</h2><p>Pick the produce, form and grade. HSN code and GST rate are filled in automatically.</p></div><span class="pill">SELLER TOOL</span></div><form id="listingForm" class="listing-form" onsubmit="submitListing(event)">
  <div class="form-group"><label>Produce</label><select class="form-control" id="listingCrop" onchange="onListingCropChange()">${ref.catalog.crops.map(c=>`<option value="${esc(c.crop)}">${c.emoji} ${esc(c.crop)}</option>`).join('')}</select></div>
  <div class="form-group"><label>Form</label><select class="form-control" id="listingForm2" onchange="updateListingTax()"></select></div>
  <div class="form-group"><label>Variety</label><select class="form-control" id="listingVarietySel" onchange="onVarietyChange()"></select></div>
  <div class="form-group" id="otherVarietyBox" style="display:none"><label>Variety name</label><input class="form-control" id="listingVarietyOther" maxlength="100" placeholder="Type the variety"></div>
  <div class="form-group"><label>Grade</label><select class="form-control" id="listingGrade"></select></div>
  <div class="form-group"><label>Grown in (J&amp;K district)</label><select class="form-control" id="listingDistrict"></select><div class="form-help" id="growHint"></div></div>
  <div class="form-group"><label>Available quantity (kg)</label><input class="form-control" id="listingQty" type="number" min="0.001" step="any" required placeholder="1000"></div>
  <div class="form-group"><label>Asking price (₹ / kg)</label><input class="form-control" id="listingPrice" type="number" min="0.01" step="any" required placeholder="95"></div>
  <div class="form-group full"><div class="alert" id="taxBox" style="margin:0"></div></div>
  <div class="form-group full"><label>Description (optional)</label><textarea class="form-control" id="listingDescription" rows="2" maxlength="1200" placeholder="Tell buyers about the produce, packing or harvest…"></textarea></div>
  <div class="full"><button class="btn btn-primary" type="submit">Publish listing ↗</button></div></form></section>`;
}
function wireListingForm(){if($('listingCrop'))onListingCropChange()}
function onListingCropChange(){
  const ref=REFSYNC,c=cropInfo(ref,$('listingCrop').value);
  fillSelect($('listingForm2'),c.forms.map(f=>f.form));
  fillSelect($('listingVarietySel'),c.varieties);
  fillSelect($('listingGrade'),c.grades.map(g=>({value:g.grade,label:`${g.label} (${g.grade})`})));
  const prod=ref.kashmir.districts.filter(d=>d.crops[c.crop]);
  const major=prod.filter(d=>d.crops[c.crop]==='major').map(d=>d.district),grown=prod.filter(d=>d.crops[c.crop]==='grown').map(d=>d.district);
  const rest=ref.jkDistricts.filter(d=>!major.includes(d)&&!grown.includes(d));
  const mine=state.user.district;
  $('listingDistrict').innerHTML=`<optgroup label="★ Major producing districts">${major.map(d=>`<option ${d===mine?'selected':''}>${esc(d)}</option>`).join('')}</optgroup><optgroup label="Also grown">${grown.map(d=>`<option ${d===mine?'selected':''}>${esc(d)}</option>`).join('')}</optgroup><optgroup label="Other J&K / Ladakh districts">${rest.map(d=>`<option ${d===mine?'selected':''}>${esc(d)}</option>`).join('')}</optgroup>`;
  $('growHint').textContent=`${c.crop} grows mainly in: ${major.join(', ')||'—'}.`;
  onVarietyChange();updateListingTax();
}
function onVarietyChange(){$('otherVarietyBox').style.display=$('listingVarietySel').value==='Other'?'block':'none'}
function updateListingTax(){
  const c=cropInfo(REFSYNC,$('listingCrop').value),f=c.forms.find(x=>x.form===$('listingForm2').value)||c.forms[0];
  $('taxBox').innerHTML=`<strong>HSN ${esc(f.hsn)}</strong> · ${esc(f.description)} · <strong>${gstLabel(f.gst_rate)}</strong>. ${Number(f.gst_rate)===0?'Fresh fruit is nil rated under GST.':'GST is charged only if the seller has a GSTIN on the profile.'}`;
}
async function submitListing(event){
  event.preventDefault();
  const sel=$('listingVarietySel').value,variety=sel==='Other'?$('listingVarietyOther').value.trim():sel;
  if(variety.length<2){toast('Enter the variety name.','error');return}
  try{await api('/api/listings',{method:'POST',body:JSON.stringify({crop:$('listingCrop').value,product_form:$('listingForm2').value,variety,grade:$('listingGrade').value,district:$('listingDistrict').value,quantity_kg:Number($('listingQty').value),price_per_kg:Number($('listingPrice').value),description:$('listingDescription').value.trim()})});
    toast('Your listing is live');renderDashboard('listings');loadSummary();loadMarketplace()}catch(e){toast(e.message,'error')}
}
async function ratesAdminHTML(){
  const rows=await api('/api/rates');
  return `${panel('Add or update a rate',`<form id="rateForm" class="listing-form" onsubmit="saveRate(event)"><div class="form-group"><label>Crop</label><select class="form-control" id="rateCrop">${REFSYNC.catalog.crops.map(c=>`<option>${esc(c.crop)}</option>`).join('')}</select></div><div class="form-group"><label>Mandi / market</label><input class="form-control" id="rateMandi" required maxlength="100" placeholder="e.g. Sopore"></div><div class="form-group"><label>Price (₹ / kg)</label><input class="form-control" type="number" id="ratePrice" min="0.01" step="any" required placeholder="92"></div><div class="form-group" style="align-self:end"><button class="btn btn-primary" type="submit">Save rate ↗</button></div></form><p class="form-help">Only update this board with properly sourced market information. Current seed values are demonstration data.</p>`)}${panel('Current market rate board',table(['Crop','Mandi','₹ / kg','Last updated'],rows.map(r=>`<tr><td><strong>${esc(r.crop)}</strong></td><td>${esc(r.mandi)}</td><td>${money(r.price_per_kg)}</td><td>${esc(String(r.updated_at||'').replace('T',' ').slice(0,16))}</td></tr>`)))}`;
}

/* ---------- Admin: members (automatic phone verification, suspend / reinstate) ---------- */
async function usersHTML(){
  const d=await api('/api/admin/overview');
  const rows=d.users.filter(u=>u.role!=='admin').map(u=>{
    const action=u.role==='inspector'?'—':(u.verified?actionButton('Suspend',`setMemberStatus(${u.id},false)`,'danger'):actionButton('Reinstate',`setMemberStatus(${u.id},true)`));
    return `<tr><td><strong>${esc(u.name)}</strong><br><span class="small">${esc(u.member_code||'')}</span></td><td>${esc(u.phone)}</td><td>${esc(u.role)}</td><td>${esc([u.district,u.state,u.pincode].filter(Boolean).join(', '))}${u.country&&u.country!=='IN'?' · '+esc(u.country):''}</td><td>${u.gstin?esc(u.gstin):'<span class="small">None</span>'}</td><td>${u.verified?'<span class="status">Phone verified</span>':'<span class="status pending">Suspended</span>'}</td><td>${esc(String(u.created_at||'').slice(0,10))}</td><td>${action}</td></tr>`});
  return panel('Members',`<p class="form-help">New buyers and sellers are verified automatically by an SMS code sent to their phone. You can suspend a member who breaks the rules and reinstate them later.</p>`+table(['Member / ID','Phone','Role','Location','GSTIN','Status','Joined','Action'],rows));
}
async function setMemberStatus(id,verified){
  if(!verified&&!confirm('Suspend this member? They will not be able to list, offer or book.'))return;
  try{await api(`/api/admin/users/${id}/verify?verified=${verified}`,{method:'POST'});toast(verified?'Member reinstated':'Member suspended');renderDashboard('users');loadSummary()}catch(e){toast(e.message,'error')}
}

/* ---------- Seller / admin: buyer directory across India ---------- */
async function buyersHTML(){
  const ref=REFSYNC;
  return panel('Buyers across India',`<p class="form-help">Verified buyers by location. To trade, share your listing and let interested buyers send an offer; contact details are not shown here.</p><div class="market-toolbar"><select id="buyerState" onchange="onBuyerState()"><option>All</option>${ref.states.map(s=>`<option>${esc(s.name)}</option>`).join('')}</select><select id="buyerDistrict" onchange="loadBuyers()"><option>All</option></select><input class="field" id="buyerPin" inputmode="numeric" maxlength="6" placeholder="Pincode" style="max-width:130px" oninput="this.value=this.value.replace(/[^0-9]/g,'');if(this.value.length===6||!this.value)loadBuyers()"><input class="field" id="buyerSearch" type="search" placeholder="Search buyer name" style="max-width:220px" oninput="clearTimeout(state.searchTimer);state.searchTimer=setTimeout(loadBuyers,250)"></div><div id="buyerTable"><div class="loading"><div class="spinner"></div>Loading buyers…</div></div>`);
}
async function onBuyerState(){
  const st=$('buyerState').value;
  if(st==='All'){$('buyerDistrict').innerHTML='<option>All</option>'}
  else{try{const ds=await api('/api/geo/districts?state='+encodeURIComponent(st));$('buyerDistrict').innerHTML='<option>All</option>'+ds.map(d=>`<option>${esc(d)}</option>`).join('')}catch(e){}}
  loadBuyers();
}
async function loadBuyers(){
  const q=new URLSearchParams({state:$('buyerState').value,district:$('buyerDistrict').value,pincode:$('buyerPin').value,search:$('buyerSearch').value.trim()});
  try{const rows=await api('/api/buyers?'+q);$('buyerTable').innerHTML=table(['Buyer','Member ID','State','District','Pincode','GST','Since'],rows.map(b=>`<tr><td><strong>${esc(b.name)}</strong></td><td>${esc(b.member_code)}</td><td>${esc(b.country!=='IN'?'Outside India ('+b.country+')':b.state)}</td><td>${esc(b.district)}</td><td>${esc(b.pincode)}</td><td>${b.gst_registered?'<span class="status">GST registered</span>':'<span class="small">Not registered</span>'}</td><td>${esc(b.member_since)}</td></tr>`))}
  catch(e){$('buyerTable').innerHTML=`<div class="small">${esc(e.message)}</div>`}
}

/* ---------- GST + Tally report (Excel) ---------- */
async function gstPanelHTML(fy='current'){
  const g=await api('/api/my/gst-summary?fy='+encodeURIComponent(fy));const s=g.summary;
  const years=g.financial_years.map(y=>`<option value="${y}" ${y===g.fy?'selected':''}>FY ${y}</option>`).join('')+`<option value="All" ${g.fy==='All'?'selected':''}>All years</option>`;
  const seller=state.user.role==='seller';
  const gstinNote=seller&&!g.gstin?`<div class="alert"><strong>No GSTIN on your profile.</strong> Without a GSTIN no GST can be charged, so your sales show tax of ₹0. GST-registered sellers charge CGST+SGST within the same state and IGST to other states.</div>`:'';
  const cards=metric(seller?'Taxable sales':'Taxable purchases',money(s.taxable),'₹','Before GST')+metric('CGST + SGST / UTGST',money(s.cgst+s.sgst),'🏛','Same-state supplies')+metric('IGST',money(s.igst),'🚚','Other-state supplies')+metric('Invoice value',money(s.invoice_value),'🧾',`${num(s.invoices)} invoices`);
  const rows=g.invoices.map(i=>`<tr><td><strong>${esc(i.invoice_no)}</strong><br><span class="small">${esc(i.date)}</span></td><td>${esc(i.party)}</td><td>${esc(i.item)}<br><span class="small">HSN ${esc(i.hsn)}</span></td><td>${money(i.taxable)}</td><td>${Number(i.gst_rate)}%</td><td>${money(i.cgst)}</td><td>${money(i.sgst)}</td><td>${money(i.igst)}</td><td><strong>${money(i.invoice_value)}</strong></td><td>${esc(i.supply_type)}</td><td>${esc(i.basis)}</td></tr>`);
  return `<div id="gstArea"><div class="panel"><div class="panel-head"><div><h2>GST &amp; Tally report</h2><p>Excel workbook with a Tally voucher register, ledger entries, GSTR-1 style sheets and HSN summary.</p></div><div class="record-actions"><select class="form-control" style="width:auto;min-height:38px" onchange="reloadGst(this.value)">${years}</select><button class="btn btn-primary btn-sm" onclick="downloadGstReport('${esc(g.fy)}')">Download Excel (.xlsx) ↓</button></div></div>${gstinNote}<div class="dashboard-grid" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">${cards}</div>${s.provisional?`<p class="form-help">${s.provisional} invoice(s) are provisional: the order is accepted but not yet dispatched.</p>`:''}<p class="form-help">${esc(g.note)}</p>${table(['Invoice','Party','Item','Taxable','GST %','CGST','SGST','IGST','Invoice value','Supply','Basis'],rows)}</div></div>`;
}
async function reloadGst(fy){try{$('gstArea').outerHTML=await gstPanelHTML(fy)}catch(e){toast(e.message,'error')}}
async function downloadGstReport(fy){
  try{const r=await fetch('/api/my/gst-report.xlsx?fy='+encodeURIComponent(fy),{headers:{Authorization:'Bearer '+state.token}});
    if(!r.ok){let err={};try{err=await r.json()}catch{}throw new Error(err.detail||'Could not create the report')}
    const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`baagh-tally-gst-${(state.user.member_code||'member').toLowerCase()}-${fy}.xlsx`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Excel report downloaded')}
  catch(e){toast(e.message,'error')}
}
async function auditHTML(){
  if(!['seller','buyer'].includes(state.user.role))return auditBaseHTML();
  return (await gstPanelHTML())+(await auditBaseHTML());
}

init();
async function init(){await loadInitial()}
