"""Voice Lab: voices and speech with OmniVoice (ComfyUI-OmniVoice-TTS node pack).

Four ways, all built here as ComfyUI graphs (the server runs them):
  design - a voice made from a description (gender, age, pitch, accent);
  clone  - the voice of a sample file or of a saved voice reads any text (long text is cut into pieces by the node);
  dialog - a conversation: every line is read by its own voice (2-4 speakers, a sample per speaker).
Saved voices (a short sample + a name) live in data/voicelab/voices; the last results in data/voicelab/out.
"""
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from aiohttp import web

# the node pack is downloaded as a GitHub archive of a fixed commit (no git needed), like the packs in catalog.py
VOICE_PACK = {"name": "ComfyUI-omnivoice-tts", "repo": "Saganaki22/ComfyUI-OmniVoice-TTS",
              "commit": "3fe8e42a6d4a03628471aa1ba8506657e2e96dea"}
# voice conversion «Своя интонация» (Chatterbox VC): the recording is re-voiced, the words and the delivery stay
VC_PACK = {"name": "ComfyUI-Chatterbox", "repo": "wildminder/ComfyUI-Chatterbox", "commit": "7175b1e42d652e12482da57c1b44f74194649c4a"}
NODES = ("OmniVoiceVoiceDesignTTS", "OmniVoiceVoiceCloneTTS", "OmniVoiceLongformTTS", "OmniVoiceMultiSpeakerTTS")
AUD_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
MAX_UPLOAD = 60 * 1024 * 1024
MAX_SPEAKERS = 4
KEEP_TAKES = 60          # the newest not-starred takes kept on disk
SHORT_TEXT_WORDS = 45    # the clone node has no chunking: longer text goes to the long-text node

QUALITY = {"fast": 16, "normal": 32, "best": 64}

# what the design window offers (the words the node understands)
GENDERS = {"female": "Женский", "male": "Мужской"}
AGES = {"child": "Ребёнок", "teenager": "Подросток", "young adult": "Молодой", "middle-aged": "Средний возраст", "elderly": "Пожилой"}
PITCHES = {"very low pitch": "Очень низкий", "low pitch": "Низкий", "moderate pitch": "Средний", "high pitch": "Высокий", "very high pitch": "Очень высокий"}
ACCENTS = {"russian accent": "Русский", "american accent": "Американский", "british accent": "Британский", "australian accent": "Австралийский",
           "canadian accent": "Канадский", "indian accent": "Индийский", "chinese accent": "Китайский", "japanese accent": "Японский",
           "korean accent": "Корейский", "portuguese accent": "Португальский"}
VALID_WORDS = set(GENDERS) | set(AGES) | set(PITCHES) | set(ACCENTS) | {"whisper"}


def _err(text, status=400):
    return web.json_response({"error": text}, status=status)


def _num(v, lo, hi, default):
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def _pick(v, options, default):
    return v if v in options else default


def _flag(v, default):
    return default if v is None else bool(v)


def settings(p):
    """Every number of the node, cleaned to its allowed range (the names are the node's own inputs)."""
    steps = int(_num(p.get("steps"), 4, 64, QUALITY.get(str(p.get("quality")), 32)))
    seed = int(_num(p.get("seed"), 0, 2 ** 31 - 1, 0)) or int(uuid.uuid4().int % (2 ** 31 - 1)) + 1
    return {"steps": steps, "speed": round(_num(p.get("speed"), 0.5, 2.0, 1.0), 2), "guidance_scale": round(_num(p.get("guidance"), 0.0, 10.0, 2.0), 2),
            "t_shift": round(_num(p.get("t_shift"), 0.0, 1.0, 0.1), 2), "duration": round(_num(p.get("duration"), 0.0, 60.0, 0.0), 1), "seed": seed,
            "device": _pick(p.get("device"), ("auto", "cuda", "cpu", "mps", "xpu"), "auto"),
            "dtype": _pick(p.get("dtype"), ("auto", "bf16", "fp16", "fp32"), "auto"),
            "attention": _pick(p.get("attention"), ("auto", "eager", "sage_attention"), "auto"),
            "position_temperature": round(_num(p.get("position_temperature"), 0.0, 20.0, 5.0), 1),
            "class_temperature": round(_num(p.get("class_temperature"), 0.0, 5.0, 0.0), 2),
            "layer_penalty_factor": round(_num(p.get("layer_penalty_factor"), 0.0, 20.0, 5.0), 1),
            "denoise": _flag(p.get("denoise"), True), "postprocess_output": _flag(p.get("postprocess_output"), True),
            "keep_model_loaded": _flag(p.get("keep_model_loaded"), True)}


def hint(p):
    """The free text 'instruct' of the clone nodes (style, emotion): English, one line."""
    return re.sub(r"\s+", " ", str(p.get("instruct") or "")).strip()[:300]


def instruct(p):
    """The description of a designed voice: the chosen words in English, or the user's own English text."""
    own = re.sub(r"\s+", " ", str(p.get("custom") or "")).strip()[:300]
    if own:
        return own
    words = [str(p.get(k) or "") for k in ("gender", "age", "pitch", "accent")]
    words = [w for w in words if w in VALID_WORDS]
    if p.get("whisper"):
        words.append("whisper")
    return ", ".join(words) or "female, moderate pitch"


def _save(g, src, p=None, prefix="H3Workspace/voice/voice"):
    q = _pick((p or {}).get("mp3"), ("V0", "128k", "320k"), "V0")
    g["90"] = {"class_type": "SaveAudioMP3", "inputs": {"audio": [src, 0], "filename_prefix": prefix, "quality": q}}
    return g


def design_graph(model, text, p):
    g = {"1": {"class_type": "OmniVoiceVoiceDesignTTS", "inputs": {"model": model, "text": text, "voice_instruct": instruct(p), **settings(p)}}}
    return _save(g, "1", p)


def clone_graph(model, text, p, ref_name, ref_text=""):
    s = settings(p)
    g = {"2": {"class_type": "LoadAudio", "inputs": {"audio": ref_name}}}
    if len(text.split()) > SHORT_TEXT_WORDS:
        g["1"] = {"class_type": "OmniVoiceLongformTTS", "inputs": {
            "model": model, "text": text, "ref_text": ref_text, "ref_audio": ["2", 0], "words_per_chunk": int(_num(p.get("words_per_chunk"), 0, 500, 100)), "preprocess_prompt": _flag(p.get("preprocess_prompt"), True), "instruct": hint(p), **s}}
    else:
        g["1"] = {"class_type": "OmniVoiceVoiceCloneTTS", "inputs": {
            "model": model, "text": text, "ref_text": ref_text, "ref_audio": ["2", 0], "preprocess_prompt": _flag(p.get("preprocess_prompt"), True), "instruct": hint(p), **s}}
    return _save(g, "1", p)


def dialog_graph(model, text, p, speakers):
    """speakers: [(uploaded file name, what is said in the sample)] one per voice, in order: [Speaker_1] ... [Speaker_N]."""
    s = settings(p)
    inputs = {"model": model, "text": text, "num_speakers": str(len(speakers)), "pause_between_speakers": round(_num(p.get("pause"), 0.0, 3.0, 0.3), 1),
              "preprocess_prompt": _flag(p.get("preprocess_prompt"), True), **{k: v for k, v in s.items() if k != "duration"}}
    g = {}
    for i, (name, ref_text) in enumerate(speakers, 1):
        g[f"a{i}"] = {"class_type": "LoadAudio", "inputs": {"audio": name}}
        inputs[f"num_speakers.speaker_{i}_audio"] = [f"a{i}", 0]
        inputs[f"num_speakers.speaker_{i}_ref_text"] = ref_text
    g["1"] = {"class_type": "OmniVoiceMultiSpeakerTTS", "inputs": inputs}
    return _save(g, "1", p)


def _default(spec):
    try:
        t = spec[0]
        cfg = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        if "default" in cfg:
            return cfg["default"]
        opts = t if isinstance(t, list) else cfg.get("options") or []
        return opts[0] if opts else None
    except (TypeError, IndexError):
        return None


def convert_graph(info, src_name, ref_name, p):
    """ChatterboxVC: the recording `src_name` is re-voiced into the voice of `ref_name`; other required inputs get their own defaults."""
    req = ((info or {}).get("input") or {}).get("required") or {}
    packs = (req.get("model_pack_name") or [[]])[0]
    packs = packs if isinstance(packs, list) else ((req.get("model_pack_name") or [None, {}])[1] or {}).get("options") or []
    pack = "chatterbox" if "chatterbox" in packs else (_default(req.get("model_pack_name") or []) or (packs[0] if packs else "chatterbox"))
    inputs = {"model_pack_name": pack, "source_audio": ["2", 0], "target_voice_audio": ["3", 0],
              "n_timesteps": int(_num(p.get("steps"), 2, 50, 10)), "flow_cfg_scale": round(_num(p.get("cfg"), 0.0, 2.0, 1.0), 2),
              "refinement_passes": int(_num(p.get("passes"), 1, 5, 2)),
              "temperature": round(_num(p.get("temperature"), 0.0, 2.0, 1.0), 2), "use_watermark": False}
    for name, spec in req.items():
        if name not in inputs:
            v = _default(spec)
            if v is not None:
                inputs[name] = v
    g = {"2": {"class_type": "LoadAudio", "inputs": {"audio": src_name}}, "3": {"class_type": "LoadAudio", "inputs": {"audio": ref_name}},
         "1": {"class_type": "ChatterboxVC", "inputs": inputs}}
    return _save(g, "1", p)


def pick_model(options):
    """Which model name to use from the node's list: the small one already on disk, then the big one on disk, then the small one to download."""
    opts = [str(o) for o in options or []]
    for want in ("OmniVoice-bf16", "OmniVoice"):
        if want in opts:
            return want
    return next((o for o in opts if "bf16" in o), opts[0] if opts else "OmniVoice-bf16 (auto download)")


def dialog_text(text, n):
    """The node wants [Speaker_N]: before each line. If the user wrote none, the lines go to the voices in turn."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if any(re.match(r"\[speaker_\d+\]\s*:", ln, re.I) for ln in lines):
        return "\n".join(lines)
    return "\n".join(f"[Speaker_{i % n + 1}]: {ln}" for i, ln in enumerate(lines))


class Store:
    """Saved voices: a short sample with a name. They are the 'voice memory': pick one to read any text or to put in a dialog."""

    def __init__(self, root):
        self.root = Path(root)
        self.vdir, self.odir = self.root / "voices", self.root / "out"
        self.index = self.root / "voices.json"
        self.takes_file = self.root / "takes.json"
        self.items = []
        for d in (self.vdir, self.odir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            self.items = json.loads(self.index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []
        self.takes = self._load_takes()

    def _write(self):
        tmp = self.index.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.index)

    def get(self, vid):
        return next((x for x in self.items if x["id"] == vid), None)

    def path(self, vid):
        it = self.get(vid)
        f = self.vdir / it["file"] if it else None
        return f if f and f.is_file() else None

    def out_path(self, oid):
        f = self.odir / (Path(str(oid)).name)
        return f if f.is_file() else None

    def _load_takes(self):
        try:
            d = json.loads(self.takes_file.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {"next": 1, "items": []}
        except (OSError, ValueError):
            return {"next": 1, "items": []}

    def _write_takes(self):
        tmp = self.takes_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.takes, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.takes_file)

    def add_take(self, data, ext, meta):
        """Keeps the result and adds it to the list of takes: a name 'Голос N', the text, the settings used (to repeat them)."""
        oid = uuid.uuid4().hex[:10] + (ext if ext.startswith(".") else "." + ext)
        (self.odir / oid).write_bytes(data)
        n = int(self.takes.get("next", 1))
        self.takes["next"] = n + 1
        take = {"id": oid, "num": n, "name": f"Голос {n}", "star": False, "date": datetime.now().isoformat(timespec="seconds"), **meta}
        self.takes["items"].append(take)
        keep, drop = [], []
        for it in reversed(self.takes["items"]):
            (keep if it.get("star") or sum(1 for k in keep if not k.get("star")) < KEEP_TAKES else drop).append(it)
        for it in drop:
            (self.odir / it["id"]).unlink(missing_ok=True)
        self.takes["items"] = list(reversed(keep))
        self._write_takes()
        return self.take_public(take)

    def take_public(self, it):
        return {**it, "url": f"/api/voice/out/{it['id']}"}

    async def h_takes(self, _req):
        return web.json_response([self.take_public(x) for x in reversed(self.takes["items"]) if (self.odir / x["id"]).is_file()])

    async def h_take_star(self, req):
        it = next((x for x in self.takes["items"] if x["id"] == req.match_info["id"]), None)
        if not it:
            raise web.HTTPNotFound()
        it["star"] = not it.get("star")
        self._write_takes()
        return web.json_response({"star": it["star"]})

    async def h_take_rename(self, req):
        it = next((x for x in self.takes["items"] if x["id"] == req.match_info["id"]), None)
        if not it:
            raise web.HTTPNotFound()
        try:
            name = str((await req.json()).get("name") or "").strip()[:60]
        except Exception:
            name = ""
        if name:
            it["name"] = name
            self._write_takes()
        return web.json_response({"name": it["name"]})

    async def h_take_delete(self, req):
        it = next((x for x in self.takes["items"] if x["id"] == req.match_info["id"]), None)
        if not it:
            raise web.HTTPNotFound()
        (self.odir / it["id"]).unlink(missing_ok=True)
        self.takes["items"] = [x for x in self.takes["items"] if x is not it]
        self._write_takes()
        return web.json_response({"ok": True})

    async def h_takes_clear(self, _req):
        gone = [x for x in self.takes["items"] if not x.get("star")]
        for it in gone:
            (self.odir / it["id"]).unlink(missing_ok=True)
        self.takes["items"] = [x for x in self.takes["items"] if x.get("star")]
        self._write_takes()
        return web.json_response({"removed": len(gone)})

    def public(self, it):
        return {**it, "url": f"/api/voice/saved/{it['id']}/file"}

    async def h_list(self, _req):
        return web.json_response([self.public(x) for x in reversed(self.items)])

    async def h_file(self, req):
        f = self.path(req.match_info["id"])
        if not f:
            raise web.HTTPNotFound()
        return web.FileResponse(f)

    async def h_out(self, req):
        f = self.out_path(req.match_info["name"])
        if not f:
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "no-store"})

    async def h_save(self, req):
        """A name + either a result of the lab ('out') or an uploaded sample ('file')."""
        name, note, out, data, ext = "", "", "", None, ".mp3"
        try:
            async for field in await req.multipart():
                if field.name == "name":
                    name = (await field.read()).decode("utf-8").strip()
                elif field.name == "note":
                    note = (await field.read()).decode("utf-8").strip()
                elif field.name == "out":
                    out = (await field.read()).decode("utf-8").strip()
                elif field.name == "file" and field.filename:
                    ext = Path(field.filename).suffix.lower()
                    data = bytes(await field.read())
        except (ValueError, UnicodeDecodeError):
            return _err("Не удалось прочитать данные")
        name = name.replace("@", "")[:60]
        if not name:
            return _err("Напишите название голоса")
        if out:
            f = self.out_path(out)
            if not f:
                return _err("Этот результат уже удалён: сделайте озвучку заново")
            data, ext = f.read_bytes(), f.suffix.lower()
        if not data:
            return _err("Нет звука: выберите файл или сначала сделайте озвучку")
        if ext not in AUD_EXT:
            return _err("Нужен звуковой файл (mp3, wav, flac, m4a, ogg)")
        if len(data) > MAX_UPLOAD:
            return _err("Файл слишком большой (до 60 МБ)")
        vid = uuid.uuid4().hex[:10]
        (self.vdir / f"{vid}{ext}").write_bytes(data)
        self.items.append({"id": vid, "name": name, "note": note[:300], "file": f"{vid}{ext}", "date": datetime.now().isoformat(timespec="seconds")})
        self._write()
        return web.json_response(self.public(self.items[-1]))

    async def h_delete(self, req):
        it = self.get(req.match_info["id"])
        if not it:
            raise web.HTTPNotFound()
        (self.vdir / it["file"]).unlink(missing_ok=True)
        self.items = [x for x in self.items if x["id"] != it["id"]]
        self._write()
        return web.json_response({"ok": True})
