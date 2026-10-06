"""Small file helpers shared by the data scripts."""
import hashlib


def sha256_bytes(contents):
    return hashlib.sha256(contents).hexdigest()


def sha256_file(path):
    return sha256_bytes(path.read_bytes())
