"""Feed the actual parser an archive built entirely from two constant strings."""
import csv,io,subprocess,sys,tempfile,zipfile
from pathlib import Path
template="[rb-speed] up to present 300: game speed 100.0 %; 30.0 presents a second, at interval 1 / 2 / 3+ 0 / 300 / 0; frame interpolation on, 150 {} and 300 real frames shown"
with tempfile.TemporaryDirectory() as out:
    data=Path(out)/"constructed.zip"
    with zipfile.ZipFile(data,"w") as f:
        f.writestr("synthetic-old",template.format("interpolated"))
        f.writestr("synthetic-new",template.replace("30.0 presents","guest clock 0.500 s a second; 30.0 presents").format("midpoint drawables")+" on FI path")
    txt=subprocess.check_output([sys.executable,sys.argv[1],data,"synthetic-old","synthetic-new"],text=True)
    rows=list(csv.DictReader(io.StringIO(txt)))
    assert len(rows)==2
    assert rows[0]["guest_presents_per_guest_s_approx"]=="" and float(rows[1]["guest_presents_per_guest_s_approx"])==60
    for r in rows:
        assert r["midpoint_drawables_shown"]=="150" and float(r["midpoint_fps_approx"])==15
        assert r["real_shown_by_fi"]=="300" and "generated_fps_approx" not in r
print("Both constructed formats yielded 150 midpoint drawables, 15 midpoint/s and 300 original drawables; independent guest-clock rate 60 when supplied")
