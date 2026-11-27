"""Bound the pinned BootMii reader before exposing it to the iOS file picker.

SPDX-License-Identifier: GPL-2.0-or-later
This does not implement ECC/HMAC authentication or any Nintendo WFC protocol.
"""
from pathlib import Path


def patch_wfc_offline_gate(root: Path) -> None:
    """An offline launch of a player-patched image must not reach WFC.

    Gate IOS IP ioctls before DNS/async dispatch and socket creation itself.
    All gates are iPhone-only, fail closed, and belong to this Core session.
    """
    declaration = '#ifdef IPHONEOS\nextern "C" bool neostation_dolphin_wiimmfi_network_allowed();\n#endif\n'
    for relative, signatures, refusal in [
        ('Source/Core/Core/IOS/Network/IP/Top.cpp', [
            'std::optional<IPCReply> NetIPTopDevice::IOCtl(const IOCtlRequest& request)',
            'std::optional<IPCReply> NetIPTopDevice::IOCtlV(const IOCtlVRequest& request)',
        ], 'return IPCReply(-SO_ENETUNREACH);'),
        ('Source/Core/Core/IOS/Network/Socket.cpp', [
            's32 WiiSockMan::NewSocket(s32 af, s32 type, s32 protocol)',
        ], 'return -SO_ENETUNREACH;'),
    ]:
        path = root / relative
        text = path.read_text()
        if declaration not in text:
            text = declaration + text
        for signature in signatures:
            anchor = signature + '\n{'
            guarded = anchor + '\n#ifdef IPHONEOS\n  if (!neostation_dolphin_wiimmfi_network_allowed()) ' + refusal + '\n#endif'
            if guarded in text:
                continue
            if text.count(anchor) != 1:
                raise SystemExit(f'Pinned WFC socket entry changed: {signature}')
            text = text.replace(anchor, guarded, 1)
        path.write_text(text)


def patch_nand_importer(root: Path) -> None:
    header = root / 'Source/Core/DiscIO/NANDImporter.h'
    source = root / 'Source/Core/DiscIO/NANDImporter.cpp'
    cmake = root / 'Source/Core/DiscIO/CMakeLists.txt'
    flag = '\n# Bounded BootMii cancellation/errors must unwind to the owned C ABI.\nset_source_files_properties(NANDImporter.cpp PROPERTIES COMPILE_OPTIONS "-fexceptions")\n'
    if flag not in cmake.read_text():
        cmake.write_text(cmake.read_text() + flag)
    if 'RewindBox bounded BootMii import' in source.read_text():
        return

    def change(text: str, old: str, new: str) -> str:
        if text.count(old) != 1:
            raise SystemExit(f'Pinned BootMii source changed: {old[:90]}')
        return text.replace(old, new, 1)

    h = header.read_text()
    h = change(h, '#include <vector>', '#include <vector>\n#include <utility>')
    h = change(h, '  NANDImporter();', '''  NANDImporter();
  explicit NANDImporter(std::string root) : m_nand_root(std::move(root)) {}
  // Percentage of the current phase, from completed pages or reachable entries.
  int GetProgress() const { return m_progress; }
  bool IsExtracting() const { return m_extracting; }
  bool Succeeded() const { return m_succeeded; }''')
    h = change(h, '  std::string m_nand_root;', '''  void ValidateEntries(u16 index, const std::string& parent, size_t depth);
  std::array<bool, 0x17ff> m_seen{};
  std::array<bool, 0x8000> m_clusters{};
  size_t m_entry_count = 0;
  size_t m_entries_done = 0;
  size_t m_extracted_bytes = 0;
  int m_progress = 0;
  bool m_extracting = false;
  bool m_succeeded = false;
  std::string m_nand_root;''')
    s = source.read_text()
    s = change(s, '#include <cstring>', '#include <cstring>\n#include <stdexcept>\n#include <set>\n#include <cctype>\n// RewindBox bounded BootMii import')
    s = change(s, '  ExportKeys();\n  ProcessEntry(0, "");\n  ExtractCertificates();', '''  ValidateEntries(0, "", 0);
  m_extracting = true;
  m_progress = 0;
  m_update_callback();
  ExportKeys();
  ProcessEntry(0, "");
  if (!ExtractCertificates()) throw std::runtime_error("nand_certificates");
  m_progress = 100;
  m_update_callback();
  m_succeeded = true;''')
    s = change(s, '      m_update_callback();', '''    {
      m_progress = static_cast<int>(i * 100 / NAND_TOTAL_BLOCKS);
      m_update_callback();
    }''')
    s = change(s, '    file.ReadBytes(&m_nand[i * NAND_BLOCK_SIZE], NAND_BLOCK_SIZE);', '''    if (!file.ReadBytes(&m_nand[i * NAND_BLOCK_SIZE], NAND_BLOCK_SIZE))
      throw std::runtime_error("nand_read");''')
    s = change(s, '    file.Seek(NAND_ECC_BLOCK_SIZE, File::SeekOrigin::Current);', '''    if (!file.Seek(NAND_ECC_BLOCK_SIZE, File::SeekOrigin::Current))
      throw std::runtime_error("nand_read");''')
    s = change(s, "  if (name.front() == '/' || parent_path.back() == '/')", "  if (name == \"/\" || (!parent_path.empty() && parent_path.back() == '/'))")
    marker = 'void NANDImporter::ProcessEntry(u16 entry_number, const std::string& parent_path)'
    validator = '''// Validate the complete reachable filesystem before creating a single file.
void NANDImporter::ValidateEntries(u16 index, const std::string& parent, size_t depth)
{
  if (depth > 64) throw std::runtime_error("nand_depth");
  std::set<std::string> names;
  while (index != 0xffff)
  {
    m_update_callback(); // Also permits bounded cancellation during validation.
    if (index >= m_superblock->fst.size() || m_seen[index])
      throw std::runtime_error("nand_fst_cycle");
    m_seen[index] = true;
    ++m_entry_count;
    const auto& entry = m_superblock->fst[index];
    const std::string name(entry.name, strnlen(entry.name, sizeof(entry.name)));
    const bool root = index == 0 && parent.empty();
    std::string folded = name;
    std::transform(folded.begin(), folded.end(), folded.begin(), [](unsigned char c) {
      return static_cast<char>(std::tolower(c));
    });
    if ((root && (name != "/" || (entry.mode & 3) != 2 || entry.sib != 0xffff)) ||
        (!root && (name.empty() || name == "." || name == ".." ||
          name.find_first_of("/\\\\:") != std::string::npos)) || !names.insert(folded).second)
      throw std::runtime_error("nand_path");
    const auto path = GetPath(entry, parent);
    if ((entry.mode & 3) == 2)
      ValidateEntries(entry.sub, path, depth + 1);
    else if ((entry.mode & 3) == 1)
    {
      const size_t size = entry.size;
      if (size > 0x20000000 || m_extracted_bytes > 0x20000000 - size)
        throw std::runtime_error("nand_size");
      m_extracted_bytes += size;
      u16 cluster = entry.sub;
      size_t remaining = size;
      while (remaining)
      {
        if (cluster >= 0x7f00 || m_clusters[cluster])
          throw std::runtime_error("nand_fat_cycle");
        m_clusters[cluster] = true;
        remaining -= std::min(remaining, size_t{0x4000});
        cluster = m_superblock->fat[cluster];
      }
    }
    else throw std::runtime_error("nand_type");
    index = entry.sib;
  }
}

'''
    s = change(s, marker, validator + marker)
    s = change(s, '    INFO_LOG_FMT(DISCIO, "Entry: {} Path: {}", entry, path);', '''    // Never put console-owned paths or credentials in a host log.
    m_progress = static_cast<int>(m_entries_done++ * 100 / m_entry_count);''')
    s = change(s, '      file.WriteBytes(data.data(), data.size());', '''      if (!file.WriteBytes(data.data(), data.size()) || !file.Flush())
        throw std::runtime_error("nand_write");''')
    s = change(s, '      File::CreateDir(m_nand_root + path);', '''      if (!File::CreateDir(m_nand_root + path) && !File::IsDirectory(m_nand_root + path))
        throw std::runtime_error("nand_write");''')
    s = change(s, '  std::vector<u8> tmd_bytes(tmd_file.GetSize());', '''  if (tmd_file.GetSize() < 0x1e4 || tmd_file.GetSize() > 0x49e4) return false;
  std::vector<u8> tmd_bytes(tmd_file.GetSize());''')
    s = change(s, '  std::vector<u8> content_bytes(content_file.GetSize());', '''  if (content_file.GetSize() == 0 || content_file.GetSize() > 64 * 1024 * 1024) return false;
  std::vector<u8> content_bytes(content_file.GetSize());''')
    s = change(s, '    PanicAlertFmtT("Unable to write to file {0}", file_path);', '    throw std::runtime_error("nand_write");')
    s = change(s, '    if (!pem_file.WriteBytes(&content_bytes[certificate_offset], certificate_size))',
               '    if (!pem_file.WriteBytes(&content_bytes[certificate_offset], certificate_size) || !pem_file.Flush())')
    s = change(s, '  if (!file.WriteBytes(m_nand_keys.data(), NAND_KEYS_SIZE))',
               '  if (!file.WriteBytes(m_nand_keys.data(), NAND_KEYS_SIZE) || !file.Flush())')
    # Publish only after every pinned-source match succeeded.
    header.write_text(h)
    source.write_text(s)
