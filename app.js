/* Tien ich dung chung cho cac trang quan tri. */
const S = s => document.querySelector(s);
const TOKEN = () => localStorage.getItem('kis-token') || '';
const USER  = () => localStorage.getItem('kis-user') || '';

async function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({}, opts.headers,
    {'X-KIS-Auth': TOKEN(), 'X-KIS-User': USER()});
  const r = await fetch(path, opts);
  if(r.status === 401 || r.status === 403){
    const j = await r.json().catch(() => ({}));
    if(r.status === 401){ location.href = 'login.html'; }
    throw new Error(j.error || 'không đủ quyền');
  }
  return r;
}

async function jget(path){ return (await api(path)).json(); }
async function jpost(path, body){
  return (await api(path, {method:'POST', headers:{'Content-Type':'application/json'},
                           body: JSON.stringify(body)})).json();
}

function say(sel, text, kind){
  const el = S(sel); if(!el) return;
  el.textContent = text; el.className = 'msg' + (kind ? ' ' + kind : '');
}

/* Gan thanh dieu huong + kiem tra quyen. adminOnly=true thi day ve hub neu khong phai admin. */
async function guard(adminOnly){
  if(!TOKEN() || !USER()){
    location.href = 'login.html';
    return null;
  }
  let me;
  try{ me = await jget('/api/me'); }
  catch(e){ return null; }
  if(adminOnly && me.role !== 'admin'){
    document.body.innerHTML =
      '<div class="wrap narrow"><div class="card"><h1>Không đủ quyền</h1>' +
      '<p class="sub">Trang này chỉ dành cho admin.</p>' +
      '<div class="row" style="margin-top:14px"><a class="btn" href="hub.html">← Về trang chính</a></div>' +
      '</div></div>';
    return null;
  }
  const nav = S('#nav');
  if(nav){
    nav.innerHTML =
      '<a href="hub.html">← Trang chính</a><span class="spacer"></span>' +
      '<span class="tag me">' + me.name + '</span>' +
      '<span class="tag' + (me.role === 'admin' ? ' admin' : '') + '">' + me.role + '</span>' +
      '<button class="btn" id="logout">Đăng xuất</button>';
    S('#logout').onclick = () => {
      localStorage.removeItem('kis-token'); localStorage.removeItem('kis-user');
      location.href = 'login.html';
    };
  }
  return me;
}
