// RPCS3 526 production reference; upstream GPL-2.0-only and notices retained.
void PPUTranslator::VSUM4UBS(ppu_opcode_t op)
{
	const auto a = get_vr<u16[8]>(op.va);
	const auto b = get_vr<u32[4]>(op.vb);
	const auto x = eval(bitcast<u32[4]>((a & 0xff) + (a >> 8)));
	const auto s = eval((x & 0xffff) + (x >> 16));
	const auto r = add_sat(s, b);
	set_vr(op.vd, r);
	set_sat(r ^ (s + b));
}

void PPUTranslator::VSUM4SBS(ppu_opcode_t op)
{
	const auto a = get_vr<s16[8]>(op.va);
	const auto b = get_vr<s32[4]>(op.vb);
	const auto x = eval(bitcast<s32[4]>((a << 8 >> 8) + (a >> 8)));
	const auto s = eval((x << 16 >> 16) + (x >> 16));
	const auto r = add_sat(s, b);
	set_vr(op.vd, r);
	set_sat(r ^ (s + b));
}

void PPUTranslator::VSUM4SHS(ppu_opcode_t op)
{
	const auto a = get_vr<s32[4]>(op.va);
	const auto b = get_vr<s32[4]>(op.vb);
	const auto s = eval((a << 16 >> 16) + (a >> 16));
	const auto r = add_sat(s, b);
	set_vr(op.vd, r);
	set_sat(r ^ (s + b));
}
