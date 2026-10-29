void partial_packets() {
    constexpr std::array<u32, 12> lengths{1, 2, 3, 7, 31, 32, 33, 127, 255, 511, 1023, 2047};
    for (auto mode : {rsx_fifo_mode::atomic, rsx_fifo_mode::atomic_ordered, rsx_fifo_mode::as_ps3})
    for (u32 bytes : {1024u, 4096u}) for (bool deferred : {false, true})
    for (bool non_increment : {false, true}) for (u32 start : starts)
    for (u32 low_bits : {0u, 3u}) for (u32 length : lengths) {
        configure(mode, bytes, deferred);
        packet(start, length, non_increment);
        rsx::thread bt, at;
        bt.ctrl->put.value = at.ctrl->put.value = (start + 4) | low_bits;
        before::FIFO_control b(&bt); after::FIFO_control a(&at);
        b.set_get(start); a.set_get(start);
        register_pair bd{sentinel, value_sentinel}, ad = bd;
        b.read(bd);
        assert(bd.reg == FIFO_EMPTY);
        assert(b.get_pos() == start + 4 && b.get_remaining_args_count() == length);
        // Four separate polling calls preserve header GET and return a defined
        // empty status. force publication provides a real GET restart point.
        for (u32 retry = 0; retry < 4; ++retry) {
            ad = {sentinel, value_sentinel}; a.read(ad);
            assert(ad.reg == FIFO_EMPTY && ad.value == value_sentinel);
            assert(a.get_pos() == start && a.get_remaining_args_count() == 0);
            a.sync_get();
            assert(at.ctrl->get.value == start);
            ++counts.header_waits;
        }
        a.sync_get_force(); assert(at.ctrl->get.value == start);
        // Publish all arguments plus the following NOP. The old version now
        // mistakes argument[1] (or the NOP for count==1) for argument[0].
        bt.ctrl->put.value = (start + 4 * (length + 2)) | low_bits;
        b.read(bd);
        counts.old_first_missed += bd.reg != method || bd.value != argument(0);
        assert(bd.reg != method || bd.value != argument(0));
        at.ctrl->put.value = bt.ctrl->put.value;
        const auto consume = [&](after::FIFO_control& fifo) {
            register_pair result{sentinel, value_sentinel}; fifo.read(result);
            counts.new_first_missed += result.reg != method || result.value != argument(0);
            assert(result.reg == method && result.value == argument(0));
            ++counts.resumed_partial_words;
            for (u32 index = 1; index < length; ++index) {
                assert(fifo.read_unsafe(result));
                assert(result.reg == method + (non_increment ? 0 : 4 * index));
                assert(result.value == argument(index));
                ++counts.resumed_partial_words;
            }
            assert(!fifo.read_unsafe(result));
            assert(fifo.get_pos() == start + 4 * (length + 1));
            fifo.read(result); assert(result.reg == FIFO_NOP);
            assert(fifo.get_pos() == start + 4 * (length + 2));
        };
        if (start == 0x407c) {
            after::FIFO_control reentry(&at);
            reentry.set_get(at.ctrl->get.value);
            consume(reentry); ++counts.get_reentries;
        } else consume(a);
        ++counts.partial_packets;
    }
}

void exceptional_paths() {
    for (auto mode : {rsx_fifo_mode::atomic, rsx_fifo_mode::atomic_ordered, rsx_fifo_mode::as_ps3}) {
        configure(mode, 4096, true);
        // The first argument is genuinely unmapped. Keep ERROR and its GET;
        // only FIFO_EMPTY is eligible for the header rewind.
        {
            constexpr u32 start = 0xffffc;
            packet(start, 3, false);
            rsx::thread bt, at;
            bt.ctrl->put.value = at.ctrl->put.value = start + 16;
            bt.iomap_table.bad_begin = at.iomap_table.bad_begin = 0x100000;
            bt.iomap_table.bad_end = at.iomap_table.bad_end = 0x200000;
            before::FIFO_control b(&bt); after::FIFO_control a(&at);
            b.set_get(start); a.set_get(start);
            register_pair bd{sentinel, value_sentinel}, ad = bd;
            b.read(bd); a.read(ad);
            assert(bd.reg == FIFO_ERROR && ad.reg == FIFO_ERROR);
            assert(state(a) == state(b));
            assert(a.get_pos() == start + 4 && a.get_remaining_args_count() == 2);
            ++counts.exceptional;
        }
        // A stopped reservation refill returns {false,0}; preserve this
        // cancellation path instead of confusing it with an unpublished word.
        {
            constexpr u32 start = 0x407c;
            packet(start, 3, false);
            rsx::thread bt, at;
            bt.ctrl->put.value = at.ctrl->put.value = start + 4;
            before::FIFO_control b(&bt); after::FIFO_control a(&at);
            b.set_get(start); a.set_get(start);
            assert(b.fetch_u32(start).first && a.fetch_u32(start).first);
            bt.ctrl->put.value = at.ctrl->put.value = start + 8;
            bt.stopped = at.stopped = true;
            vm::reservations.at((start + 4) / 128) = 1;
            register_pair bd{sentinel, value_sentinel}, ad = bd;
            b.read(bd); a.read(ad);
            assert(bd.reg == FIFO_EMPTY && ad.reg == FIFO_EMPTY);
            assert(state(a) == state(b));
            assert(a.get_pos() == start + 4 && a.get_remaining_args_count() == 3);
            vm::reservations.fill(0); ++counts.exceptional;
        }
        // Recovering a pending argument may replace GET and abort the packet.
        // The new return status must not undo those recovery side effects.
        {
            constexpr u32 start = 0xffff8, recovery = 0x8000;
            packet(start, 3, false);
            rsx::thread bt, at;
            bt.ctrl->put.value = at.ctrl->put.value = start + 8;
            before::FIFO_control b(&bt); after::FIFO_control a(&at);
            b.set_get(start); a.set_get(start);
            register_pair bd{sentinel, value_sentinel}, ad = bd;
            b.read(bd); a.read(ad);
            assert(bd.value == argument(0) && ad.value == argument(0));
            bt.ctrl->put.value = at.ctrl->put.value = start + 12;
            bt.iomap_table.bad_begin = at.iomap_table.bad_begin = 0x100000;
            bt.iomap_table.bad_end = at.iomap_table.bad_end = 0x200000;
            bt.on_recover = [&] { b.set_get(recovery); b.abort(); };
            at.on_recover = [&] { a.set_get(recovery); a.abort(); };
            bd = ad = {sentinel, value_sentinel}; b.read(bd); a.read(ad);
            assert(bt.recoveries == 1 && at.recoveries == 1);
            assert(bd.reg == sentinel && ad.reg == FIFO_EMPTY);
            assert(b.get_pos() == recovery && a.get_pos() == recovery);
            assert(bt.ctrl->get.value == recovery && at.ctrl->get.value == recovery);
            assert(!b.get_remaining_args_count() && !a.get_remaining_args_count());
            ++counts.exceptional;
        }
    }
}

void fast_blocking() {
    for (bool deferred : {false, true}) for (u32 start : starts) {
        configure(rsx_fifo_mode::fast, deferred ? 4096 : 1024, deferred);
        packet(start, 3, false);
        rsx::thread bt, at;
        bt.ctrl->put.value = at.ctrl->put.value = start + 4;
        before::FIFO_control b(&bt); after::FIFO_control a(&at);
        b.set_get(start); a.set_get(start);
        bt.on_wait = [&] { assert(bt.ctrl->get.value == start + 4); bt.ctrl->put.value = start + 8; };
        at.on_wait = [&] { assert(at.ctrl->get.value == start + 4); at.ctrl->put.value = start + 8; };
        register_pair bd{sentinel, value_sentinel}, ad = bd;
        b.read(bd); a.read(ad);
        assert(bt.waits == 1 && at.waits == 1);
        assert(bd.reg == method && ad.reg == method && bd.value == argument(0) && ad.value == argument(0));
        assert(state(b) == state(a)); ++counts.fast_blocking;
    }
}

void restore_pending() {
    // This exercises the existing restore_state method and its GET/count
    // convention, not the emulator's complete savestate serialization.
    for (auto mode : modes) for (bool non_increment : {false, true})
    for (u32 length : {3u, 33u, 1023u}) for (u32 current : {1u, 2u}) {
        configure(mode, 4096, true);
        constexpr u32 start = 0x407c;
        packet(start, length, non_increment);
        rsx::thread bt, at;
        bt.ctrl->get.value = at.ctrl->get.value = start + 4 * (current + 1);
        bt.ctrl->put.value = at.ctrl->put.value = start + 4 * (length + 1);
        before::FIFO_control b(&bt); after::FIFO_control a(&at);
        b.restore_state(command(length, non_increment), length - current);
        a.restore_state(command(length, non_increment), length - current);
        register_pair bd{sentinel, value_sentinel}, ad = bd;
        b.read(bd); a.read(ad);
        const u32 reg = method + (non_increment ? 0 : current * 4);
        assert(bd.reg == reg && ad.reg == reg);
        assert(bd.value == argument(current) && ad.value == bd.value);
        assert(state(b) == state(a)); ++counts.restored_pending;
    }
}

int main() {
    pending_packets(); partial_packets(); exceptional_paths(); fast_blocking(); restore_pending();
    std::cout << "{\"passed\":true,\"assertionsActive\":true"
        << ",\"pendingCases\":" << counts.pending_cases
        << ",\"pendingWaits\":" << counts.pending_waits
        << ",\"baselinePendingUnchanged\":" << counts.old_pending_unchanged
        << ",\"candidatePendingUnchanged\":" << counts.new_pending_unchanged
        << ",\"resumedPendingCommands\":" << counts.resumed_pending
        << ",\"partialPackets\":" << counts.partial_packets
        << ",\"baselineFirstArgumentMissed\":" << counts.old_first_missed
        << ",\"candidateFirstArgumentMissed\":" << counts.new_first_missed
        << ",\"resumedPartialWords\":" << counts.resumed_partial_words
        << ",\"headerWaits\":" << counts.header_waits
        << ",\"getReentries\":" << counts.get_reentries
        << ",\"faultCancellationRecoveryCases\":" << counts.exceptional
        << ",\"fastBlockingCases\":" << counts.fast_blocking
        << ",\"restoredPendingCases\":" << counts.restored_pending << "}\n";
}
