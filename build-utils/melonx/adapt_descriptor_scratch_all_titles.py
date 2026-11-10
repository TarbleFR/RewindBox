"""Use the binding-sized descriptor template scratch for every title, not only Hogwarts Legacy.

Core 631 sized DescriptorSetUpdater's template scratch arrays by binding number for every title, but the template path
takes them whole only under EncodingPolicy.BindingSizedDescriptorScratch, which Library.cs sets for Hogwarts Legacy
only. Off, it takes one stage's length, so a fragment texture (binding 64-95), a buffer texture or a buffer image throws
IndexOutOfRangeException, caught by UpdateAndBindDescriptorSets, which writes the set again one descriptor at a time.

Super Smash Bros. Ultimate on IPA 640 (Core 639, 4 November 2026; private logs, not in the repository), the pass and GPU
detail line: 3 317 to 12 060 texture template fallbacks per 5 s window, as many first-chance IndexOutOfRangeException
("exceptions 8944 (first: IndexOutOfRangeException ...)"); the same title on 629 logged 30 467 in a window. This is the
defect Core 631 removed for Hogwarts, measured here on another title.

Change: the flag is set for every title. IncrementalArrayDescriptors and every other Hogwarts policy keep their scope.
Semantics: the Core 631 gate fallback-descriptor-scratch ran the production DescriptorSetUpdater with the policy off and
on and found the same semantic digest and resource trace (docs/evidence/melonx-631-gates); the policy only avoids the
exception and its descriptor-by-descriptor rewrite. Not measured on an iPhone; no FPS gain claimed. Fail closed on drift:
Library.cs must be the Core 639 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/Library.cs': 'db8e5c87d2f0e3f32ede4459aa7e843fe96434e475c57e5fa836eaf6becde106',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    library = paths['src/Ryujinx.Library/Library.cs']
    once(library, '''            // Descriptor encoding: template scratch sized by binding, texture arrays written by changed range.
            Ryujinx.Graphics.Vulkan.EncodingPolicy.BindingSizedDescriptorScratch = hogwarts;
''', '''            // Descriptor encoding: template scratch sized by binding (every title: without it a fragment texture or a buffer
            // texture throws and the set is rewritten one descriptor at a time; adapt_descriptor_scratch_all_titles),
            // texture arrays written by changed range (Hogwarts Legacy).
            Ryujinx.Graphics.Vulkan.EncodingPolicy.BindingSizedDescriptorScratch = true;
''')
    return list(paths.values())
