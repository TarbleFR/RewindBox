// Host driver for NeoTextureIdentity: prints the identity read from a file.
#include "NeoTextureIdentity.h"
#include <cstdio>
int main(int argc, char** argv) {
  if (argc != 3) return 64;
  const std::string kind = argv[1], path = argv[2];
  NeoTextureIdentity::Result r;
  if (kind == "ps2") r = NeoTextureIdentity::PS2(path);
  else if (kind == "gc" || kind == "wii") r = NeoTextureIdentity::Dolphin(path, kind);
  else if (kind == "psp") r = NeoTextureIdentity::PSP(path);
  else if (kind == "3ds") r = NeoTextureIdentity::N3DS(path);
  else if (kind == "n64") r = NeoTextureIdentity::N64(path);
  else if (kind == "ps1") r = NeoTextureIdentity::PS1(path);
  else return 64;
  std::string folder = r.folder;  // an N64 ROM name has spaces: printed as "+" (one field per word)
  for (char& c : folder) if (c == ' ') c = '+';
  std::printf("value=%s folder=%s revision=%s crc=%s region=%s format=%s problem=%s\n", r.value.c_str(), folder.c_str(),
              r.revision.c_str(), r.crc.c_str(), r.region.c_str(), r.format.c_str(), r.problem.c_str());
  return r.ok() ? 0 : 1;
}
