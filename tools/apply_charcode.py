"""Re-add the custom character code feature to an official ok-ww release tree.

Usage: python tools/apply_charcode.py <release-tree> <git-url-for-pyappify>

Upstream removed the feature in ok-oldking/ok-wuthering-waves@d0a5929 (2026-11-16).
This script puts it back on top of a release from ok-oldking/ok-ww-update:

  1. copies charcode/overlay/ (CustomCharLoader.py, CharacterCodeTab.py) into the tree
  2. re-adds apply_team_char_classes() to src/char/CharFactory.py
  3. re-adds its call in src/task/BaseCombatTask.py
  4. registers the Character Code tab in config.py (custom_tabs)
  5. points every git_url in pyappify.yml at our update repository
  6. merges the feature's translations into i18n/*/ok.po and recompiles ok.mo

Every edit is anchored on upstream code. If an anchor is gone the script stops with
an error instead of guessing, so a broken release is never tagged.
Running it twice on the same tree is harmless.
"""
import pathlib
import re
import shutil
import sys

import polib

HERE = pathlib.Path(__file__).resolve().parent.parent / "charcode"

CHAR_FACTORY_IMPORT = "from src.char.CustomCharLoader import load_team_char_class, normalize_team"

APPLY_FUNCTION = '''def apply_team_char_classes(task, chars):
    """Apply custom code only after the complete three-character team is known."""
    if len(chars) != 3 or any(char is None for char in chars):
        return chars
    infos = [char_dict.get(char.char_name) for char in chars]
    if any(info is None for info in infos):
        return chars
    builtin_classes = [info['cls'] for info in infos]
    try:
        team = normalize_team(builtin_classes)
    except ValueError:
        return chars
    for index, (char, builtin_cls) in enumerate(zip(chars, builtin_classes)):
        desired_cls = load_team_char_class(builtin_cls, team)
        if type(char) is desired_cls:
            continue
        replacement = desired_cls(
            task,
            char.index,
            char_name=char.char_name,
            confidence=char.confidence,
            ring_index=char.ring_index,
            char_type=char.char_type,
            buff_time=char.buff_time,
        )
        replacement.__dict__.update(char.__dict__)
        chars[index] = replacement
    return chars


'''

TAB_ENTRY = '["src.gui.CharacterCodeTab", "CharacterCodeTab"]'


class PatchError(RuntimeError):
    pass


def read(path):
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write(path, text, newline):
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def patch_char_factory(root):
    path = root / "src/char/CharFactory.py"
    text, nl = read(path)
    if "def apply_team_char_classes(" in text:
        print("CharFactory.py: already has apply_team_char_classes, skipped")
        return
    imports = list(re.finditer(r"^from src\.char\.\w+ import [\w, ]+$", text, re.M))
    if not imports:
        raise PatchError("CharFactory.py: no 'from src.char.X import Y' lines to anchor the import")
    end = imports[-1].end()
    text = text[:end] + "\n" + CHAR_FACTORY_IMPORT + text[end:]
    anchor = re.search(r"^def is_float\(", text, re.M)
    if anchor:
        text = text[:anchor.start()] + APPLY_FUNCTION + text[anchor.start():]
    else:
        text = text.rstrip("\n") + "\n\n\n" + APPLY_FUNCTION.rstrip("\n") + "\n"
    write(path, text, nl)
    print("CharFactory.py: added import and apply_team_char_classes")


def patch_base_combat_task(root):
    path = root / "src/task/BaseCombatTask.py"
    text, nl = read(path)
    if "apply_team_char_classes(self, self.chars)" in text:
        print("BaseCombatTask.py: already calls apply_team_char_classes, skipped")
        return
    match = re.search(r"^from src\.char\.CharFactory import (.+)$", text, re.M)
    if not match:
        raise PatchError("BaseCombatTask.py: 'from src.char.CharFactory import ...' not found")
    names = [n.strip() for n in match.group(1).split(",")]
    if "apply_team_char_classes" not in names:
        names.insert(0, "apply_team_char_classes")
        text = text[:match.start()] + "from src.char.CharFactory import " + ", ".join(names) + text[match.end():]
    marker = text.find("team size changed to 2")
    if marker < 0:
        raise PatchError("BaseCombatTask.py: anchor 'team size changed to 2' not found")
    loop = re.compile(r"^([ \t]+)for char in self\.chars:\n[ \t]+if char is not None:\n[ \t]+char\.reset_state\(\)", re.M)
    found = loop.search(text, marker)
    if not found:
        raise PatchError("BaseCombatTask.py: reset_state loop after the team-size check not found")
    indent = found.group(1)
    text = text[:found.start()] + f"{indent}apply_team_char_classes(self, self.chars)\n\n" + text[found.start():]
    write(path, text, nl)
    print("BaseCombatTask.py: added apply_team_char_classes call")


def patch_config(root):
    path = root / "config.py"
    text, nl = read(path)
    if "src.gui.CharacterCodeTab" in text:
        print("config.py: tab already registered, skipped")
        return
    existing = re.search(r"^([ \t]*)'custom_tabs':\s*\[", text, re.M)
    if existing:
        indent = existing.group(1)
        text = text[:existing.end()] + f"\n{indent}    {TAB_ENTRY}," + text[existing.end():]
    else:
        anchor = re.search(r"^([ \t]*)'my_app':", text, re.M)
        if not anchor:
            raise PatchError("config.py: neither 'custom_tabs' nor 'my_app' found")
        indent = anchor.group(1)
        text = text[:anchor.start()] + f"{indent}'custom_tabs': [{TAB_ENTRY}],\n" + text[anchor.start():]
    write(path, text, nl)
    print("config.py: registered CharacterCodeTab")


def patch_pyappify(root, git_url):
    path = root / "pyappify.yml"
    text, nl = read(path)
    new, count = re.subn(r'^(\s*git_url:\s*)"[^"]*"', lambda m: f'{m.group(1)}"{git_url}"', text, flags=re.M)
    if count == 0:
        raise PatchError("pyappify.yml: no git_url entries found")
    write(path, new, nl)
    print(f"pyappify.yml: {count} git_url entries -> {git_url}")


def merge_translations(root):
    for extra_path in sorted((HERE / "i18n").glob("*.po")):
        target_dir = root / "i18n" / extra_path.stem / "LC_MESSAGES"
        po_path = target_dir / "ok.po"
        if not po_path.exists():
            print(f"i18n: {extra_path.stem} not in this release, skipped")
            continue
        po = polib.pofile(str(po_path))
        known = {e.msgid for e in po}
        new_entries = [polib.POEntry(msgid=e.msgid, msgstr=e.msgstr)
                       for e in polib.pofile(str(extra_path)) if e.msgid not in known]
        added = len(new_entries)
        if new_entries:
            # Append as text: re-saving would rewrap upstream's existing entries.
            text, nl = read(po_path)
            block = "\n".join(str(e) for e in new_entries)
            write(po_path, text.rstrip("\n") + "\n\n" + block + "\n", nl)
            po = polib.pofile(str(po_path))
        po.save_as_mofile(str(target_dir / "ok.mo"))
        print(f"i18n: {extra_path.stem} +{added} entries, ok.mo rebuilt")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    root = pathlib.Path(sys.argv[1]).resolve()
    git_url = sys.argv[2]
    for rel in ("src/char/CharFactory.py", "src/task/BaseCombatTask.py", "config.py", "pyappify.yml"):
        if not (root / rel).is_file():
            raise PatchError(f"{rel} missing; is {root} an ok-ww release tree?")
    for src in (HERE / "overlay").rglob("*.py"):
        dst = root / src.relative_to(HERE / "overlay")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"overlay: {dst.relative_to(root).as_posix()}")
    patch_char_factory(root)
    patch_base_combat_task(root)
    patch_config(root)
    patch_pyappify(root, git_url)
    merge_translations(root)
    for rel in ("src/char/CharFactory.py", "src/task/BaseCombatTask.py", "config.py",
                "src/char/CustomCharLoader.py", "src/gui/CharacterCodeTab.py"):
        compile((root / rel).read_bytes(), rel, "exec")  # syntax check, writes no __pycache__
    print("done")


if __name__ == "__main__":
    try:
        main()
    except PatchError as e:
        sys.exit(f"PATCH FAILED: {e}")
