#if RANGE_PROBE
using System.Collections;
using System.Collections.Generic;

static class RangeBookkeepingProbe
{
    public static long ShiftedElements, Replacements, Removals, Inserts, Searches;
    public static void Reset() => ShiftedElements = Replacements = Removals = Inserts = Searches = 0;
}

sealed class TrackedRangeList<T> : IEnumerable<T>
{
    readonly List<T> _items = new();
    public int Count => _items.Count;
    public T this[int index]
    {
        get => _items[index];
        set { RangeBookkeepingProbe.Replacements++; _items[index] = value; }
    }
    public void Add(T value) => _items.Add(value);
    public void Insert(int index, T value)
    {
        RangeBookkeepingProbe.ShiftedElements += _items.Count - index;
        RangeBookkeepingProbe.Inserts++; _items.Insert(index, value);
    }
    public void RemoveAt(int index)
    {
        RangeBookkeepingProbe.ShiftedElements += _items.Count - index - 1;
        RangeBookkeepingProbe.Removals++; _items.RemoveAt(index);
    }
    public int BinarySearch(T value) { RangeBookkeepingProbe.Searches++; return _items.BinarySearch(value); }
    public IEnumerator<T> GetEnumerator() => _items.GetEnumerator();
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
#endif
