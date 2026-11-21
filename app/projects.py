"""Projects of the LLM section: a named folder with documents, skills, a short summary («memory») and chats.

Layout: DATA_DIR/projects/<id>/project.json, docs/<name>.txt (text of every uploaded document), skills/<name>.md, summary.md.
Chats stay in DATA_DIR/chats; a chat of a project has "project": "<id>" in its json.
"""
import io
import json
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

DOC_EXT = (".md", ".markdown", ".txt", ".docx")
MAX_FILE = 20_000_000
CTX_DOCS = 24000      # characters of documents given to the model per request
CTX_SKILLS = 16000
CTX_SUMMARY = 6000
CHUNK = 1500


def _text(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def docx_text(data):
    """Plain text of a .docx (paragraphs and table cells) without extra libraries."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ValueError("Не удалось прочитать Word-файл (нужен .docx, не старый .doc).")
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ElementTree.fromstring(xml)
    paras = []
    for p in root.iter(ns + "p"):
        parts = []
        for el in p.iter():
            if el.tag == ns + "t" and el.text:
                parts.append(el.text)
            elif el.tag == ns + "tab":
                parts.append("\t")
            elif el.tag == ns + "br":
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras).strip()


def _safe_name(name, ext):
    stem = re.sub(r"[^\w\- .()]+", "_", Path(name).stem).strip(" ._")[:80] or "document"
    return stem + ext


def _expand(files):
    out, total = [], 0
    for name, data in files:
        if name.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                raise ValueError(f"Архив «{Path(name).name}» повреждён или это не zip.")
            for info in zf.infolist():
                n = info.filename.replace("\\", "/")
                if info.is_dir() or n.startswith("/") or ".." in n.split("/") or "__MACOSX" in n:
                    continue
                total += info.file_size
                if total > MAX_FILE or len(out) > 400:
                    raise ValueError("Архив слишком большой (нужны текстовые файлы, обычно меньше мегабайта).")
                out.append((n, zf.read(info)))
        else:
            if len(data) > MAX_FILE:
                raise ValueError(f"Файл «{Path(name).name}» слишком большой.")
            out.append((name, data))
    return out


def _to_text(name, data):
    ext = Path(name).suffix.lower()
    if ext == ".docx":
        return docx_text(data)
    return _text(data)


class Projects:
    def __init__(self, root):
        self.root = Path(root)

    # --- projects
    def _dir(self, pid):
        if not re.fullmatch(r"[a-z0-9]{4,40}", pid or ""):
            raise ValueError("bad project id")
        return self.root / pid

    def _meta(self, pid):
        p = self._dir(pid) / "project.json"
        if not p.exists():
            raise KeyError(pid)
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_meta(self, pid, meta):
        meta["updated"] = datetime.now().isoformat(timespec="seconds")
        (self._dir(pid) / "project.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def list(self):
        out = []
        for d in self.root.iterdir() if self.root.exists() else []:
            if (d / "project.json").exists():
                try:
                    m = json.loads((d / "project.json").read_text(encoding="utf-8"))
                except ValueError:
                    continue
                out.append({"id": d.name, "name": m.get("name", d.name), "updated": m.get("updated", ""),
                            "docs": len(list((d / "docs").glob("*.txt"))) if (d / "docs").exists() else 0,
                            "skills": len(list((d / "skills").glob("*.md"))) if (d / "skills").exists() else 0})
        return sorted(out, key=lambda x: x["updated"], reverse=True)

    def create(self, name):
        name = " ".join((name or "").split())[:80] or "Новый проект"
        pid = uuid.uuid4().hex[:10]
        d = self._dir(pid)
        (d / "docs").mkdir(parents=True)
        (d / "skills").mkdir()
        self._save_meta(pid, {"name": name, "created": datetime.now().isoformat(timespec="seconds")})
        return pid

    def rename(self, pid, name):
        m = self._meta(pid)
        m["name"] = " ".join((name or "").split())[:80] or m["name"]
        self._save_meta(pid, m)

    def delete(self, pid):
        shutil.rmtree(self._dir(pid), ignore_errors=True)

    def clear(self, pid):
        """Empty the project (documents, skills, summary), the project itself stays."""
        d = self._dir(pid)
        self._meta(pid)
        for sub in ("docs", "skills"):
            shutil.rmtree(d / sub, ignore_errors=True)
            (d / sub).mkdir()
        (d / "summary.md").unlink(missing_ok=True)

    def path(self, pid):
        self._meta(pid)
        return self._dir(pid)

    # --- content
    def detail(self, pid):
        m = self._meta(pid)
        d = self._dir(pid)
        docs = [{"name": p.name, "size": len(p.read_text(encoding="utf-8", errors="replace"))} for p in sorted((d / "docs").glob("*.txt"))]
        skills = [{"name": p.name} for p in sorted((d / "skills").glob("*.md"))]
        summary = (d / "summary.md").read_text(encoding="utf-8") if (d / "summary.md").exists() else ""
        return {"id": pid, "name": m.get("name"), "docs": docs, "skills": skills, "summary": summary}

    def add_docs(self, pid, files):
        d = self._dir(pid) / "docs"
        self._meta(pid)
        d.mkdir(exist_ok=True)
        n, bad = 0, []
        for name, data in _expand(files):
            if Path(name).suffix.lower() not in DOC_EXT:
                continue
            try:
                text = _to_text(name, data)
            except ValueError as e:
                bad.append(str(e))
                continue
            if not text.strip():
                continue
            (d / (_safe_name(name, ".txt"))).write_text(text, encoding="utf-8")
            n += 1
        if not n:
            raise ValueError(bad[0] if bad else "Не нашёл документов. Подойдут .docx, .md, .txt или архив .zip с ними.")
        return n

    def del_doc(self, pid, name):
        (self._dir(pid) / "docs" / Path(name).name).unlink(missing_ok=True)

    def add_skills(self, pid, files):
        d = self._dir(pid) / "skills"
        self._meta(pid)
        d.mkdir(exist_ok=True)
        n = 0
        for name, data in _expand(files):
            if Path(name).suffix.lower() not in (".md", ".markdown", ".txt", ".docx"):
                continue
            text = _to_text(name, data)
            if text.strip():
                (d / _safe_name(name, ".md")).write_text(text, encoding="utf-8")
                n += 1
        if not n:
            raise ValueError("Не нашёл скилл. Подойдёт файл .md, .txt, .docx или архив .zip.")
        return n

    def del_skill(self, pid, name):
        (self._dir(pid) / "skills" / Path(name).name).unlink(missing_ok=True)

    def set_summary(self, pid, text):
        self._meta(pid)
        (self._dir(pid) / "summary.md").write_text((text or "").strip()[:CTX_SUMMARY * 2], encoding="utf-8")

    def doc_name_ok(self, pid, name):
        return (self._dir(pid) / "docs" / Path(name).name).exists()

    # --- what the model gets
    def context(self, pid, query=""):
        """Text for the system prompt: project skills, summary, documents (small ones whole, big ones by pieces matching the question)."""
        try:
            m = self._meta(pid)
        except (KeyError, ValueError):
            return ""
        d = self._dir(pid)
        parts = [f"ПРОЕКТ «{m.get('name')}». Пользователь работает в рамках этого проекта: опирайся на его скиллы, сводку и документы ниже, "
                 "не противоречь им. Если нужного в документах нет, так и скажи, не выдумывай."]
        left = CTX_SKILLS
        for p in sorted((d / "skills").glob("*.md")) if (d / "skills").exists() else []:
            t = p.read_text(encoding="utf-8", errors="replace").strip()[:left]
            if t:
                parts.append(f"# СКИЛЛ ПРОЕКТА «{p.stem}» (работай по нему всегда)\n\n{t}")
                left -= len(t)
            if left <= 0:
                break
        if (d / "summary.md").exists():
            s = (d / "summary.md").read_text(encoding="utf-8").strip()[:CTX_SUMMARY]
            if s:
                parts.append("# СВОДКА ПРОЕКТА (память: герои, стиль, решения)\n\n" + s)
        docs = [(p.stem, p.read_text(encoding="utf-8", errors="replace").strip()) for p in sorted((d / "docs").glob("*.txt"))] if (d / "docs").exists() else []
        docs = [x for x in docs if x[1]]
        if docs:
            if sum(len(t) for _, t in docs) <= CTX_DOCS:
                parts.append("# ДОКУМЕНТЫ ПРОЕКТА\n\n" + "\n\n".join(f"## {n}\n{t}" for n, t in docs))
            else:
                parts.append("# ДОКУМЕНТЫ ПРОЕКТА (длинные: ниже самые подходящие к вопросу куски, остальное не показано)\n\n"
                             + "\n\n".join(f"## {n} (часть)\n{t}" for n, t in self._best_chunks(docs, query)))
        return "\n\n".join(parts) if len(parts) > 1 else ""

    @staticmethod
    def _best_chunks(docs, query):
        words = {w for w in re.findall(r"\w{3,}", (query or "").lower())}
        stems = {w[:max(3, len(w) - 2)] for w in words}   # a rough stem: Russian endings differ
        chunks = []
        for name, text in docs:
            paras, cur = re.split(r"\n\s*\n|\n", text), ""
            pieces = []
            for para in paras:
                if len(cur) + len(para) > CHUNK and cur:
                    pieces.append(cur)
                    cur = ""
                cur += para + "\n"
            if cur.strip():
                pieces.append(cur)
            for i, c in enumerate(pieces):
                low = c.lower()
                score = sum(low.count(s) for s in stems)
                chunks.append((score, 1 if i == 0 else 0, name, i, c.strip()))   # the start of a document is a small bonus: it holds the title and the idea
        chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)
        picked, used = [], 0
        for score, _, name, i, c in chunks:
            if used + len(c) > CTX_DOCS:
                continue
            picked.append((name, i, c))
            used += len(c)
        picked.sort(key=lambda x: (x[0], x[1]))   # back in reading order
        return [(n, c) for n, _, c in picked]
