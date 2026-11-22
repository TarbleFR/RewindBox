#!/usr/bin/env python3
"""Record what each ordered adapter found before it ran, so a gate can rebuild an adapter's control exactly.

Usage: melonx_adapter_preimages.py <copy of the pristine upstream to prepare> [<store>]

melonx_adapter_control rebuilds the tree an adapter was applied to by undoing, in the final preparation, the `once`
replacements of that adapter and of every later adapter sharing its files. That only works when each replacement's
new text is unique in the final file. Since IPA 771 several adapters replace a text by a shorter or an empty one
(adapt_hogwarts_pipeline_replay: "Pump();", adapt_xci_update_identity: an empty text, adapt_descriptor_pool_lifetime:
"Retire();"), so they cannot be undone, and neither can any adapter sharing a file with them: on 22 November 2026 most
gates stopped at this step on the head of the branch.

This runs the real preparation (prepare_embedded.main) on the given copy and, right before each adapter of
melonx_adapter_control.ORDER is applied, copies the files of its BASELINE into <store>/<adapter>/ (default
dist/melonx/adapter-preimages, or MELONX_ADAPTER_PREIMAGES). Those are the bytes the adapter pins by digest, so
melonx_adapter_control restores them instead of undoing text, and still requires each to have its pinned digest and the
adapters re-applied to the control to reproduce the final preparation byte for byte. Nothing of the preparation changes:
the adapters run unmodified, in prepare_embedded's order. Writes <store>/index.json (adapter -> file -> SHA-256).
"""
from pathlib import Path
import hashlib, importlib, json, shutil, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, PREIMAGES  # noqa: E402


def main():
    source = Path(sys.argv[1]).resolve()
    store = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else PREIMAGES
    if store.exists():
        shutil.rmtree(store)
    index, applied = {}, []

    def recording(name, module, original):
        def apply(tree):
            assert Path(tree).resolve() == source and name not in index, name
            files = {}
            for relative, expected in module.BASELINE.items():
                data = (source / relative).read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                assert digest == expected, (name, relative)  # the adapter's own entry check
                target = store / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                files[relative] = digest
            index[name] = files
            applied.append(name)
            return original(tree)
        return apply

    for name in ORDER:
        module = importlib.import_module(name)
        module.apply = recording(name, module, module.apply)
    import prepare_embedded  # binds the recording functions (from adapt_x import apply as adapt_x)
    sys.argv = ['prepare_embedded.py', str(source)]
    prepare_embedded.main()
    assert applied == list(ORDER), 'prepare_embedded does not run the ordered adapters once each, in ORDER'
    (store / 'index.json').write_text(json.dumps(index, indent=1, sort_keys=True) + '\n')
    print(json.dumps(dict(result='recorded', adapters=len(index), files=sum(len(f) for f in index.values()), store=str(store))))


if __name__ == '__main__':
    main()
