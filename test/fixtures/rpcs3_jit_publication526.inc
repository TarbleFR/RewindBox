// RPCS3 Build526 unmodified MemoryManager1 and MemoryManager2. GPL-2.0-only.
struct MemoryManager1 : llvm::RTDyldMemoryManager
{
	// Desktop reserves 256 MiB for code or data. iOS draws exact-sized
	// allocations from the already prepared process-lifetime arenas.
#ifndef RPCS3_IOS
	static constexpr u64 c_max_size = 0x1000'0000;
	// Allocation unit (2M)
	static constexpr u64 c_page_size = 2 * 1024 * 1024;

	void* m_code_mems = nullptr;
	void* m_data_ro_mems = nullptr;
	void* m_data_rw_mems = nullptr;
	u64 code_ptr = 0;
	u64 data_ro_ptr = 0;
	u64 data_rw_ptr = 0;
#else
	struct code_mapping
	{
		u8* local = nullptr;
		u8* target = nullptr;
		usz size = 0;
	};
	struct arena_allocation
	{
		u8* target = nullptr;
		usz size = 0;
	};

	std::vector<code_mapping> m_pending_code;
	std::vector<code_mapping> m_code;
	std::vector<arena_allocation> m_data;
#endif

	// First fallback for non-existing symbols
	// May be a memory container internally
	std::function<u64(const std::string&)> m_symbols_cement;

	MemoryManager1(std::function<u64(const std::string&)> symbols_cement = {}) noexcept
		: m_symbols_cement(std::move(symbols_cement))
	{
#ifndef RPCS3_IOS
		auto ptr = reinterpret_cast<u8*>(utils::memory_reserve(c_max_size * 3, true));
		m_code_mems = ptr;
		// ptr += c_max_size;
		// m_data_ro_mems = ptr;
		 ptr += c_max_size;
		m_data_rw_mems = ptr;
#endif
	}

	MemoryManager1(const MemoryManager1&) = delete;

	MemoryManager1& operator=(const MemoryManager1&) = delete;

	~MemoryManager1() override
	{
		// Hack: don't release to prevent reuse of address space, see jit_announce
		// constexpr auto how_much = [](u64 pos) { return utils::align(pos, pos < c_page_size ? c_page_size / 4 : c_page_size); };
		// utils::memory_decommit(m_code_mems, how_much(code_ptr));
		// utils::memory_decommit(m_data_ro_mems, how_much(data_ro_ptr));
		// utils::memory_decommit(m_data_rw_mems, how_much(data_rw_ptr));
#ifdef RPCS3_IOS
		for (const code_mapping& item : m_code)
		{
			rpcs3::ios::jit::release_allocation(true, item.target, item.size);
		}
		for (const arena_allocation& item : m_data)
		{
			rpcs3::ios::jit::release_allocation(false, item.target, item.size);
		}
#else
		utils::memory_decommit(m_code_mems, c_max_size * 3, true);
#endif
	}

	llvm::JITSymbol findSymbol(const std::string& name) override
	{
		u64 addr = RTDyldMemoryManager::getSymbolAddress(name);

		if (!addr && m_symbols_cement)
		{
			addr = m_symbols_cement(name);
		}

		if (!addr)
		{
			addr = make_null_function(name);

			if (!addr)
			{
				fmt::throw_exception("Failed to link '%s'", name);
			}
		}

		return {addr, llvm::JITSymbolFlags::Exported};
	}

#ifndef RPCS3_IOS
	u8* allocate(u64& alloc_pos, void* block, uptr size, u64 align, utils::protection prot)
	{
		align = align ? align : 16;
 
		const u64 sizea = utils::align(size, align);

		if (!size || align > c_page_size || sizea > c_max_size || sizea < size)
		{
			jit_log.fatal("Unsupported size/alignment (size=0x%x, align=0x%x)", size, align);
			return nullptr;
		}

		u64 oldp = alloc_pos;

		u64 olda = utils::align(oldp, align);

		ensure(olda >= oldp);
		ensure(olda < ~sizea);

		u64 newp = olda + sizea;

		if ((newp - 1) / c_max_size != (oldp - 1) / c_max_size)
		{
			constexpr usz num_of_allocations = 1;

			if ((newp - 1) / c_max_size > num_of_allocations)
			{
				// Allocating more than one region does not work for relocations, needs more robust solution
				fmt::throw_exception("Out of memory (size=0x%x, align=0x%x)", size, align);
			}
		}

		// Update allocation counter
		alloc_pos = newp;

		constexpr usz page_quarter = c_page_size / 4;

		// Optimization: split the first allocation to 512 KiB for single-module compilers
		if (oldp < c_page_size && align < page_quarter && (std::min(newp, c_page_size) - 1) / page_quarter != (oldp - 1) / page_quarter)
		{
			const u64 pagea = utils::align(oldp, page_quarter);
			const u64 psize = utils::align(std::min(newp, c_page_size) - pagea, page_quarter);
			utils::memory_commit(reinterpret_cast<u8*>(block) + (pagea % c_max_size), psize, prot);

			// Advance
			oldp = pagea + psize;
		}

		if ((newp - 1) / c_page_size != (oldp - 1) / c_page_size)
		{
			// Allocate pages on demand
			const u64 pagea = utils::align(oldp, c_page_size);
			const u64 psize = utils::align(newp - pagea, c_page_size);
			utils::memory_commit(reinterpret_cast<u8*>(block) + (pagea % c_max_size), psize, prot);
		}

		return reinterpret_cast<u8*>(block) + (olda % c_max_size);
	}
#endif

	u8* allocateCodeSection(uptr size, uint align, uint /*sec_id*/, llvm::StringRef /*sec_name*/) override
	{
#ifdef RPCS3_IOS
		align = align ? align : 16;
		u8* const target = static_cast<u8*>(rpcs3::ios::jit::allocate(true, size, align));
		if (!target)
		{
			jit_log.fatal("Unable to allocate iOS LLVM code (size=0x%x, align=0x%x): %s",
				size, align, rpcs3::ios::jit::last_error());
			return nullptr;
		}

		u8* const local = ensure(static_cast<u8*>(rpcs3::ios::jit::writable(target, size)));
		m_pending_code.push_back({local, target, size});
		m_code.push_back({local, target, size});
		maybe_log_ios_jit_arena_pressure(true);
		return local;
#else
		u8* const target = allocate(code_ptr, m_code_mems, size, align, utils::protection::wx);
		return target;
#endif
	}

#ifdef RPCS3_IOS
	void notifyObjectLoaded(llvm::ExecutionEngine* engine, const llvm::object::ObjectFile&) override
	{
		for (const code_mapping& item : m_pending_code)
		{
			engine->mapSectionAddress(item.local, reinterpret_cast<u64>(item.target));
		}
		m_pending_code.clear();
	}
#endif

	u8* allocateDataSection(uptr size, uint align, uint /*sec_id*/, llvm::StringRef /*sec_name*/, bool is_ro) override
	{
#ifdef RPCS3_IOS
		(void)is_ro;
		align = align ? align : 16;
		u8* const target = static_cast<u8*>(rpcs3::ios::jit::allocate(false, size, align));
		if (!target)
		{
			jit_log.fatal("Unable to allocate iOS LLVM data (size=0x%x, align=0x%x): %s",
				size, align, rpcs3::ios::jit::last_error());
			return nullptr;
		}
		m_data.push_back({target, size});
		maybe_log_ios_jit_arena_pressure(false);
		return target;
#else
		if (is_ro)
		{
			// Disabled
			//return allocate(data_ro_ptr, m_data_ro_mems, size, align, utils::protection::rw);
		}
		return allocate(data_rw_ptr, m_data_rw_mems, size, align, utils::protection::rw);
#endif
	}

	bool finalizeMemory(std::string* = nullptr) override
	{
#ifdef RPCS3_IOS
		for (const code_mapping& item : m_code)
		{
			rpcs3::ios::jit::flush(item.target, item.size);
		}
#endif
		return false;
	}

	void registerEHFrames(u8*, u64, usz) override
	{
	}

	void deregisterEHFrames() override
	{
	}
};

// Simple memory manager
struct MemoryManager2 : llvm::RTDyldMemoryManager
{
	// First fallback for non-existing symbols
	// May be a memory container internally
	std::function<u64(const std::string&)> m_symbols_cement;

#ifdef RPCS3_IOS
	struct code_mapping
	{
		u8* local = nullptr;
		u8* target = nullptr;
		usz size = 0;
	};

	std::vector<code_mapping> m_pending_code;
	std::vector<code_mapping> m_code;
#endif

	MemoryManager2(std::function<u64(const std::string&)> symbols_cement = {}) noexcept
		: m_symbols_cement(std::move(symbols_cement))
	{
	}

	~MemoryManager2() override
	{
	}

	llvm::JITSymbol findSymbol(const std::string& name) override
	{
		u64 addr = RTDyldMemoryManager::getSymbolAddress(name);

		if (!addr && m_symbols_cement)
		{
			addr = m_symbols_cement(name);
		}

		if (!addr)
		{
			addr = make_null_function(name);

			if (!addr)
			{
				fmt::throw_exception("Failed to link '%s' (MM2)", name);
			}
		}

		return {addr, llvm::JITSymbolFlags::Exported};
	}

	u8* allocateCodeSection(uptr size, uint align, uint /*sec_id*/, llvm::StringRef /*sec_name*/) override
	{
		u8* const target = jit_runtime::alloc(size, align, true);
#ifdef RPCS3_IOS
		u8* const local = ensure(static_cast<u8*>(rpcs3::ios::jit::writable(target, size)));
		m_pending_code.push_back({local, target, size});
		m_code.push_back({local, target, size});
		return local;
#else
		return target;
#endif
	}

#ifdef RPCS3_IOS
	void notifyObjectLoaded(llvm::ExecutionEngine* engine, const llvm::object::ObjectFile&) override
	{
		for (const code_mapping& item : m_pending_code)
		{
			engine->mapSectionAddress(item.local, reinterpret_cast<u64>(item.target));
		}
		m_pending_code.clear();
	}
#endif

	u8* allocateDataSection(uptr size, uint align, uint /*sec_id*/, llvm::StringRef /*sec_name*/, bool /*is_ro*/) override
	{
		return jit_runtime::alloc(size, align, false);
	}

	bool finalizeMemory(std::string* = nullptr) override
	{
#ifdef RPCS3_IOS
		for (const code_mapping& item : m_code)
		{
			rpcs3::ios::jit::flush(item.target, item.size);
		}
#endif
		return false;
	}

	void registerEHFrames(u8*, u64, usz) override
	{
	}

	void deregisterEHFrames() override
	{
	}
};

