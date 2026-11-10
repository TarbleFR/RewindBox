	stp	x29, x30, [sp, #-64]!           // 16-byte Folded Spill
	str	x23, [sp, #16]                  // 8-byte Spill
	stp	x22, x21, [sp, #32]             // 16-byte Folded Spill
	stp	x20, x19, [sp, #48]             // 16-byte Folded Spill
	mov	x29, sp
	ldrb	w8, [x0]
	cmp	w8, #1
	b.ne	.LBB5_14
	ldr	x21, [x1, #8]
	cmp	x21, #3
	b.hs	.LBB5_14
	cbz	x21, .LBB5_6
	cmp	w2, #1
	b.hi	.LBB5_12
	mov	w8, w2
	add	x8, x0, x8, lsl #5
	add	x22, x8, #32
	tbz	w4, #0, .LBB5_7
	str	wzr, [x22, #24]
	b	.LBB5_12
	mov	w0, #0                          // =0x0
	b	.LBB5_13
	ldr	w8, [x22, #24]
	lsl	x2, x21, #3
	cmp	x21, x8
	b.ne	.LBB5_10
	ldr	x8, [x22]
	ldr	x1, [x1]
	cmp	x8, x3
	b.ne	.LBB5_11
	add	x0, x22, #8
	mov	x19, x1
	mov	x20, x2
	mov	x23, x3
	bl	bcmp
	mov	x1, x19
	mov	x2, x20
	mov	x3, x23
	cbnz	w0, .LBB5_11
	b	.LBB5_13
	ldr	x1, [x1]
	str	x3, [x22]
	str	w21, [x22, #24]
	add	x0, x22, #8
	bl	memcpy
	mov	w0, #1                          // =0x1
	ldp	x20, x19, [sp, #48]             // 16-byte Folded Reload
	ldp	x22, x21, [sp, #32]             // 16-byte Folded Reload
	ldr	x23, [sp, #16]                  // 8-byte Reload
	ldp	x29, x30, [sp], #64             // 16-byte Folded Reload
	ret
	adrp	x0, .L.str.6
	add	x0, x0, :lo12:.L.str.6
	adrp	x1, .L.str.1
	add	x1, x1, :lo12:.L.str.1
	adrp	x3, .L__PRETTY_FUNCTION__._ZNK2vk14command_buffer31update_descriptor_binding_cacheERKNSt3__14spanImLm18446744073709551615EEE19VkPipelineBindPointmb
	add	x3, x3, :lo12:.L__PRETTY_FUNCTION__._ZNK2vk14command_buffer31update_descriptor_binding_cacheERKNSt3__14spanImLm18446744073709551615EEE19VkPipelineBindPointmb
	mov	w2, #398                        // =0x18e
	bl	__assert_fail
