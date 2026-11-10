"""Capture scalar threaded array bindings without allocating a snapshot array.

A one-element array has only one reference to capture. Put that reference in
the same FIFO reference table used by normal snapshots, and resolve its Base on
the consumer as before. A lazily allocated length-one array is borrowed only
during the synchronous backend call. Its slot is detached during that call so
even nested command consumption gets independent scratch. Clear it on success
or exception, then retain at most one empty array per resource/category.

Empty and multi-element arrays keep the existing owned-snapshot path. Vulkan
TextureArray/ImageArray consume array elements synchronously; neither retains
the caller's array. No backend state, barriers or descriptor flags change.
"""
import hashlib
from adapt_session import once


# The borrowed array contract relies on these complete, reviewed backend
# postimages consuming every element before returning, without retaining the
# caller's array. A future backend edit needs that contract reviewed again.
BACKEND_INPUTS = {
    'src/Ryujinx.Graphics.Vulkan/TextureArray.cs': '0bed44e171184a7d641e04d0a7e5542b5d7cdf7cf400cb44867ccf0509f5fd86',
    'src/Ryujinx.Graphics.Vulkan/ImageArray.cs': 'cf238484e0218aaf4082271bd328187fac89014313b2ec63609580de47799515',
    'src/Ryujinx.Graphics.OpenGL/Image/TextureArray.cs': 'bd3d4b5fdaa73fdbe0cf6b97031ebc4bb68bfc21bbc452df1a6f363e6e489526',
    'src/Ryujinx.Graphics.OpenGL/Image/ImageArray.cs': 'c9f2fd0d19ea1f4e49ee5700135dca3d2ef6ea764cdc74891280e6e45a6217b8',
}


def apply(source):
    for relative, digest in BACKEND_INPUTS.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest, relative
    root = source / 'src/Ryujinx.Graphics.GAL/Multithreading'
    changed = []
    for owner, category, plural, element, wrapper, comment in (
        ('ThreadedTextureArray', 'TextureArray', 'Textures', 'ITexture', 'ThreadedTexture',
         'Capture before reserving command/table slots; a failed copy owns no queue state.'),
        ('ThreadedTextureArray', 'TextureArray', 'Samplers', 'ISampler', 'ThreadedSampler',
         'Capture before reserving command/table slots; a failed copy owns no queue state.'),
        ('ThreadedImageArray', 'ImageArray', 'Images', 'ITexture', 'ThreadedTexture',
         'The caller may reuse its array as soon as this method returns.'),
    ):
        values = plural.lower()
        variable = category[0].lower() + category[1:]
        scratch = 'Single' + plural + 'Scratch'
        resource = root / f'Resources/{owner}.cs'
        command = root / f'Commands/{category}/{category}Set{plural}Command.cs'
        command_type = f'{category}Set{plural}Command'
        once(resource, f'        public I{category} Base;\n',
             f'        internal {element}[] {scratch};\n        public I{category} Base;\n')
        old = f'''            // {comment}
            {element}[] snapshot = {values}.ToArray();
            _renderer.New<{command_type}>()->Set(Ref(this), index, Ref(snapshot));
            _renderer.QueueCommand();'''
        new = f'''            if ({values} != null && {values}.Length == 1)
            {{
                // Capture the value before reserving queue state; the caller can
                // immediately reuse its one-element array after this method.
                {element} value = {values}[0];
                _renderer.New<{command_type}>()->SetSingle(Ref(this), index, Ref(value));
                _renderer.QueueCommand();
                return;
            }}

{old}'''
        once(resource, old, new)
        once(command, f'        private TableRef<{element}[]> _{values};\n',
             f'''        private TableRef<{element}[]> _{values};
        private TableRef<{element}> _value;
        private bool _single;
''')
        once(command, f'''            _{values} = {values};
        }}''', f'''            _{values} = {values};
            _single = false;
        }}

        public void SetSingle(TableRef<{owner}> {variable}, int index, TableRef<{element}> value)
        {{
            _{variable} = {variable};
            _index = index;
            _value = value;
            _single = true;
        }}''')
        needle = f'''            {owner} {variable} = command._{variable}.Get(threaded);
'''
        once(command, needle, needle + f'''            if (command._single)
            {{
                {element} value = command._value.Get(threaded);
                {element}[] single = {variable}.{scratch} ?? new {element}[1];
                // The slot is borrowed, not shared, while the backend runs.
                {variable}.{scratch} = null;

                try
                {{
                    single[0] = (({wrapper})value)?.Base;
                    {variable}.Base.Set{plural}(command._index, single);
                }}
                finally
                {{
                    single[0] = null;
                    {variable}.{scratch} ??= single;
                }}

                return;
            }}

''')
        if resource not in changed:
            changed.append(resource)
        changed.append(command)
    return changed
