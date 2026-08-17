#!/usr/bin/env python3
"""Read-only GGUF header reader: list tensor names, types, dims and on-disk sizes.

Written to check --override-tensor regexes against real tensor names before
deploying them. Stdlib only: the llm-server guest has no numpy and installing
packages there is not allowed. Reads only the header of each shard, never the
tensor data, so it is cheap even on a 138GB model.

Usage (tab-separated: name, type, dims, on-disk bytes, shard):

    ./scripts/gguf-tensor-names.py /path/to/model-*.gguf > tensors.tsv

Output is line-oriented so a candidate rule can be validated directly, e.g.
count what `blk\\.(40|41|42)\\.ffn_(down|gate|up)_exps` would move to VRAM.
"""
import os
import struct
import sys

GGUF_MAGIC = b"GGUF"

# metadata value type ids
(UINT8, INT8, UINT16, INT16, UINT32, INT32, FLOAT32, BOOL, STRING, ARRAY,
 UINT64, INT64, FLOAT64) = range(13)

_FIXED = {
    UINT8: ("<B", 1), INT8: ("<b", 1),
    UINT16: ("<H", 2), INT16: ("<h", 2),
    UINT32: ("<I", 4), INT32: ("<i", 4),
    FLOAT32: ("<f", 4), BOOL: ("<?", 1),
    UINT64: ("<Q", 8), INT64: ("<q", 8), FLOAT64: ("<d", 8),
}

GGML_TYPE_NAMES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
    8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K",
    14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS",
    19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S", 23: "IQ4_XS",
    24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64", 29: "IQ1_M",
    30: "BF16", 39: "MXFP4",
}


class Reader:
    def __init__(self, fh):
        self.fh = fh

    def raw(self, n):
        b = self.fh.read(n)
        if len(b) != n:
            raise EOFError("short read")
        return b

    def scalar(self, vtype):
        fmt, size = _FIXED[vtype]
        return struct.unpack(fmt, self.raw(size))[0]

    def string(self):
        n = struct.unpack("<Q", self.raw(8))[0]
        return self.raw(n).decode("utf-8", errors="replace")

    def value(self, vtype):
        if vtype == STRING:
            return self.string()
        if vtype == ARRAY:
            elem_type = struct.unpack("<I", self.raw(4))[0]
            count = struct.unpack("<Q", self.raw(8))[0]
            if elem_type == STRING:
                # skip long token arrays, keep only the count
                for _ in range(count):
                    n = struct.unpack("<Q", self.raw(8))[0]
                    self.fh.seek(n, os.SEEK_CUR)
                return "<%d strings>" % count
            if elem_type == ARRAY:
                raise ValueError("nested arrays unsupported")
            fmt, size = _FIXED[elem_type]
            vals = [struct.unpack(fmt, self.raw(size))[0] for _ in range(count)]
            return vals if count <= 16 else "<%d values>" % count
        return self.scalar(vtype)


def read_header(path):
    out = {"path": path, "kv": {}, "tensors": []}
    with open(path, "rb") as fh:
        r = Reader(fh)
        if r.raw(4) != GGUF_MAGIC:
            raise ValueError("not a GGUF file: %s" % path)
        version = struct.unpack("<I", r.raw(4))[0]
        n_tensors = struct.unpack("<Q", r.raw(8))[0]
        n_kv = struct.unpack("<Q", r.raw(8))[0]
        out["version"] = version
        out["n_tensors"] = n_tensors
        for _ in range(n_kv):
            key = r.string()
            vtype = struct.unpack("<I", r.raw(4))[0]
            out["kv"][key] = r.value(vtype)
        for _ in range(n_tensors):
            name = r.string()
            n_dims = struct.unpack("<I", r.raw(4))[0]
            dims = [struct.unpack("<Q", r.raw(8))[0] for _ in range(n_dims)]
            ttype = struct.unpack("<I", r.raw(4))[0]
            offset = struct.unpack("<Q", r.raw(8))[0]
            out["tensors"].append(
                {"name": name, "dims": dims, "type": ttype, "offset": offset})
        align = out["kv"].get("general.alignment", 32)
        pos = fh.tell()
        data_start = pos + (-pos % align)
        out["data_start"] = data_start
        out["file_size"] = os.path.getsize(path)
    # derive on-disk size from consecutive offsets (tensors are stored in order)
    ts = sorted(out["tensors"], key=lambda t: t["offset"])
    for i, t in enumerate(ts):
        end = (ts[i + 1]["offset"] if i + 1 < len(ts)
               else out["file_size"] - out["data_start"])
        t["nbytes"] = end - t["offset"]
    return out


def main(paths):
    all_tensors = []
    for p in paths:
        h = read_header(p)
        sys.stderr.write("# %s: v%d, %d tensors\n"
                         % (os.path.basename(p), h["version"], h["n_tensors"]))
        for t in h["tensors"]:
            t["shard"] = os.path.basename(p)
            all_tensors.append(t)
    for t in all_tensors:
        print("%s\t%s\t%s\t%d\t%s" % (
            t["name"], GGML_TYPE_NAMES.get(t["type"], "type%d" % t["type"]),
            "x".join(str(d) for d in t["dims"]), t["nbytes"], t["shard"]))


if __name__ == "__main__":
    paths = sys.argv[1:]
    if not paths or paths[0].startswith("-"):
        sys.exit(__doc__)
    main(paths)
