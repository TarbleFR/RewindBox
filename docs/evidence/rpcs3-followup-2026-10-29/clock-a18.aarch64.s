	.build_version macos, 15, 0
	.section	__TEXT,__text,regular,pure_instructions
	.globl	__ZN6before18get_timebased_timeEv ; -- Begin function _ZN6before18get_timebased_timeEv
	.p2align	2
__ZN6before18get_timebased_timeEv:      ; @_ZN6before18get_timebased_timeEv
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #64
	.cfi_def_cfa_offset 64
	stp	x22, x21, [sp, #16]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #32]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #48]             ; 16-byte Folded Spill
	add	x29, sp, #48
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
	.cfi_remember_state
Lloh0:
	adrp	x8, __ZN5utils10s_tsc_freqE@GOTPAGE
Lloh1:
	ldr	x8, [x8, __ZN5utils10s_tsc_freqE@GOTPAGEOFF]
Lloh2:
	ldr	x8, [x8]
	cbz	x8, LBB0_3
; %bb.1:
	; InlineAsm Start
	mrs	x9, CNTVCT_EL0
	; InlineAsm End
	udiv	x10, x9, x8
	mov	w11, #46080                     ; =0xb400
	movk	w11, #1220, lsl #16
	msub	x9, x10, x8, x9
	mul	x9, x9, x11
	udiv	x8, x9, x8
	madd	x8, x10, x11, x8
Lloh3:
	adrp	x9, _g_cfg@GOTPAGE
Lloh4:
	ldr	x9, [x9, _g_cfg@GOTPAGEOFF]
Lloh5:
	ldr	x9, [x9]
	mul	x8, x8, x9
LBB0_2:
	lsr	x8, x8, #2
	mov	x9, #62915                      ; =0xf5c3
	movk	x9, #23592, lsl #16
	movk	x9, #49807, lsl #32
	movk	x9, #10485, lsl #48
	umulh	x8, x8, x9
	lsr	x8, x8, #2
Lloh6:
	adrp	x9, _g_timebase_offs@GOTPAGE
Lloh7:
	ldr	x9, [x9, _g_timebase_offs@GOTPAGEOFF]
Lloh8:
	ldr	x9, [x9]
	sub	x0, x8, x9
	.cfi_def_cfa wsp, 64
	ldp	x29, x30, [sp, #48]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #32]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #16]             ; 16-byte Folded Reload
	add	sp, sp, #64
	.cfi_def_cfa_offset 0
	.cfi_restore w30
	.cfi_restore w29
	.cfi_restore w19
	.cfi_restore w20
	.cfi_restore w21
	.cfi_restore w22
	ret
LBB0_3:
	.cfi_restore_state
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbnz	w0, LBB0_7
; %bb.4:
	mov	w19, #46080                     ; =0xb400
	movk	w19, #1220, lsl #16
	mov	x20, #23123                     ; =0x5a53
	movk	x20, #41115, lsl #16
	movk	x20, #47151, lsl #32
	movk	x20, #68, lsl #48
Lloh9:
	adrp	x21, _g_cfg@GOTPAGE
Lloh10:
	ldr	x21, [x21, _g_cfg@GOTPAGEOFF]
LBB0_5:                                 ; =>This Inner Loop Header: Depth=1
	ldp	x8, x9, [sp]
	mul	x8, x8, x19
	mul	x9, x9, x19
	lsr	x9, x9, #9
	umulh	x9, x9, x20
	add	x8, x8, x9, lsr #11
	ldr	x9, [x21]
	mul	x8, x8, x9
	cmp	x8, #100
	b.hs	LBB0_2
; %bb.6:                                ;   in Loop: Header=BB0_5 Depth=1
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbz	w0, LBB0_5
LBB0_7:
	brk	#0x1
	.loh AdrpLdrGotLdr	Lloh0, Lloh1, Lloh2
	.loh AdrpLdrGotLdr	Lloh3, Lloh4, Lloh5
	.loh AdrpLdrGotLdr	Lloh6, Lloh7, Lloh8
	.loh AdrpLdrGot	Lloh9, Lloh10
	.cfi_endproc
                                        ; -- End function
	.globl	__ZN6before15get_system_timeEv  ; -- Begin function _ZN6before15get_system_timeEv
	.p2align	2
__ZN6before15get_system_timeEv:         ; @_ZN6before15get_system_timeEv
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #48
	.cfi_def_cfa_offset 48
	stp	x20, x19, [sp, #16]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #32]             ; 16-byte Folded Spill
	add	x29, sp, #32
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_remember_state
	mov	w19, #16960                     ; =0x4240
	movk	w19, #15, lsl #16
Lloh11:
	adrp	x8, __ZN5utils10s_tsc_freqE@GOTPAGE
Lloh12:
	ldr	x8, [x8, __ZN5utils10s_tsc_freqE@GOTPAGEOFF]
Lloh13:
	ldr	x8, [x8]
	cbz	x8, LBB1_2
; %bb.1:
	; InlineAsm Start
	mrs	x9, CNTVCT_EL0
	; InlineAsm End
	udiv	x10, x9, x8
	msub	x9, x10, x8, x9
	mul	x9, x9, x19
	udiv	x8, x9, x8
	madd	x0, x10, x19, x8
	b	LBB1_5
LBB1_2:
	mov	x20, #63439                     ; =0xf7cf
	movk	x20, #58195, lsl #16
	movk	x20, #39845, lsl #32
	movk	x20, #8388, lsl #48
LBB1_3:                                 ; =>This Inner Loop Header: Depth=1
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbnz	w0, LBB1_6
; %bb.4:                                ;   in Loop: Header=BB1_3 Depth=1
	ldp	x8, x9, [sp]
	mul	x8, x8, x19
	lsr	x9, x9, #3
	umulh	x9, x9, x20
	adds	x0, x8, x9, lsr #4
	b.eq	LBB1_3
LBB1_5:
	.cfi_def_cfa wsp, 48
	ldp	x29, x30, [sp, #32]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #16]             ; 16-byte Folded Reload
	add	sp, sp, #48
	.cfi_def_cfa_offset 0
	.cfi_restore w30
	.cfi_restore w29
	.cfi_restore w19
	.cfi_restore w20
	ret
LBB1_6:
	.cfi_restore_state
	brk	#0x1
	.loh AdrpLdrGotLdr	Lloh11, Lloh12, Lloh13
	.cfi_endproc
                                        ; -- End function
	.globl	__ZN5after18get_timebased_timeEv ; -- Begin function _ZN5after18get_timebased_timeEv
	.p2align	2
__ZN5after18get_timebased_timeEv:       ; @_ZN5after18get_timebased_timeEv
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #64
	.cfi_def_cfa_offset 64
	stp	x22, x21, [sp, #16]             ; 16-byte Folded Spill
	stp	x20, x19, [sp, #32]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #48]             ; 16-byte Folded Spill
	add	x29, sp, #48
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_offset w21, -40
	.cfi_offset w22, -48
Lloh14:
	adrp	x8, __ZN5utils10s_tsc_freqE@GOTPAGE
Lloh15:
	ldr	x8, [x8, __ZN5utils10s_tsc_freqE@GOTPAGEOFF]
Lloh16:
	ldr	x9, [x8]
	cbz	x9, LBB2_3
; %bb.1:
	; InlineAsm Start
	mrs	x8, CNTVCT_EL0
	; InlineAsm End
	mov	w10, #51712                     ; =0xca00
	movk	w10, #15258, lsl #16
	cmp	x9, x10
	b.ne	LBB2_8
; %bb.2:
	; InlineAsm Start
	; InlineAsm End
	mov	x9, #44565                      ; =0xae15
	movk	x9, #57671, lsl #16
	movk	x9, #5242, lsl #32
	movk	x9, #18350, lsl #48
	umulh	x9, x8, x9
	sub	x10, x8, x9
	add	x9, x9, x10, lsr #1
	lsr	x9, x9, #4
	mov	w10, #25                        ; =0x19
	msub	x8, x9, x10, x8
	cmp	x8, #12
	cset	w8, hi
	orr	x8, x8, x9, lsl #1
Lloh17:
	adrp	x9, _g_cfg@GOTPAGE
Lloh18:
	ldr	x9, [x9, _g_cfg@GOTPAGEOFF]
Lloh19:
	ldr	x9, [x9]
	mul	x8, x9, x8
	b	LBB2_9
LBB2_3:
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbnz	w0, LBB2_7
; %bb.4:
	mov	w19, #46080                     ; =0xb400
	movk	w19, #1220, lsl #16
	mov	x20, #23123                     ; =0x5a53
	movk	x20, #41115, lsl #16
	movk	x20, #47151, lsl #32
	movk	x20, #68, lsl #48
Lloh20:
	adrp	x21, _g_cfg@GOTPAGE
Lloh21:
	ldr	x21, [x21, _g_cfg@GOTPAGEOFF]
LBB2_5:                                 ; =>This Inner Loop Header: Depth=1
	ldp	x8, x9, [sp]
	mul	x8, x8, x19
	mul	x9, x9, x19
	lsr	x9, x9, #9
	umulh	x9, x9, x20
	add	x8, x8, x9, lsr #11
	ldr	x9, [x21]
	mul	x8, x8, x9
	cmp	x8, #100
	b.hs	LBB2_9
; %bb.6:                                ;   in Loop: Header=BB2_5 Depth=1
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbz	w0, LBB2_5
LBB2_7:
	brk	#0x1
LBB2_8:
	udiv	x10, x8, x9
	mov	w11, #46080                     ; =0xb400
	movk	w11, #1220, lsl #16
	msub	x8, x10, x9, x8
	mul	x8, x8, x11
	udiv	x8, x8, x9
	madd	x8, x10, x11, x8
Lloh22:
	adrp	x9, _g_cfg@GOTPAGE
Lloh23:
	ldr	x9, [x9, _g_cfg@GOTPAGEOFF]
Lloh24:
	ldr	x9, [x9]
	mul	x8, x8, x9
LBB2_9:
	lsr	x8, x8, #2
	mov	x9, #62915                      ; =0xf5c3
	movk	x9, #23592, lsl #16
	movk	x9, #49807, lsl #32
	movk	x9, #10485, lsl #48
	umulh	x8, x8, x9
	lsr	x8, x8, #2
Lloh25:
	adrp	x9, _g_timebase_offs@GOTPAGE
Lloh26:
	ldr	x9, [x9, _g_timebase_offs@GOTPAGEOFF]
Lloh27:
	ldr	x9, [x9]
	sub	x0, x8, x9
	.cfi_def_cfa wsp, 64
	ldp	x29, x30, [sp, #48]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #32]             ; 16-byte Folded Reload
	ldp	x22, x21, [sp, #16]             ; 16-byte Folded Reload
	add	sp, sp, #64
	.cfi_def_cfa_offset 0
	.cfi_restore w30
	.cfi_restore w29
	.cfi_restore w19
	.cfi_restore w20
	.cfi_restore w21
	.cfi_restore w22
	ret
	.loh AdrpLdrGotLdr	Lloh14, Lloh15, Lloh16
	.loh AdrpLdrGotLdr	Lloh17, Lloh18, Lloh19
	.loh AdrpLdrGot	Lloh20, Lloh21
	.loh AdrpLdrGotLdr	Lloh22, Lloh23, Lloh24
	.loh AdrpLdrGotLdr	Lloh25, Lloh26, Lloh27
	.cfi_endproc
                                        ; -- End function
	.globl	__ZN5after15get_system_timeEv   ; -- Begin function _ZN5after15get_system_timeEv
	.p2align	2
__ZN5after15get_system_timeEv:          ; @_ZN5after15get_system_timeEv
	.cfi_startproc
; %bb.0:
	sub	sp, sp, #48
	.cfi_def_cfa_offset 48
	stp	x20, x19, [sp, #16]             ; 16-byte Folded Spill
	stp	x29, x30, [sp, #32]             ; 16-byte Folded Spill
	add	x29, sp, #32
	.cfi_def_cfa w29, 16
	.cfi_offset w30, -8
	.cfi_offset w29, -16
	.cfi_offset w19, -24
	.cfi_offset w20, -32
	.cfi_remember_state
Lloh28:
	adrp	x8, __ZN5utils10s_tsc_freqE@GOTPAGE
Lloh29:
	ldr	x8, [x8, __ZN5utils10s_tsc_freqE@GOTPAGEOFF]
Lloh30:
	ldr	x8, [x8]
	cbz	x8, LBB3_3
; %bb.1:
	; InlineAsm Start
	mrs	x9, CNTVCT_EL0
	; InlineAsm End
	mov	w10, #51712                     ; =0xca00
	movk	w10, #15258, lsl #16
	cmp	x8, x10
	b.ne	LBB3_6
; %bb.2:
	; InlineAsm Start
	; InlineAsm End
	lsr	x8, x9, #3
	mov	x9, #63439                      ; =0xf7cf
	movk	x9, #58195, lsl #16
	movk	x9, #39845, lsl #32
	movk	x9, #8388, lsl #48
	umulh	x8, x8, x9
	lsr	x0, x8, #4
	b	LBB3_7
LBB3_3:
	mov	w19, #16960                     ; =0x4240
	movk	w19, #15, lsl #16
	mov	x20, #63439                     ; =0xf7cf
	movk	x20, #58195, lsl #16
	movk	x20, #39845, lsl #32
	movk	x20, #8388, lsl #48
LBB3_4:                                 ; =>This Inner Loop Header: Depth=1
	mov	x1, sp
	mov	w0, #1                          ; =0x1
	bl	_clock_gettime
	cbnz	w0, LBB3_8
; %bb.5:                                ;   in Loop: Header=BB3_4 Depth=1
	ldp	x8, x9, [sp]
	mul	x8, x8, x19
	lsr	x9, x9, #3
	umulh	x9, x9, x20
	adds	x0, x8, x9, lsr #4
	b.eq	LBB3_4
	b	LBB3_7
LBB3_6:
	udiv	x10, x9, x8
	mov	w11, #16960                     ; =0x4240
	movk	w11, #15, lsl #16
	msub	x9, x10, x8, x9
	mul	x9, x9, x11
	udiv	x8, x9, x8
	madd	x0, x10, x11, x8
LBB3_7:
	.cfi_def_cfa wsp, 48
	ldp	x29, x30, [sp, #32]             ; 16-byte Folded Reload
	ldp	x20, x19, [sp, #16]             ; 16-byte Folded Reload
	add	sp, sp, #48
	.cfi_def_cfa_offset 0
	.cfi_restore w30
	.cfi_restore w29
	.cfi_restore w19
	.cfi_restore w20
	ret
LBB3_8:
	.cfi_restore_state
	brk	#0x1
	.loh AdrpLdrGotLdr	Lloh28, Lloh29, Lloh30
	.cfi_endproc
                                        ; -- End function
.subsections_via_symbols
