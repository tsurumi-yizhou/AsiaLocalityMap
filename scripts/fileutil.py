"""Small file helpers shared by the data scripts."""
import hashlib
import json


COMPACT = dict(ensure_ascii=False, separators=(',', ':'))
PRETTY = dict(ensure_ascii=False, indent=2)


def json_text(obj, compact=False, **options):
    return json.dumps(obj, **(COMPACT if compact else PRETTY), **options)


def write_json(path, obj, compact=False, newline=False, **options):
    path.write_text(json_text(obj, compact, **options) + ('\n' if newline else ''))


def sha256_bytes(contents):
    return hashlib.sha256(contents).hexdigest()


def sha256_file(path):
    return sha256_bytes(path.read_bytes())
