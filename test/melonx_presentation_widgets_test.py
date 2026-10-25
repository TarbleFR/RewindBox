"""Reproduce the reported null-context warning, then exercise the fixed widget."""
import re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
test=(ROOT/'test/melonx_presentation_widgets_test.dart').read_text()
with tempfile.TemporaryDirectory(prefix='.melonx-presentation-',dir=ROOT/'test') as temporary:
    work=Path(temporary)
    old=subprocess.check_output(['git','show','fa6d056e668e55fb7b96959b20cc15064e52e68a:lib/widgets/melonx_internal_playlist_actions.dart'],cwd=ROOT,text=True)
    old=re.sub(r"import '../([^']+)';",r"import 'package:neostation/\1';",old)
    old=re.sub(r"import '(\w+\.dart)';",r"import 'package:neostation/widgets/\1';",old)
    (work/'old_widget.dart').write_text(old)
    (work/'old_test.dart').write_text(test.replace("'package:neostation/widgets/melonx_internal_playlist_actions.dart'","'old_widget.dart'").replace("'database_test_helper.dart'","'../database_test_helper.dart'"))
    subprocess.run(['flutter','test','--no-pub','--dart-define=EXPECT_OLD=true',str(work/'old_test.dart')],cwd=ROOT,check=True)
subprocess.run(['flutter','test','--no-pub','test/melonx_presentation_widgets_test.dart'],cwd=ROOT,check=True)
