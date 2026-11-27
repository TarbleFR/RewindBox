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

    # WiiConnect24 uses libcurl directly, bypassing IOS IP and WiiSockMan.
    path = root / 'Source/Core/Core/IOS/Network/KD/NetKDRequest.cpp'
    text = path.read_text()
    if declaration not in text:
        text = declaration + text
    for signature, refusal in [
        ('void NetKDRequestDevice::SchedulerWorker(const SchedulerEvent event)', 'return;'),
        ('NWC24::ErrorCode NetKDRequestDevice::KDCheckMail(u32* mail_flag, u32* interval)', 'return NWC24::WC24_ERR_NETWORK;'),
        ('NWC24::ErrorCode NetKDRequestDevice::KDSendMail()', 'return NWC24::WC24_ERR_NETWORK;'),
        ('NWC24::ErrorCode NetKDRequestDevice::KDDownload(const u16 entry_index,\n                                                const std::optional<u8> subtask_id)', 'return NWC24::WC24_ERR_NETWORK;'),
        ('IPCReply NetKDRequestDevice::HandleRequestRegisterUserId(const IOS::HLE::IOCtlRequest& request)',
         '{ auto& memory = GetSystem().GetMemory(); memory.Write_U32(0, request.buffer_out + 4);\n'
         '    WriteReturnValue(memory, NWC24::WC24_ERR_NETWORK, request.buffer_out); return IPCReply{IPC_SUCCESS}; }'),
    ]:
        anchor = signature + '\n{'
        guarded = anchor + '\n#ifdef IPHONEOS\n  if (!neostation_dolphin_wiimmfi_network_allowed()) ' + refusal + '\n#endif'
        if guarded not in text:
            if text.count(anchor) != 1:
                raise SystemExit(f'Pinned WC24 entry changed: {signature}')
            text = text.replace(anchor, guarded, 1)
    path.write_text(text)


def patch_online_memory_and_identity(root: Path) -> None:
    # Upstream HTTP/IPC/OSReport messages can contain console credentials even
    # when PCAP/SSL dump options are off. Suspend upstream listeners online;
    # owned RewindBox JSON diagnostics do not pass through this logger.
    path = root / 'Source/Core/Common/Logging/LogManager.cpp'
    text = path.read_text()
    declaration = '''#ifdef IPHONEOS
// Weak for standalone iOS tools that link Common without the embedded bridge.
extern "C" bool neostation_dolphin_wiimmfi_network_allowed() __attribute__((weak_import));
#endif
'''
    if declaration not in text:
        text = declaration + text
    for signature, refusal in [
        ('bool LogManager::IsEnabled(LogType type, LogLevel level) const', 'return false;'),
        ('void LogManager::LogWithFullPath(LogLevel level, LogType type, const char* file, int line,\n                                 const char* message)', 'return;'),
    ]:
        anchor = signature + '\n{'
        guarded = anchor + '''
#ifdef IPHONEOS
  if (neostation_dolphin_wiimmfi_network_allowed &&
      neostation_dolphin_wiimmfi_network_allowed()) ''' + refusal + '\n#endif'
        if guarded not in text:
            if text.count(anchor) != 1:
                raise SystemExit(f'Pinned logger entry changed: {signature}')
            text = text.replace(anchor, guarded, 1)
    path.write_text(text)

    path = root / 'Source/Core/Core/PatchEngine.cpp'
    text = path.read_text()
    declaration = '#ifdef IPHONEOS\nextern "C" bool neostation_dolphin_wiimmfi_network_allowed();\n#endif\n'
    if declaration not in text:
        text = declaration + text
    anchor = '  LoadPatchSection("OnFrame", &s_on_frame, globalIni, localIni);'
    replacement = '''  // Retain upstream compatibility defaults, not local memory modifications.
#ifdef IPHONEOS
  const Common::IniFile online_local;
  LoadPatchSection("OnFrame", &s_on_frame, globalIni,
                   neostation_dolphin_wiimmfi_network_allowed() ? online_local : localIni);
#else
  LoadPatchSection("OnFrame", &s_on_frame, globalIni, localIni);
#endif'''
    if replacement not in text:
        if text.count(anchor) != 1:
            raise SystemExit('Pinned OnFrame loader changed')
        text = text.replace(anchor, replacement, 1)
    path.write_text(text)

    # Never serialize the imported console's identifiers into RewindBox logs.
    for relative, old, new in [
        ('Source/Core/Core/Boot/Boot_BS2Emu.cpp',
         'INFO_LOG_FMT(BOOT, "No previous serial number found, generated one instead: {}", serno);',
         'INFO_LOG_FMT(BOOT, "No previous serial number found; value omitted");'),
        ('Source/Core/Core/Boot/Boot_BS2Emu.cpp',
         'INFO_LOG_FMT(BOOT, "Using serial number: {}", serno);',
         'INFO_LOG_FMT(BOOT, "Using existing console serial number; value omitted");'),
        ('Source/Core/Core/IOS/ES/Identity.cpp',
         'INFO_LOG_FMT(IOS_ES, "GetDeviceId: {:08X}", *device_id);',
         'INFO_LOG_FMT(IOS_ES, "GetDeviceId: console identifier omitted");'),
        ('Source/Core/Core/IOS/ES/TitleManagement.cpp',
         'WARN_LOG_FMT(IOS_ES, "Device ID mismatch: ticket {:08x}, device {:08x}", ticket_device_id,\n                   device_id);',
         'WARN_LOG_FMT(IOS_ES, "Device ID mismatch: console identifiers omitted");'),
    ]:
        path = root / relative
        text = path.read_text()
        replacement = '#ifdef IPHONEOS\n      ' + new + '\n#else\n      ' + old + '\n#endif'
        if replacement not in text:
            if text.count(old) != 1:
                raise SystemExit(f'Pinned identity log changed: {relative}')
            text = text.replace(old, replacement, 1)
        path.write_text(text)


def patch_wfc_session_diagnostics(root: Path) -> None:
    def insert(relative: str, anchor: str, replacement: str, count=1):
        path = root / 'Source/Core' / relative
        text = path.read_text()
        if replacement not in text:
            if text.count(anchor) != count:
                raise SystemExit(f'Pinned Wiimmfi diagnostic changed: {relative}: {anchor[:80]}')
            path.write_text(text.replace(anchor, replacement))

    def declaration(relative: str, anchor: str, signature: str):
        insert(relative, anchor, f'#ifdef IPHONEOS\nextern "C" {signature};\n#endif\n\n' + anchor)

    def observe(relative: str, anchor: str, expression: str, count=1):
        insert(relative, anchor, anchor + f'\n#ifdef IPHONEOS\n  neostation_dolphin_wiimmfi_observe({expression});\n#endif', count)

    # Keep the verified RewindBox NAND selected when Dolphin reloads paths from INIs.
    ui = 'UICommon/UICommon.cpp'
    declaration(ui, 'namespace UICommon\n{', 'bool neostation_dolphin_wiimmfi_network_allowed()')
    custom = '  File::SetUserPath(D_WIIROOT_IDX, Config::Get(Config::MAIN_FS_PATH));'
    insert(ui, custom, '''#ifdef IPHONEOS
  if (neostation_dolphin_wiimmfi_network_allowed())
    File::SetUserPath(D_WIIROOT_IDX, File::GetUserPath(D_USER_IDX) + "Wii/");
  else
#endif
  ''' + custom.lstrip())
    boot = 'Core/BootManager.cpp'
    declaration(boot, 'namespace BootManager\n{', 'bool neostation_dolphin_wiimmfi_validate_boot_nand(bool deterministic)')
    anchor = '  Core::UpdateWantDeterminism(system, /*initial*/ true);'
    insert(boot, anchor, anchor + '''

#ifdef IPHONEOS
  if (!neostation_dolphin_wiimmfi_validate_boot_nand(Core::WantsDeterminism()))
    return false;
#endif''')
    ios = 'Core/IOS/IOS.cpp'
    declaration(ios, 'namespace IOS::HLE\n{', 'void neostation_dolphin_wiimmfi_observe_ios_identity(bool personal)')
    anchor = '  INFO_LOG_FMT(IOS, "Starting IOS {:016x}", title_id);'
    insert(ios, anchor, anchor + '''
#ifdef IPHONEOS
  neostation_dolphin_wiimmfi_observe_ios_identity(!GetIOSC().IsUsingDefaultId());
#endif''')

    ssl = 'Core/IOS/Network/SSL.cpp'
    anchor = '\nstd::optional<IPCReply> NetSSLDevice::IOCtlV('
    insert(ssl, anchor, '''
#ifdef IPHONEOS
extern "C" bool neostation_dolphin_wiimmfi_tls_files_valid(const std::string& root)
{
  const auto valid = [&root](const char* name, const std::array<u8, 32>& expected) {
    File::IOFile file(root + "/" + name, "rb");
    const auto size = file.GetSize();
    if (size < 32 || size > 64 * 1024) return false;
    std::vector<u8> bytes(size);
    std::array<u8, 32> hash{};
    return file.ReadBytes(bytes.data(), bytes.size()) &&
           mbedtls_sha256_ret(bytes.data(), bytes.size(), hash.data(), 0) == 0 && hash == expected;
  };
  return valid("clientca.pem", s_client_cert_hash) &&
         valid("clientcakey.pem", s_client_key_hash) && valid("rootca.pem", s_root_ca_hash);
}
#endif
''' + anchor)

    top = 'Core/IOS/Network/IP/Top.cpp'
    sock = 'Core/IOS/Network/Socket.cpp'
    for relative in (top, sock):
        declaration(relative, 'namespace IOS::HLE\n{', 'void neostation_dolphin_wiimmfi_observe(s32 event)')
    observe(top, '  hostent* remoteHost = gethostbyname(hostname.c_str());',
            'remoteHost && remoteHost->h_addr_list && remoteHost->h_addr_list[0] ? 0 : 1', 2)
    observe(top, '  int ret = getaddrinfo(pNodeName, pServiceName, hints_valid ? &hints : nullptr, &result);',
            'ret == 0 && result ? 0 : 1')
    # Darwin requires output-only members of getaddrinfo hints to be zero.
    # Copy only the four input fields from the Wii request.
    insert(top, '  addrinfo hints;\n  const bool hints_valid = request.in_vectors.size() > 2 && request.in_vectors[2].size;',
           '  addrinfo hints{};\n  const bool hints_valid = request.in_vectors.size() > 2 && request.in_vectors[2].size >= 0x10;')
    insert(top, '    hints.ai_addrlen = memory.Read_U32(request.in_vectors[2].address + 0x10);\n'
           '    hints.ai_canonname = nullptr;',
           '    // Remaining members describe resolver output, not guest input.')
    # Darwin point-to-point VPN/cellular interfaces need not have a broadcast address.
    anchor = '    return reinterpret_cast<const sockaddr_in*>(addr)->sin_addr;'
    insert(top, anchor, '''#ifdef IPHONEOS
    if (!addr || addr->sa_family != AF_INET) return in_addr{};
#endif
''' + anchor)
    anchor = 'get_addr(iface->ifa_broadaddr), routing_table};'
    insert(top, anchor, '''
#ifdef IPHONEOS
                              (iface->ifa_flags & IFF_BROADCAST) ? get_addr(iface->ifa_broadaddr) : in_addr{},
                              routing_table};
#else
                              ''' + anchor + '\n#endif')
    insert(top, '#include <ifaddrs.h>', '#include <ifaddrs.h>\n#ifdef IPHONEOS\n#include <net/if.h>\n#endif')

    anchor = '  return AddSocket(fd, false);'
    insert(sock, anchor, '''  const auto result = AddSocket(fd, false);
#ifdef IPHONEOS
  neostation_dolphin_wiimmfi_observe(result >= 0 ? 2 : 3);
#endif
  return result;''')
    anchor = '  SetLastNetError(return_value);'
    insert(sock, anchor, anchor + '''
#ifdef IPHONEOS
  if (return_value == -SO_ETIMEDOUT)
    neostation_dolphin_wiimmfi_observe(7);
  else if (caller == "SO_CONNECT" && return_value != -SO_EAGAIN && return_value != -SO_EALREADY &&
           return_value != -SO_EINPROGRESS && return_value != -SO_EISCONN)
    neostation_dolphin_wiimmfi_observe(3);
#endif''')
    observe(sock, '            connecting_state = ConnectingState::Error;', '7')
    anchor = '            const int ret = mbedtls_ssl_handshake(ctx);'
    insert(sock, anchor, anchor + '''
#ifdef IPHONEOS
            if (ret != MBEDTLS_ERR_SSL_WANT_READ && ret != MBEDTLS_ERR_SSL_WANT_WRITE)
              neostation_dolphin_wiimmfi_observe(ret == 0 ? 4 : ret == MBEDTLS_ERR_X509_CERT_VERIFY_FAILED ? 5 : 6);
#endif''')


    # A physical Wii NAND can retain WLAN credentials, a fixed address or a
    # proxy. Dolphin reports LINK_WIRED and uses host sockets, so expose the
    # matching automatic wired profile to this online session only.
    config = 'Core/IOS/Network/NCD/WiiNetConfig.cpp'
    declaration(config, 'namespace IOS::HLE::Net\n{', 'bool neostation_dolphin_wiimmfi_network_allowed()')
    declaration(config, 'namespace IOS::HLE::Net\n{', 'void neostation_dolphin_wiimmfi_observe(s32 event)')
    # A guest config save or reset during the online session must not persist
    # the synthetic profile or remove the physical Wii's original settings.
    anchor = 'void WiiNetConfig::WriteConfig(FS::FileSystem* fs) const\n{'
    insert(config, anchor, anchor + '''
#ifdef IPHONEOS
  if (neostation_dolphin_wiimmfi_network_allowed()) return;
#endif''')
    anchor = 'void WiiNetConfig::ResetConfig(FS::FileSystem* fs)\n{'
    insert(config, anchor, anchor + '''
#ifdef IPHONEOS
  if (neostation_dolphin_wiimmfi_network_allowed())
  {
    m_data = {};
    return;
  }
#endif''')
    anchor = '  memory.CopyToEmu(address, &m_data, sizeof(m_data));'
    insert(config, anchor, '''#ifdef IPHONEOS
  if (neostation_dolphin_wiimmfi_network_allowed())
  {
    ConfigData session{};
    session.version = m_data.version;
    session.linkTimeout = m_data.linkTimeout;
    session.nwc24Permission = m_data.nwc24Permission;
    session.connType = ConfigData::IF_WIRED;
    session.connection[0].flags =
        ConnectionSettings::WIRED_IF | ConnectionSettings::DNS_DHCP | ConnectionSettings::IP_DHCP |
        ConnectionSettings::CONNECTION_TEST_OK | ConnectionSettings::CONNECTION_SELECTED;
    memory.CopyToEmu(address, &session, sizeof(session));
    neostation_dolphin_wiimmfi_observe(8);
    return;
  }
#endif
''' + anchor)


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
    s = change(s, '  IOS::ES::TMDReader tmd(std::move(tmd_bytes));', '''  IOS::ES::TMDReader tmd(std::move(tmd_bytes));
  // Header size alone does not bound the content table used by GetContent.
  if (!tmd.IsValid() || tmd.GetTitleId() != 0x000000010000000dULL) return false;''')
    s = change(s, '    PanicAlertFmtT("Unable to write to file {0}", file_path);', '    throw std::runtime_error("nand_write");')
    s = change(s, '    if (!pem_file.WriteBytes(&content_bytes[certificate_offset], certificate_size))',
               '    if (!pem_file.WriteBytes(&content_bytes[certificate_offset], certificate_size) || !pem_file.Flush())')
    s = change(s, '  if (!file.WriteBytes(m_nand_keys.data(), NAND_KEYS_SIZE))',
               '  if (!file.WriteBytes(m_nand_keys.data(), NAND_KEYS_SIZE) || !file.Flush())')
    # Publish only after every pinned-source match succeeded.
    header.write_text(h)
    source.write_text(s)
