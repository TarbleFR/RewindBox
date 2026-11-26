from pathlib import Path
import argparse,hashlib,re,subprocess,tempfile
p=argparse.ArgumentParser()
p.add_argument("reference",type=Path);p.add_argument("ordinary",type=Path);p.add_argument("diagnostic",type=Path)
a=p.parse_args();exc=lambda b:hashlib.sha256(b).hexdigest()
def examine(d):
 obj=d/"callbacks.o"
 with tempfile.TemporaryDirectory() as tmp:
    raw=Path(tmp)/"text";subprocess.run(["objcopy","--dump-section",f".text={raw}",obj],check=True)
    text=raw.read_bytes()
 nm=subprocess.check_output(["nm","--defined-only",obj],text=True)
 if "__fi_count_on_block_invoke" not in nm or "__fi_commit_block_invoke" not in nm: raise ValueError("Missing real callbacks")
 rel="\n".join(line.strip() for line in subprocess.check_output(["objdump","-r","-j",".text",obj],text=True).splitlines() if re.match(r"^[a-fA-F\d]+\s+R_",line)).encode()
 return text,(d/"callbacks.ll").read_bytes(),rel,nm
base=examine(a.reference);normal=examine(a.ordinary);diag=examine(a.diagnostic)
for j,label in enumerate(["ELF .text","LLVM IR","relocations for .text"]):
 if base[j]!=normal[j]: raise ValueError(f"Production instructions differ in {label}")
 print(f"{label}: reference == ordinary, {len(base[j])} bytes, SHA256 {exc(base[j])}")
assert base[0]!=diag[0] and "g_rb_fi_stats_" not in normal[3] and "g_rb_fi_stats_" in diag[3]
print(f"Diagnostic .text: {len(diag[0])} bytes, SHA256 {exc(diag[0])}; diagnostic symbols absent from ordinary object")
