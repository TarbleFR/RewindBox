	ldrb	w8, [x0]
	cmp	w8, #1
	b.ne	.LBB5_15
	ldr	x8, [x1, #8]
	cmp	x8, #3
	b.hs	.LBB5_15
	cbz	x8, .LBB5_12
	cmp	w2, #1
	b.ls	.LBB5_5
	mov	w0, #1                          // =0x1
	ret
	mov	w9, w2
	add	x9, x0, x9, lsl #5
	tbz	w4, #0, .LBB5_7
	stur	wzr, [x9, #56]
	mov	w0, #1                          // =0x1
	ret
	ldr	x10, [x1]
	ldr	x11, [x10]
	ldur	w12, [x9, #56]
	cmp	x8, x12
	b.ne	.LBB5_13
	ldur	x12, [x9, #32]
	cmp	x12, x3
	b.ne	.LBB5_13
	ldur	x12, [x9, #40]
	cmp	x12, x11
	b.ne	.LBB5_13
	cmp	x8, #1
	b.eq	.LBB5_12
	ldur	x12, [x9, #48]
	ldr	x13, [x10, #8]
	cmp	x12, x13
	b.ne	.LBB5_13
	mov	w0, #0                          // =0x0
	ret
	stur	w8, [x9, #56]
	stp	x3, x11, [x9, #32]
	ldr	x8, [x1, #8]
	cmp	x8, #2
	b.ne	.LBB5_4
	ldr	x8, [x10, #8]
	stur	x8, [x9, #48]
	mov	w0, #1                          // =0x1
	ret
	stp	x29, x30, [sp, #-16]!           // 16-byte Folded Spill
	mov	x29, sp
	adrp	x0, .L.str.6
	add	x0, x0, :lo12:.L.str.6
	adrp	x1, .L.str.1
	add	x1, x1, :lo12:.L.str.1
	adrp	x3, .L__PRETTY_FUNCTION__._ZNK2vk14command_buffer31update_descriptor_binding_cacheERKNSt3__14spanImLm18446744073709551615EEE19VkPipelineBindPointmb
	add	x3, x3, :lo12:.L__PRETTY_FUNCTION__._ZNK2vk14command_buffer31update_descriptor_binding_cacheERKNSt3__14spanImLm18446744073709551615EEE19VkPipelineBindPointmb
	mov	w2, #398                        // =0x18e
	bl	__assert_fail
