#!/usr/bin/env python3
"""vq_tuner.py — browser-based per-texture VQ tuning (operator art pass).

Serves http://localhost:8765 — pick a STAGE08 shrink target, tweak the
sharpening (luma-only, applied to the in-tool 2x2 box downscale of the
ORIGINAL 1024x1024 record: no third-party resampler, no new colors) and the
encoder knobs (edge_w / mask_w), press Encode, and compare the prepared
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


def sharpen(ref, amount, radius):
    """Luma-only unsharp (the v2 per-channel version made chroma noise):
    the luma detail delta is added equally to R, G and B."""
    if amount <= 0:
        return ref
    luma = (ref[..., :3] @ np.float32([0.299, 0.587, 0.114]))[..., None]
    blur = luma
    for _ in range(max(1, int(radius))):
        blur = shr.box3(blur)
    out = ref.copy()
    out[..., :3] = np.clip(ref[..., :3] + amount * (luma - blur), 0.0, 255.0)
    return out


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
    ref = np.rint(sharpen(source(off), float(p["sharpen"]), int(p["radius"])))
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
    rec, out_rgba, psnr = shr.finish(ref, PIXFMT[off], rng, blk_w, float(p["edge_w"]))
    out = np.frombuffer(out_rgba, np.uint8).reshape(512, 512, 4).astype(np.float32)
    return rec, ref, out, psnr, int((time.time() - t0) * 1000), mask.exists()


def api_encode(p):
    rec, ref, out, psnr, ms, has_mask = run_encode(p)
    return {"ref": data_uri(ref), "out": data_uri(out), "psnr": float(psnr),
            "ms": ms, "mask": has_mask, "full": bool(p.get("full"))}


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
    (shr.EDIT_DIR / ("%08x-params.json" % off)).write_text(json.dumps(
        {"sharpen": float(p["sharpen"]), "radius": int(p["radius"]),
         "edge_w": float(p["edge_w"]), "mask_w": float(p["mask_w"])}, indent=1))
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
</style>
<div id=bar>
 <select id=tex></select>
 <label>sharpen <input id=sharpen type=range min=0 max=3 step=0.05 value=0><span id=sharpenv>0</span></label>
 <label>radius <input id=radius type=range min=1 max=3 step=1 value=1><span id=radiusv>1</span></label>
 <label>edge_w <input id=edge_w type=range min=0 max=4 step=0.1 value=0><span id=edge_wv>0</span></label>
 <label>mask_w <input id=mask_w type=range min=0 max=8 step=0.5 value=4><span id=mask_wv>4</span></label>
 <label><input id=full type=checkbox>full quality</label>
 <button id=enc>Encode</button>
 <button id=save>Save</button>
 <label>zoom <select id=zoom><option>1</option><option selected>2</option><option>4</option></select></label>
 <span id=status></span>
</div>
<div class=wrap>
 <div class=col><div class=cap>prepared source (downscale + sharpen) — this is what Save writes</div>
  <div class=pane id=p1><img id=ref></div></div>
 <div class=col><div class=cap>VQ round trip — this is what ships</div>
  <div class=pane id=p2><img id=out></div></div>
</div>
<script>
const TEX = __TEXTURES__;
const $ = id => document.getElementById(id);
TEX.forEach(t => $('tex').add(new Option(t.label, t.off)));
['sharpen','radius','edge_w','mask_w'].forEach(k => {
  $(k).oninput = () => $(k+'v').textContent = $(k).value;
});
function params(){ return {off:$('tex').value, sharpen:+$('sharpen').value,
  radius:+$('radius').value, edge_w:+$('edge_w').value, mask_w:+$('mask_w').value,
  full:$('full').checked}; }
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
    + ' ms · mask ' + (j.mask ? 'found' : 'none') + ' · '
    + (j.full ? 'full (30 iters)' : 'fast (10 iters)');
}
$('enc').onclick = encode;
$('tex').onchange = encode;
$('save').onclick = async () => {
  if(!confirm('Overwrite edit/' + $('tex').value
      + '.png (existing backed up to -prev) + params.json?')) return;
  const j = await call('/api/save'); if(!j) return;
  $('status').textContent = j.msg;
};
$('zoom').onchange = () => {
  const z = 512 * +$('zoom').value + 'px';
  $('ref').style.width = z; $('out').style.width = z;
};
$('zoom').onchange();
let lock = false;
[['p1','p2'],['p2','p1']].forEach(([a,b]) => $(a).onscroll = () => {
  if(lock) return; lock = true;
  $(b).scrollLeft = $(a).scrollLeft; $(b).scrollTop = $(a).scrollTop;
  lock = false;
});
encode();
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
