# RewindBox — private test IPA597

Status: preparation; no successful IPA or device result is claimed yet.

The maintainer requested the latest compiled RPCS3 Core in a new IPA.
Application baseline: delivered596, source
`d5c5f107f7b514980033d1b95218aa9d2f640609`, run40968162236.
The five unaffected application product roots stay identical. The sole native
host delta is `native/neoswap-storage/Store.cpp`, SHA256
`87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46`.

RPCS3 is reused from successful run40981514937, source
`88cdc5e3e115a0b8587711d77147467baf38128b`, artifact12946200694.
It retains ABI30, 88 exports and PPU/SPU codegen identities. Its existing Apple
continuation receipts keep their original execution and reuse scope.
MeloNX Core87 remains the exact artifact12931177865 from source07f35048 and
run40949501203, already authenticated in delivered596.

The new workflow derives directly from the successful596 assembly. It performs
one application compilation and verifies the signed IPA, original engine payload
preservation, licenses and application/extension versions. It does not compile
either engine or rerun unchanged native test suites. Unchanged retained
components preserve the established hashes and source pins. Output is encrypted
for private delivery; there is no public release or tag.

The established installation target remains iOS18 ARM64, with SideStore
re-signing. Compilation and static verification do not establish iPhone gameplay,
FPS gains or fixes for previously reported rendering/freezing scenes.
