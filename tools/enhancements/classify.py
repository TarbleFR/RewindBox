"""Category rules shared by the enhancement catalogue builder and its tests.

A category is decided from the author's own label only. It never claims an
effect was measured: it routes an entry to the tab a player looks in.
"""
import re

CATEGORIES = ('cheat', 'fps', 'ultrawide', 'graphics', 'performance')

# Labels that change the game's speed instead of its frame rate stay cheats.
_SPEED = re.compile(r'\b(turbo|speed ?up|fast ?forward|x ?[2-9] speed|game ?speed|slow ?motion|slowmo)\b', re.I)
_FPS = re.compile(
    r'(\b\d{2,3} ?fps\b|\bfps\b|frame ?rate|framerate|\b(50|60|120) ?hz\b|50/60|\bvsync\b|frame ?skip|'
    r'frameskip|frame ?pacing|unlock(ed)? ?frame)', re.I)
_ULTRAWIDE = re.compile(
    r'(\b(16|21|32|15|20|18) ?: ?(9|10)\b|ultra ?wide|wide ?screen|aspect|\bfov\b|field of view|black ?bars?|'
    r'pillarbox|letterbox|\bhor\+|anamorphic|\bvert\-)', re.I)
_PERFORMANCE = re.compile(
    r'(speed ?hack|speedhack|performance|\bperf\b|optimi[sz]|reduce(d)? (input )?lag|input lag|lag fix|stutter|'
    r'\bcpu\b|\bgpu (usage|load)|culling|less (draw|load)|skip (heavy|unneeded))', re.I)
_GRAPHICS = re.compile(
    r'(resolution|\b\d{3,4}p\b|\b[248]k\b|progressive|interlac|\bblur|bloom|\bdof\b|depth of field|'
    r'anti.?alias|\b(ml|fx|sm|ta|ms)aa\b|\b(ms)?aa ?[x2-8]|\blod\b|draw distance|view distance|film grain|'
    r'\bssa[o0]\b|ambient occlusion|ghosting|brightness|\bgfx\b|graphic|\b(no|hide|disable|remove) ?hud\b|'
    r'\bhud (off|on|removal)|dither|scanline|post.?process|lens flare|chromatic|\bchrom ab\b|vignette|'
    r'tone ?mapp|exposure|sharpen|texture filter|anisotropic|'
    r'\b(fog|shadows?|lighting|foliage|distortion)( effects?)? (off|on|disable|removal|remover|quality)|'
    r'\b(no|disable|remove) (fog|shadows?|lighting|foliage))', re.I)


def classify(name, default='cheat'):
    """Return the category of an author label; `default` covers the rest."""
    label = name or ''
    if _SPEED.search(label):
        return 'cheat'
    if _FPS.search(label):
        return 'fps'
    if _ULTRAWIDE.search(label):
        return 'ultrawide'
    if _PERFORMANCE.search(label):
        return 'performance'
    if _GRAPHICS.search(label):
        return 'graphics'
    return default
