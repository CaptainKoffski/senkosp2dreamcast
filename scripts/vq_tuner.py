#!/usr/bin/env python3
"""vq_tuner.py — browser-based per-texture VQ tuning (operator art pass).

Serves http://localhost:8765 — pick a STAGE08 shrink target, tweak the
sharpening (luma-only, applied to the in-tool 2x2 box downscale of the
ORIGINAL 1024x1024 record: no third-party resampler, no new colors) and the
encoder knobs (edge_w / mask_w), drag rectangles on the left panel for
region-scoped EXTRA sharpening (per-region amount, ~3 px feather so region
borders don't seam), press Encode, and compare the prepared
source against the true VQ round trip (the build encoder + the
control-tested decoder). Per-texture rng seeds make the preview
byte-identical to what shrink_vq.py ships.

Save writes captures/phase5/textures/edit/<off>.png (sharpening baked in;
an existing edit is backed up to <off>-prev.png) plus <off>-params.json,
which shrink_vq.py reads at build time — so the saved state IS the build.

Stdlib + numpy (tools/pyenv — docs/kb/tooling.md):
  tools/pyenv/bin/python scripts/vq_tuner.py [senkosp.dat] [port]
"""
import base64, importlib.util, json, pathlib, struct, sys, threading, time, zlib
import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


dec = _load("dec", REPO / "scripts/decode_pvr_vq.py")
shr = _load("shr", REPO / "scripts/shrink_vq.py")

# shrink targets + the full-size 0b777810 (experiment only: its edit files
# are ignored by the build since the 2026-08-25 shrink-3 amendment)
TEXTURES = list(shr.TARGETS) + [(0x0b777810, 0x02)]
PIXFMT = dict(TEXTURES)
DAT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "senkosp.dat"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
shr.PSNR_FLOOR = 0.0        # tool displays PSNR; Save + build keep the 26 dB gate
LOCK = threading.Lock()     # numpy encode is heavy: one at a time
SOURCES = {}                # off -> 512x512 float RGBA box downscale


def source(off):
    if off not in SOURCES:
        with open(DAT, "rb") as f:
            w, h, pf, rgba = dec.decode(f, off)
        assert (w, h, pf) == (1024, 1024, PIXFMT[off]), (w, h, pf)
        img = np.frombuffer(rgba, np.uint8).reshape(1024, 1024, 4).astype(np.float32)
        SOURCES[off] = img.reshape(512, 2, 512, 2, 4).mean((1, 3))
    return SOURCES[off]


def sharpen(ref, amt, radius):
    """Luma-only unsharp (the v2 per-channel version made chroma noise):
    the luma detail delta is added equally to R, G and B. amt is a
    (512, 512) per-pixel amount map (global slider + feathered regions)."""
    if amt.max() <= 0:
        return ref
    luma = (ref[..., :3] @ np.float32([0.299, 0.587, 0.114]))[..., None]
    blur = luma
    for _ in range(max(1, int(radius))):
        blur = shr.box3(blur)
    out = ref.copy()
    out[..., :3] = np.clip(ref[..., :3] + amt[..., None] * (luma - blur), 0.0, 255.0)
    return out


def amount_map(p):
    """Global sharpen everywhere + per-region extra (max on overlap),
    feathered ~3 px so the sharpened/unsharpened border can't seam."""
    amt = np.full((shr.DST, shr.DST), float(p["sharpen"]), np.float32)
    extra = np.zeros((shr.DST, shr.DST), np.float32)
    for r in p.get("regions") or []:
        x0, y0 = max(0, int(r["x0"])), max(0, int(r["y0"]))
        x1, y1 = min(shr.DST, int(r["x1"])), min(shr.DST, int(r["y1"]))
        if x1 > x0 and y1 > y0:
            extra[y0:y1, x0:x1] = np.maximum(extra[y0:y1, x0:x1], float(r["extra"]))
    if extra.any():
        e = extra[..., None]
        for _ in range(3):
            e = shr.box3(e)
        amt += e[..., 0]
    return amt


def color_adjust(ref, p):
    """Per-channel gain, optionally scoped to bright pixels (luma >= gain_lo
    with a 40-step linear knee) — the anti-green-cast knob."""
    g = np.float32([float(p.get("gain_r", 1)), float(p.get("gain_g", 1)),
                    float(p.get("gain_b", 1))])
    if (g == 1).all():
        return ref
    rgb = ref[..., :3]
    lo = float(p.get("gain_lo", 0))
    if lo > 0:
        luma = rgb @ np.float32([0.299, 0.587, 0.114])
        w = np.clip((luma - lo + 20.0) / 40.0, 0.0, 1.0)[..., None]
    else:
        w = 1.0
    out = ref.copy()
    out[..., :3] = np.clip(rgb * (1.0 + w * (g - 1.0)), 0.0, 255.0)
    return out


def bright_cast(img):
    """Mean G - (R+B)/2 over bright pixels (luma > 180): the green-cast needle."""
    rgb = img[..., :3]
    sel = (rgb @ np.float32([0.299, 0.587, 0.114])) > 180
    if not sel.any():
        return 0.0
    return float((rgb[..., 1] - (rgb[..., 0] + rgb[..., 2]) / 2)[sel].mean())


def png_bytes(img):
    """float RGBA (h, w, 4) -> PNG bytes (8-bit RGBA, filter 0)."""
    raw = img.astype(np.uint8)
    h, w = raw.shape[:2]
    rows = b"".join(b"\x00" + raw[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6))
            + chunk(b"IEND", b""))


def data_uri(img):
    return "data:image/png;base64," + base64.b64encode(png_bytes(img)).decode()


def run_encode(p):
    """One tool encode, mirroring shrink_vq.encode_one's edit path exactly.
    ref is rounded to whole uint8 values so the preview equals what a saved
    edit PNG reproduces at build time, byte for byte."""
    off = int(p["off"], 16)
    ref = color_adjust(source(off), p)
    ref = np.rint(sharpen(ref, amount_map(p), int(p["radius"])))
    mask = shr.EDIT_DIR / ("%08x-mask.png" % off)
    blk_w = None
    if mask.exists() and float(p["mask_w"]) > 0:
        mw, mh, mimg = shr.load_png_rgba(mask)
        m = mimg[..., :3].mean(-1) / 255.0
        blk_w = 1.0 + float(p["mask_w"]) \
            * m.reshape(shr.DST // 2, 2, shr.DST // 2, 2).mean((1, 3)).ravel()
    shr.KMEANS_ITERS = 30 if p.get("full") else 10
    rng = np.random.default_rng(0x53454e4b ^ off)   # matches shrink_vq main()
    t0 = time.time()
    # ARGB1555 override: equal 5/5/5 steps keep neutral grays neutral (565's
    # finer green step tints bright grays); loader precedent = STAGE10's VQ-1555
    out_pf = 0x00 if p.get("pf1555") else PIXFMT[off]
    rec, out_rgba, psnr = shr.finish(ref, out_pf, rng, blk_w, float(p["edge_w"]))
    out = np.frombuffer(out_rgba, np.uint8).reshape(512, 512, 4).astype(np.float32)
    return rec, ref, out, psnr, int((time.time() - t0) * 1000), mask.exists()


def api_encode(p):
    rec, ref, out, psnr, ms, has_mask = run_encode(p)
    return {"ref": data_uri(ref), "out": data_uri(out), "psnr": float(psnr),
            "ms": ms, "mask": has_mask, "full": bool(p.get("full")),
            "pf": "1555" if p.get("pf1555") else "native",
            "cast_ref": round(bright_cast(ref), 2), "cast_out": round(bright_cast(out), 2)}


def api_save(p):
    p = dict(p, full=True)                       # never save a fast preview
    rec, ref, out, psnr, ms, has_mask = run_encode(p)
    if psnr < 26.0:
        return {"error": "PSNR %.1f dB is under the 26 dB build gate — not saved" % psnr}
    off = int(p["off"], 16)
    edit = shr.EDIT_DIR / ("%08x.png" % off)
    if edit.exists():
        (shr.EDIT_DIR / ("%08x-prev.png" % off)).write_bytes(edit.read_bytes())
    edit.write_bytes(png_bytes(ref))
    d = {"sharpen": float(p["sharpen"]), "radius": int(p["radius"]),
         "edge_w": float(p["edge_w"]), "mask_w": float(p["mask_w"]),
         "gain_r": float(p.get("gain_r", 1)), "gain_g": float(p.get("gain_g", 1)),
         "gain_b": float(p.get("gain_b", 1)), "gain_lo": float(p.get("gain_lo", 0)),
         "regions": p.get("regions") or []}
    if p.get("pf1555"):
        d["out_pf"] = 0x00
    (shr.EDIT_DIR / ("%08x-params.json" % off)).write_text(json.dumps(d, indent=1))
    return {"msg": "saved %08x.png + %08x-params.json (PSNR %.1f dB)%s"
                   % (off, off, psnr,
                      "" if PIXFMT[off] != 0x02 else " — NOTE: 0b777810 ships full-size; build ignores this")}


PAGE = """<!doctype html><meta charset="utf-8"><title>vq tuner</title>
<style>
body{font:13px system-ui;margin:0;background:#222;color:#ddd}
#bar{padding:8px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;background:#333;position:sticky;top:0;z-index:1}
label{display:flex;gap:4px;align-items:center;white-space:nowrap}
.col{width:50%}.pane{height:calc(100vh - 76px);overflow:auto}
img{image-rendering:pixelated;display:block}
.wrap{display:flex}.cap{padding:3px 8px;color:#8bc;font-size:12px}
button{padding:4px 12px}#status{color:#cd8}
img{user-select:none;-webkit-user-drag:none}
.rgn{position:absolute;border:1px solid #fc4;background:rgba(255,200,60,.12);
     color:#fc4;font-size:10px;cursor:pointer;overflow:hidden}
.rgn.sel{border-color:#4cf;color:#4cf;background:rgba(80,200,255,.15)}
</style>
<div id=bar>
 <select id=tex></select>
 <label>sharpen <input id=sharpen type=range min=0 max=3 step=0.05 value=0><span id=sharpenv>0</span></label>
 <label>radius <input id=radius type=range min=1 max=3 step=1 value=1><span id=radiusv>1</span></label>
 <label>edge_w <input id=edge_w type=range min=0 max=4 step=0.1 value=0><span id=edge_wv>0</span></label>
 <label>mask_w <input id=mask_w type=range min=0 max=8 step=0.5 value=4><span id=mask_wv>4</span></label>
 <label>R× <input id=gain_r type=range min=0.85 max=1.15 step=0.005 value=1><span id=gain_rv>1</span></label>
 <label>G× <input id=gain_g type=range min=0.85 max=1.15 step=0.005 value=1><span id=gain_gv>1</span></label>
 <label>B× <input id=gain_b type=range min=0.85 max=1.15 step=0.005 value=1><span id=gain_bv>1</span></label>
 <label>luma≥ <input id=gain_lo type=range min=0 max=220 step=10 value=0><span id=gain_lov>0</span></label>
 <label>region + <input id=rsharp type=range min=0 max=4 step=0.05 value=1><span id=rsharpv>1</span></label>
 <button id=delr>Del region</button>
 <button id=clearr>Clear</button>
 <label><input id=pf1555 type=checkbox>ARGB1555</label>
 <label><input id=full type=checkbox>full quality</label>
 <button id=enc>Encode</button>
 <button id=save>Save</button>
 <label>zoom <select id=zoom><option>1</option><option selected>2</option><option>4</option></select></label>
 <span id=status></span>
</div>
<div class=wrap>
 <div class=col><div class=cap>prepared source — drag a rectangle for region-extra sharpen; this is what Save writes</div>
  <div class=pane id=p1><div id=refwrap style="position:relative"><img id=ref></div></div></div>
 <div class=col><div class=cap>VQ round trip — this is what ships</div>
  <div class=pane id=p2><img id=out></div></div>
</div>
<script>
const TEX = __TEXTURES__;
const $ = id => document.getElementById(id);
TEX.forEach(t => $('tex').add(new Option(t.label, t.off)));
['sharpen','radius','edge_w','mask_w','gain_r','gain_g','gain_b','gain_lo'].forEach(k => {
  $(k).oninput = () => $(k+'v').textContent = $(k).value;
});
function params(){ return {off:$('tex').value, sharpen:+$('sharpen').value,
  radius:+$('radius').value, edge_w:+$('edge_w').value, mask_w:+$('mask_w').value,
  gain_r:+$('gain_r').value, gain_g:+$('gain_g').value, gain_b:+$('gain_b').value,
  gain_lo:+$('gain_lo').value,
  regions:regions, pf1555:$('pf1555').checked, full:$('full').checked}; }
async function call(url){
  $('status').textContent = 'encoding…';
  $('enc').disabled = $('save').disabled = true;
  try{
    const r = await fetch(url, {method:'POST', body:JSON.stringify(params())});
    const j = await r.json();
    if(j.error){ $('status').textContent = '⚠ ' + j.error; return null; }
    return j;
  } catch(e){ $('status').textContent = '⚠ ' + e; return null; }
  finally { $('enc').disabled = $('save').disabled = false; }
}
async function encode(){
  const j = await call('/api/encode'); if(!j) return;
  $('ref').src = j.ref; $('out').src = j.out;
  $('status').textContent = 'PSNR ' + j.psnr.toFixed(1) + ' dB · ' + j.ms
    + ' ms · ' + j.pf + ' · cast ' + j.cast_ref.toFixed(1) + '→' + j.cast_out.toFixed(1)
    + ' · mask ' + (j.mask ? 'found' : 'none') + ' · '
    + (j.full ? 'full (30 iters)' : 'fast (10 iters)');
}
$('enc').onclick = encode;

// ---- region-scoped extra sharpening ----------------------------------
let regions = [], sel = -1, drag = null;
function pxToTex(e){
  const r = $('ref').getBoundingClientRect(), z = +$('zoom').value;
  return [Math.max(0, Math.min(511, Math.round((e.clientX - r.left)/z))),
          Math.max(0, Math.min(511, Math.round((e.clientY - r.top)/z)))];
}
function norm(d){ return {x0:Math.min(d.x0,d.x1), y0:Math.min(d.y0,d.y1),
                          x1:Math.max(d.x0,d.x1), y1:Math.max(d.y0,d.y1)}; }
function render(){
  document.querySelectorAll('.rgn').forEach(el => el.remove());
  const z = +$('zoom').value;
  const list = drag ? regions.concat([{...norm(drag), extra:+$('rsharp').value}]) : regions;
  list.forEach((r, i) => {
    const d = document.createElement('div');
    d.className = 'rgn' + (i === sel ? ' sel' : '');
    d.style.cssText = 'left:' + r.x0*z + 'px;top:' + r.y0*z + 'px;width:'
      + (r.x1-r.x0)*z + 'px;height:' + (r.y1-r.y0)*z + 'px';
    d.textContent = '+' + r.extra;
    d.onmousedown = e => { e.stopPropagation(); e.preventDefault();
      sel = i; $('rsharp').value = r.extra; $('rsharpv').textContent = r.extra; render(); };
    $('refwrap').appendChild(d);
  });
}
$('ref').onmousedown = e => { e.preventDefault(); const [x,y] = pxToTex(e);
  drag = {x0:x, y0:y, x1:x, y1:y}; };
window.onmousemove = e => { if(!drag) return;
  const [x,y] = pxToTex(e); drag.x1 = x; drag.y1 = y; render(); };
window.onmouseup = () => {
  if(!drag) return;
  const r = norm(drag); drag = null;
  if(r.x1 - r.x0 >= 4 && r.y1 - r.y0 >= 4){
    regions.push({...r, extra:+$('rsharp').value}); sel = regions.length - 1;
  }
  render();
};
$('rsharp').oninput = () => { $('rsharpv').textContent = $('rsharp').value;
  if(sel >= 0){ regions[sel].extra = +$('rsharp').value; render(); } };
$('delr').onclick = () => { if(sel >= 0){ regions.splice(sel, 1); sel = -1; render(); } };
$('clearr').onclick = () => { regions = []; sel = -1; render(); };

async function loadState(){
  const j = await (await fetch('/api/state?off=' + $('tex').value)).json();
  regions = j.regions || []; sel = -1;
  for(const k of ['sharpen','radius','edge_w','mask_w','gain_r','gain_g','gain_b','gain_lo'])
    if(k in (j.params || {})){ $(k).value = j.params[k]; $(k+'v').textContent = j.params[k]; }
  $('pf1555').checked = !!j.pf1555;
  render();
}
$('tex').onchange = () => loadState().then(encode);
$('save').onclick = async () => {
  if(!confirm('Overwrite edit/' + $('tex').value
      + '.png (existing backed up to -prev) + params.json?')) return;
  const j = await call('/api/save'); if(!j) return;
  $('status').textContent = j.msg;
};
$('zoom').onchange = () => {
  const z = 512 * +$('zoom').value + 'px';
  $('ref').style.width = z; $('out').style.width = z;
  render();
};
$('zoom').onchange();
let lock = false;
[['p1','p2'],['p2','p1']].forEach(([a,b]) => $(a).onscroll = () => {
  if(lock) return; lock = true;
  $(b).scrollLeft = $(a).scrollLeft; $(b).scrollTop = $(a).scrollTop;
  lock = false;
});
loadState().then(encode);
</script>"""


def page():
    tex = [{"off": "%08x" % off,
            "label": "%08x — %s" % (off, {0x00: "ARGB1555", 0x01: "RGB565"}.get(pf)
                                    or "ARGB4444 (ships full-size — experiment only)")}
           for off, pf in TEXTURES]
    return PAGE.replace("__TEXTURES__", json.dumps(tex))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(page().encode(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/state?off="):
            off = self.path.rsplit("=", 1)[1]
            f = shr.EDIT_DIR / ("%s-params.json" % off)
            p = json.loads(f.read_text()) if f.exists() else {}
            self._send(json.dumps({
                "params": {k: p[k] for k in ("sharpen", "radius", "edge_w", "mask_w",
                                             "gain_r", "gain_g", "gain_b", "gain_lo") if k in p},
                "regions": p.get("regions", []),
                "pf1555": p.get("out_pf") == 0x00}).encode(), "application/json")
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            p = json.loads(self.rfile.read(n) or b"{}")
            with LOCK:
                if self.path == "/api/encode":
                    out = api_encode(p)
                elif self.path == "/api/save":
                    out = api_save(p)
                else:
                    self.send_error(404)
                    return
            self._send(json.dumps(out).encode(), "application/json")
        except Exception as e:
            self._send(json.dumps({"error": "%s: %s" % (type(e).__name__, e)}).encode(),
                       "application/json", 500)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("vq_tuner: http://localhost:%d  (dat=%s, Ctrl-C to stop)" % (PORT, DAT))
    srv.serve_forever()
