"""Avoid rereading the same page-table entry while checking a contiguous GPU range.

MemoryManager.IsContiguous is called by buffer/texture span reads and range discovery.
The previous page's nextPte is this page's current PTE: retain it instead of doing
another page-table lookup. Mapped, unmapped, physical-memory and kind bits are still
compared exactly as before. No persistent cache or mapping invalidation changes.
"""
from adapt_session import once


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs'
    once(path, '''        private bool IsContiguous(ulong va, int size)
        {
            if (!ValidateAddress(va) || GetPte(va) == PteUnmapped)
            {
                return false;
            }
''', '''        private bool IsContiguous(ulong va, int size)
        {
            if (!ValidateAddress(va))
            {
                return false;
            }

            ulong currentPte = GetPte(va);

            if (currentPte == PteUnmapped)
            {
                return false;
            }
''')
    once(path, '''                if (GetPte(va) + PageSize != nextPte)
                {
                    return false;
                }

                va += PageSize;
''', '''                if (currentPte + PageSize != nextPte)
                {
                    return false;
                }

                currentPte = nextPte;
                va += PageSize;
''')
    return [path]
