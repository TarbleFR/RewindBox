// RPCS3 525 production reference: PPUTranslator.cpp, XITRIX base 22f1152 + RewindBox canonical delta.
// Upstream RPCS3 copyright and GPL-2.0-only retained; see native source COPYING.
void PPUTranslator::VMSUMUBM(ppu_opcode_t op)
{
	const auto [a, b] = get_vrs<u16[8]>(op.va, op.vb);
	const auto c = get_vr<u32[4]>(op.vc);
	const auto ml = bitcast<u32[4]>((a << 8 >> 8) * (b << 8 >> 8));
	const auto mh = bitcast<u32[4]>((a >> 8) * (b >> 8));
	set_vr(op.vd, eval(((ml << 16 >> 16) + (ml >> 16)) + ((mh << 16 >> 16) + (mh >> 16)) + c));
}

void PPUTranslator::VMSUMMBM(ppu_opcode_t op)
{
	const auto a = get_vr<s16[8]>(op.va);
	const auto b = get_vr<u16[8]>(op.vb);
	const auto c = get_vr<s32[4]>(op.vc);
	const auto ml = bitcast<s32[4]>((a << 8 >> 8) * noncast<s16[8]>(b << 8 >> 8));
	const auto mh = bitcast<s32[4]>((a >> 8) * noncast<s16[8]>(b >> 8));
	set_vr(op.vd, ((ml << 16 >> 16) + (ml >> 16)) + ((mh << 16 >> 16) + (mh >> 16)) + c);
}

void PPUTranslator::VMSUMUHM(ppu_opcode_t op)
{
	const auto [a, b, c] = get_vrs<u32[4]>(op.va, op.vb, op.vc);
	const auto ml = (a << 16 >> 16) * (b << 16 >> 16);
	const auto mh = (a >> 16) * (b >> 16);
	set_vr(op.vd, ml + mh + c);
}

void PPUTranslator::VMSUMSHM(ppu_opcode_t op)
{
	const auto [a, b, c] = get_vrs<s32[4]>(op.va, op.vb, op.vc);
	const auto ml = (a << 16 >> 16) * (b << 16 >> 16);
	const auto mh = (a >> 16) * (b >> 16);
	set_vr(op.vd, ml + mh + c);
}
