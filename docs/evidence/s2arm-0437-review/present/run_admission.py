from pathlib import Path
import tempfile,subprocess,sys
src=Path(sys.argv[1]).read_text()
pos=src.index('    if (st == 1 && link_on()')
start=src.index('    pthread_mutex_lock(&g_pq_mu);',pos)
end=src.index('    pq_item *it =', start)
with tempfile.TemporaryDirectory() as tmp:
    dest=Path(tmp); (dest/'admission.inc').write_text(src[start:end])
    subprocess.run(['clang','-O2','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread','-I'+tmp,str(Path(__file__).parent/'admission.c'),'-o',str(dest/'probe')],check=True)
    sys.exit(subprocess.run([str(dest/'probe')],timeout=10).returncode)
