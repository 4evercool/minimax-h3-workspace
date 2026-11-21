"""Reference Mode: saved cards of a character, a vehicle, an object or a place.

A card keeps several pictures (each can be switched on or off), an optional voice sample and a short text
(what it is, what to keep). Cards live in data/refmodes.json, their files in data/refmodes/<id>/. The pages
(Video studio, Action studio) take the switched-on pictures of the ticked cards as references and replace
@name in a scene text with the picture tag plus a one-line definition (that part is done in index.html).
"""
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from aiohttp import web

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AUD_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
TYPES = ("character", "vehicle", "object", "location")
MAX_IMAGES = 9
MAX_UPLOAD = 60 * 1024 * 1024


def token(name):
    """What the user types after @ in a scene text: the name without spaces."""
    return re.sub(r"\s+", "_", str(name or "").strip())


def _err(text, status=400):
    return web.json_response({"error": text}, status=status)


class Store:
    def __init__(self, index_file, files_dir):
        self.index = Path(index_file)
        self.dir = Path(files_dir)
        self.items = []
        if self.index.exists():
            try:
                self.items = json.loads(self.index.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                try:   # a damaged list must not be overwritten silently: keep it next to the new one
                    shutil.copy2(self.index, self.index.with_name("refmodes.broken.json"))
                except OSError:
                    pass
                self.items = []

    def save(self):
        self.index.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.index)

    def get(self, rid):
        return next((x for x in self.items if x["id"] == rid), None)

    def public(self, it):
        base = f"/api/refmodes/{it['id']}/file/"
        out = dict(it)
        out["images"] = [{**i, "url": base + i["file"]} for i in it.get("images", [])]
        v = it.get("voice")
        out["voice"] = {**v, "url": base + v["file"]} if v else None
        return out

    async def h_list(self, _req):
        return web.json_response([self.public(x) for x in self.items])

    async def h_file(self, req):
        it = self.get(req.match_info["id"])
        name = Path(req.match_info["name"]).name
        if not it:
            raise web.HTTPNotFound()
        known = {i["file"] for i in it.get("images", [])} | ({it["voice"]["file"]} if it.get("voice") else set())
        f = self.dir / it["id"] / name
        if name not in known or not f.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(f)

    async def h_save(self, req):
        meta, up = None, {}
        try:
            async for field in await req.multipart():
                if field.name == "meta":
                    meta = json.loads((await field.read()).decode("utf-8"))
                elif field.name and field.filename:
                    data = bytes(await field.read())
                    if len(data) > MAX_UPLOAD:
                        return _err("Файл «%s» слишком большой (до 60 МБ)" % field.filename)
                    up[field.name] = (field.filename, data)
        except (ValueError, UnicodeDecodeError):
            return _err("Не удалось прочитать данные карточки")
        if not isinstance(meta, dict):
            return _err("Не удалось прочитать данные карточки")

        rid = str(meta.get("id") or "")
        old = self.get(rid) if rid else None
        if rid and not old:
            return _err("Карточка не найдена: возможно, её удалили", 404)
        name = str(meta.get("name") or "").replace("@", "").strip()[:60]
        if not name:
            return _err("Напишите название: по нему карточка вставляется в текст сцены (@название)")
        tok = token(name).lower()
        if any(x is not old and token(x["name"]).lower() == tok for x in self.items):
            return _err("Карточка с таким названием уже есть")
        typ = meta.get("type") if meta.get("type") in TYPES else "character"

        def text(key, limit):
            return re.sub(r"\s+", " ", str(meta.get(key) or "")).strip()[:limit]

        # check everything first, write after: a refused save must not leave half of a card on the disk
        old_imgs = {i["file"] for i in (old or {}).get("images", [])}
        plan = []
        for n, im in enumerate((meta.get("images") or [])[:MAX_IMAGES]):
            if not isinstance(im, dict):
                continue
            fn = Path(str(im.get("file") or "")).name
            label, on = str(im.get("label") or "").strip()[:80], bool(im.get("on", True))
            if fn and fn in old_imgs:
                plan.append((fn, None, label, on))
                continue
            got = up.get(f"img_{n}")
            if not got:
                continue
            if Path(got[0]).suffix.lower() not in IMG_EXT:
                return _err("Изображение «%s»: нужен файл PNG, JPG или WEBP" % got[0])
            plan.append((None, got, label, on))
        voice_plan = None
        if meta.get("voice_keep") and old and old.get("voice"):
            voice_plan = ("old", old["voice"])
        elif "voice" in up:
            if Path(up["voice"][0]).suffix.lower() not in AUD_EXT:
                return _err("Голос «%s»: нужен звуковой файл (WAV, MP3, FLAC, M4A, OGG)" % up["voice"][0])
            voice_plan = ("new", up["voice"])

        rid = old["id"] if old else uuid.uuid4().hex[:12]
        folder = self.dir / rid
        folder.mkdir(parents=True, exist_ok=True)
        images = []
        for fn, got, label, on in plan:
            if got:
                fn = uuid.uuid4().hex[:10] + Path(got[0]).suffix.lower()
                (folder / fn).write_bytes(got[1])
            images.append({"file": fn, "label": label, "on": on})
        voice = None
        if voice_plan and voice_plan[0] == "old":
            voice = voice_plan[1]
        elif voice_plan:
            vf = "voice_" + uuid.uuid4().hex[:8] + Path(voice_plan[1][0]).suffix.lower()
            (folder / vf).write_bytes(voice_plan[1][1])
            voice = {"file": vf, "label": Path(voice_plan[1][0]).name[:80]}
        keep = {i["file"] for i in images} | ({voice["file"]} if voice else set())
        dropped = old_imgs | ({old["voice"]["file"]} if old and old.get("voice") else set())
        for fn in dropped - keep:   # copies the program made itself: the user's own files are not touched
            (folder / Path(fn).name).unlink(missing_ok=True)

        item = {"id": rid, "name": name, "type": typ, "what": text("what", 300), "features": text("features", 1200),
                "images": images, "voice": voice, "updated": datetime.now().isoformat(timespec="seconds")}
        if old:
            self.items[self.items.index(old)] = item
        else:
            self.items.insert(0, item)
        self.save()
        return web.json_response(self.public(item))

    async def h_delete(self, req):
        it = self.get(req.match_info["id"])
        if not it:
            raise web.HTTPNotFound()
        self.items = [x for x in self.items if x is not it]
        self.save()
        folder = self.dir / it["id"]
        if folder.is_dir() and self.dir.resolve() in folder.resolve().parents:
            shutil.rmtree(folder, ignore_errors=True)
        return web.json_response({"ok": True})
