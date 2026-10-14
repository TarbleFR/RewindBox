/*
MIT License

Copyright (c) 2020-2022 Rupert Carmichael

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

#ifndef VECX_PSG_H
#define VECX_PSG_H

typedef struct _psg_t {
    uint8_t reg[16]; // 16 Read/Write 8-bit registers
    uint8_t rlatch; // Register that is currently selected

    uint16_t tperiod[3]; // Periods for Tones A, B, and C
    uint16_t tcounter[3]; // Counters for Tones A, B, and C
    uint8_t amplitude[3]; // Amplitudes for Tones A, B, and C

    uint8_t nperiod; // Noise Period
    uint16_t ncounter; // Noise Counter
    uint32_t nshift; // Noise Random Number Generator Shift Register (17-bit)

    uint16_t eperiod; // Envelope Period
    uint16_t ecounter; // Envelope Counter
    uint8_t eseg; // Envelope Segment: Which half of the cycle
    uint8_t estep; // Envelope Step
    uint8_t evol; // Envelope Volume

    uint8_t tdisable[3]; // Disable bit for Tones A, B, and C
    uint8_t ndisable[3]; // Disable bit for Noise on Channels A, B, and C
    uint8_t emode[3]; // Envelope Mode Enable bit for Tones A, B, and C

    uint8_t sign[3]; // Signify whether the waveform is high or low
} psg_t;

void vecx_psg_set_buffer(int16_t*);
void vecx_psg_reset_buffer(void);
void vecx_psg_init(void);
uint8_t vecx_psg_rd(void);
void vecx_psg_wr(uint8_t data);
void vecx_psg_io_wr(uint8_t);
uint8_t vecx_psg_get_reg(void);
void vecx_psg_set_reg(uint8_t);
size_t vecx_psg_exec(void);

void vecx_psg_state_load(psg_t*);
void vecx_psg_state_save(psg_t*);

#endif
