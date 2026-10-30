"""Return guest-sized packed depth readbacks; preserve full thin mip blits."""
import hashlib,json
from pathlib import Path

def edits(source):
 out={};p=source/'src/Ryujinx.Graphics.Vulkan/TextureView.cs';s=p.read_text(encoding='utf-8-sig')
 old='''            int size = width * height * Info.BytesPerPixel;
            using BufferHolder bufferHolder = _gd.BufferManager.Create(_gd, size);'''
 new='''            int guestSize = checked(width * height * Info.BytesPerPixel);
            int size = GetBufferDataLength(guestSize);
            using BufferHolder bufferHolder = _gd.BufferManager.Create(_gd, size);'''
 if s.count(old)!=1:raise RuntimeError('Depth rectangle readback drift')
 s=s.replace(old,new);old='            byte[] bitmap = new byte[size];';new='            byte[] bitmap = new byte[guestSize];'
 if s.count(old)!=1:raise RuntimeError('Depth bitmap size drift')
 s=s.replace(old,new)
 old='''                if (output.IsEmpty)
                {
                    output = new byte[GetBufferDataLength(size)];
                }

                FormatConverter.ConvertD32FS8ToD24S8(output, storage);
                return output;
            }

            return storage;'''
 new='''                // size is the D32FS8 host byte count (8 bytes/texel).
                // The guest receives packed D24S8 (4), never the stale tail
                // of the reusable host flush buffer. In-place packing is safe:
                // each output word precedes the next two unread host words.
                if ((size & 7) != 0 || size < 0 || storage.Length < size)
                    throw new ArgumentException("Invalid D32FS8 readback length.");
                int guestSize = size / 2;
                output = output.IsEmpty ? new byte[guestSize] : output[..guestSize];
                FormatConverter.ConvertD32FS8ToD24S8(output, storage[..size]);
                return output;
            }

            return storage[..size];'''
 if s.count(old)!=1:raise RuntimeError('Depth readback formatter drift')
 out[p]=s.replace(old,new)
 p=source/'src/Ryujinx.Graphics.Vulkan/TextureCopy.cs';s=p.read_text(encoding='utf-8-sig')
 old='''                static int Clamp(int value, int max)
                {
                    return Math.Clamp(value, 0, max);
                }

                Offset3D xy1 = new(Clamp(extents.X1, width) >> level, Clamp(extents.Y1, height) >> level, 0);
                Offset3D xy2 = new(Clamp(extents.X2, width) >> level, Clamp(extents.Y2, height) >> level, 1);'''
 new='''                static int ScaleEndpoint(int value, int max, int level)
                {
                    int clamped = Math.Clamp(value, 0, max);
                    // A complete mip dimension never falls below one texel.
                    // Preserve both orientations, including flipped blits;
                    // interior/cropped coordinates retain integer rounding.
                    return clamped == max ? Math.Max(1, max >> level) : clamped >> level;
                }

                Offset3D xy1 = new(ScaleEndpoint(extents.X1, width, level), ScaleEndpoint(extents.Y1, height, level), 0);
                Offset3D xy2 = new(ScaleEndpoint(extents.X2, width, level), ScaleEndpoint(extents.Y2, height, level), 1);'''
 if s.count(old)!=1:raise RuntimeError('Mip blit endpoints drift')
 out[p]=s.replace(old,new);return out

def apply(source):
 c=json.loads(Path(__file__).with_name('texture-readback-bounds-contract.json').read_text());before={p:hashlib.sha256((source/p).read_bytes()).hexdigest()for p in c['before']}
 if before==c['after']:return[source/p for p in before]
 if before!=c['before']:raise RuntimeError('Texture readback preimage drift')
 out=edits(source)
 if {str(p.relative_to(source)):hashlib.sha256(s.encode()).hexdigest()for p,s in out.items()}!=c['after']:raise RuntimeError('Texture readback postimage drift')
 for p,s in out.items():p.write_text(s)
 return list(out)
