#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <new>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>
#include <cstdint>
using usz=std::size_t;using u32=std::uint32_t;
[[maybe_unused]] constexpr auto umax=static_cast<usz>(-1);
static thread_local bool count_allocations=false;
static thread_local usz allocations=0;
__attribute__((noinline)) void* operator new(std::size_t n){if(count_allocations)++allocations;if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
__attribute__((noinline)) void operator delete(void* p) noexcept{std::free(p);}
__attribute__((noinline)) void operator delete(void* p,std::size_t) noexcept{std::free(p);}
namespace fmt {
	template <usz list_size>
	std::string replace_all(std::string src, const std::pair<std::string_view, std::string> (&list)[list_size])
	{
		if constexpr (list_size == 0)
			return src;

		for (usz pos = 0; pos < src.length(); ++pos)
		{
			for (usz i = 0; i < list_size; ++i)
			{
				const usz comp_length = list[i].first.length();

				if (src.length() - pos < comp_length)
				{
					continue;
				}

				if (src.substr(pos, comp_length) == list[i].first)
				{
					src.erase(pos, comp_length);
					src.insert(pos, list[i].second.data(), list[i].second.length());
					pos += list[i].second.length() - 1;
					break;
				}
			}
		}

		return src;
	}

	template <usz list_size>
	std::string replace_all(std::string src, const std::pair<std::string_view, std::function<std::string()>> (&list)[list_size])
	{
		if constexpr (list_size == 0)
			return src;

		for (usz pos = 0; pos < src.length(); ++pos)
		{
			for (usz i = 0; i < list_size; ++i)
			{
				const usz comp_length = list[i].first.length();

				if (src.length() - pos < comp_length)
				{
					continue;
				}

				if (src.substr(pos, comp_length) == list[i].first)
				{
					src.erase(pos, comp_length);
					auto replacement = list[i].second();
					src.insert(pos, replacement);
					pos += replacement.length() - 1;
					break;
				}
			}
		}

		return src;
	}

}
enum ParamFlag
{
	PF_PARAM_IN,
	PF_PARAM_OUT,
	PF_PARAM_UNIFORM,
	PF_PARAM_CONST,
	PF_PARAM_NONE,
	PF_PARAM_COUNT,
};

struct ParamItem
{
	const std::string name;
	const std::string value;
	int location;

	ParamItem(std::string _name, int _location, std::string _value = "")
		: name(std::move(_name))
		, value(std::move(_value)),
		location(_location)
	{ }
};

struct ParamType
{
	const ParamFlag flag;
	const std::string type;
	std::vector<ParamItem> items;

	ParamType(const ParamFlag _flag, std::string _type)
		: flag(_flag)
		, type(std::move(_type))
	{
	}

	bool HasItem(std::string_view name) const
	{
		return std::any_of(items.cbegin(), items.cend(), [&name](const auto& item)
		{
			return item.name == name;
		});
	}

	bool ReplaceOrInsert(std::string_view name, const ParamItem& item)
	{
		if (HasItem(name))
		{
			std::vector<ParamItem> new_list;
			for (const auto& it : items)
			{
				if (it.name != name)
				{
					new_list.emplace_back(it.name, it.location, it.value);
				}
				else
				{
					new_list.emplace_back(item.name, item.location, item.value);
				}
			}

			std::swap(items, new_list);
			return true;
		}

		items.push_back(item);
		return false;
	}
};

struct ParamArray
{
	std::vector<ParamType> params[PF_PARAM_COUNT];

	ParamType* SearchParam(const ParamFlag& flag, std::string_view type)
	{
		for (auto& param : params[flag])
		{
			if (param.type == type)
				return &param;
		}

		return nullptr;
	}

	bool HasParamTypeless(const ParamFlag flag, std::string_view name) const
	{
		const auto& p = params[flag];
		return std::any_of(p.cbegin(), p.cend(), [&name](const auto& param)
		{
			return param.HasItem(name);
		});
	}

	bool HasParam(const ParamFlag flag, std::string_view type, std::string_view name)
	{
		const ParamType* t = SearchParam(flag, type);
		return t && t->HasItem(name);
	}

	std::string AddParam(const ParamFlag flag, const std::string& type, const std::string& name, const std::string& value)
	{
		ParamType* t = SearchParam(flag, type);

		if (t)
		{
			if (!t->HasItem(name)) t->items.emplace_back(name, -1, value);
		}
		else
		{
			params[flag].emplace_back(flag, type);
			params[flag].back().items.emplace_back(name, -1, value);
		}

		return name;
	}

	std::string AddParam(const ParamFlag flag, const std::string& type, const std::string& name, int location = -1)
	{
		ParamType* t = SearchParam(flag, type);

		if (t)
		{
			if (!t->HasItem(name)) t->items.emplace_back(name, location);
		}
		else
		{
			params[flag].emplace_back(flag, type);
			params[flag].back().items.emplace_back(name, location);
		}

		return name;
	}

	void Clear()
	{
		for (auto& param : params)
		{
			param.clear();
		}
	}
};


template <usz Count>
std::string replace_shader_tokens(std::string_view source,
	const std::pair<std::string_view, std::function<std::string()>> (&tokens)[Count])
{
	std::string result;
	result.reserve(source.size());
	usz cursor = 0;
	for (usz pos; (pos = source.find('$', cursor)) != std::string_view::npos;)
	{
		result.append(source.substr(cursor, pos - cursor));
		bool matched = false;
		for (const auto& token : tokens)
		{
			if (source.substr(pos, token.first.size()) == token.first)
			{
				result += token.second();
				cursor = pos + token.first.size();
				matched = true;
				break;
			}
		}
		if (!matched)
		{
			result += '$';
			cursor = pos + 1;
		}
	}
	result.append(source.substr(cursor));
	return result;
}
constexpr int RSX_FP_OPCODE_TEXBEM=1,RSX_FP_OPCODE_TXPBEM=2;
struct SRC0{static constexpr int index=0;};struct SRC1{static constexpr int index=1;};struct SRC2{static constexpr int index=2;};
struct Boundary {
    int mode=0;std::vector<int> events;ParamArray params;
    struct {int tex_num=3,opcode=0;bool fp16=false;}dst;
    struct {int tex_num=7;}d2;
    struct {bool has_native_half_support=false;}device_props;
    std::string invoke(int key){
        events.push_back(key);
        const auto name=std::string("param")+std::to_string(key);
        params.AddParam(PF_PARAM_NONE,"vec4",name,mode);
        switch(mode%5){
        case 0:return name;
        case 1:return {};
        case 2:return "$0$$"+name;
        case 3:return std::string(100,'x')+name;
        default:return std::string("x\0$Ty",5)+name;
        }
    }
    std::string AddAddrReg(){return invoke(3);}
    std::string GetCond(){return mode%3==0?"true":invoke(4);}
    std::string GetOptionalBranchCond(){return invoke(5);}
    std::string GetMask(){return invoke(6);}
    std::string AddConst(){return invoke(7);}
    std::string getFloatTypeName(usz n){return invoke(10+static_cast<int>(n));}
    std::string getHalfTypeName(usz n){return invoke(20+static_cast<int>(n));}
    void reset(int value){mode=value;events.clear();params.Clear();}
    std::string declarations()const{
        std::string result;for(const auto& group:params.params)for(const auto& type:group)for(const auto& item:type.items)
            result+=type.type+"/"+item.name+"/"+item.value+"/"+std::to_string(item.location)+";";
        return result;
    }
};
#define RPCS3_IOS
namespace before {
// BEGIN BOUNDARY
struct VertexProgramDecompiler:Boundary{
    std::string GetSRC(u32 n){return invoke(static_cast<int>(n));}
    struct Instr{std::vector<std::string>body;}instruction;
    Instr* m_cur_instr=&instruction;std::vector<std::string>m_body;
    std::string Format(const std::string& code);void AddCode(const std::string& code);
};
struct FragmentProgramDecompiler:Boundary{
    SRC0 src0;SRC1 src1;SRC2 src2;
    template<typename T>std::string GetSRC(T){return invoke(T::index);}
    std::string Format(const std::string& code,bool ignore_redirects=false);
};

std::string VertexProgramDecompiler::Format(const std::string& code)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", std::bind(std::mem_fn(&VertexProgramDecompiler::GetSRC), this, 0) },
		{ "$1", std::bind(std::mem_fn(&VertexProgramDecompiler::GetSRC), this, 1) },
		{ "$2", std::bind(std::mem_fn(&VertexProgramDecompiler::GetSRC), this, 2) },
		{ "$s", std::bind(std::mem_fn(&VertexProgramDecompiler::GetSRC), this, 2) },
		{ "$a", std::bind(std::mem_fn(&VertexProgramDecompiler::AddAddrReg), this) },
		{ "$t", [this]() -> std::string { return "vtex" + std::to_string(d2.tex_num); } },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", std::bind(std::mem_fn(&VertexProgramDecompiler::GetCond), this) },
		{ "$ifbcond", std::bind(std::mem_fn(&VertexProgramDecompiler::GetOptionalBranchCond), this) },
		{ "$Ty", [this](){ return getFloatTypeName(4); } }
	};

	return fmt::replace_all(code, repl_list);
}
void VertexProgramDecompiler::AddCode(const std::string& code)
{
	m_body.push_back(Format(code) + ";");
	m_cur_instr->body.push_back(Format(code));
}
std::string FragmentProgramDecompiler::Format(const std::string& code, bool ignore_redirects)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", [this]() -> std::string {return GetSRC<SRC0>(src0);} },
		{ "$1", [this]() -> std::string {return GetSRC<SRC1>(src1);} },
		{ "$2", [this]() -> std::string {return GetSRC<SRC2>(src2);} },
		{ "$t", [this]() -> std::string { return "tex" + std::to_string(dst.tex_num);} },
		{ "$_i", [this]() -> std::string {return std::to_string(dst.tex_num);} },
		{ "$m", std::bind(std::mem_fn(&FragmentProgramDecompiler::GetMask), this) },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", std::bind(std::mem_fn(&FragmentProgramDecompiler::GetCond), this) },
		{ "$_c", std::bind(std::mem_fn(&FragmentProgramDecompiler::AddConst), this) },
		{ "$float4", [this]() -> std::string { return getFloatTypeName(4); } },
		{ "$float3", [this]() -> std::string { return getFloatTypeName(3); } },
		{ "$float2", [this]() -> std::string { return getFloatTypeName(2); } },
		{ "$float_t", [this]() -> std::string { return getFloatTypeName(1); } },
		{ "$half4", [this]() -> std::string { return getHalfTypeName(4); } },
		{ "$half3", [this]() -> std::string { return getHalfTypeName(3); } },
		{ "$half2", [this]() -> std::string { return getHalfTypeName(2); } },
		{ "$half_t", [this]() -> std::string { return getHalfTypeName(1); } },
		{ "$Ty", [this]() -> std::string { return (!device_props.has_native_half_support || !dst.fp16)? getFloatTypeName(4) : getHalfTypeName(4); } }
	};

	if (!ignore_redirects)
	{
		//Special processing redirects
		switch (dst.opcode)
		{
		case RSX_FP_OPCODE_TEXBEM:
		case RSX_FP_OPCODE_TXPBEM:
		{
			//Redirect parameter 0 to the x2d temp register for TEXBEM
			//TODO: Organize this a little better
			std::pair<std::string_view, std::string> repl[] = { { "$0", "x2d" } };
			std::string result = fmt::replace_all(code, repl);

			return fmt::replace_all(result, repl_list);
		}
		}
	}

	return fmt::replace_all(code, repl_list);
}
}
#undef RPCS3_IOS
#define RPCS3_IOS
namespace after {
// BEGIN BOUNDARY
struct VertexProgramDecompiler:Boundary{
    std::string GetSRC(u32 n){return invoke(static_cast<int>(n));}
    struct Instr{std::vector<std::string>body;}instruction;
    Instr* m_cur_instr=&instruction;std::vector<std::string>m_body;
    std::string Format(const std::string& code);void AddCode(const std::string& code);
};
struct FragmentProgramDecompiler:Boundary{
    SRC0 src0;SRC1 src1;SRC2 src2;
    template<typename T>std::string GetSRC(T){return invoke(T::index);}
    std::string Format(const std::string& code,bool ignore_redirects=false);
};

std::string VertexProgramDecompiler::Format(const std::string& code)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", [this]() { return GetSRC(0); } },
		{ "$1", [this]() { return GetSRC(1); } },
		{ "$2", [this]() { return GetSRC(2); } },
		{ "$s", [this]() { return GetSRC(2); } },
		{ "$a", [this]() { return AddAddrReg(); } },
		{ "$t", [this]() -> std::string { return "vtex" + std::to_string(d2.tex_num); } },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", [this]() { return GetCond(); } },
		{ "$ifbcond", [this]() { return GetOptionalBranchCond(); } },
		{ "$Ty", [this](){ return getFloatTypeName(4); } }
	};

	#ifdef RPCS3_IOS
	return replace_shader_tokens(code, repl_list);
#else
	return fmt::replace_all(code, repl_list);
#endif
}
void VertexProgramDecompiler::AddCode(const std::string& code)
{
#ifdef RPCS3_IOS
	// Format only once: its declaration/constant registration is idempotent.
	// Keep the two original text forms used by the full body and CFG builder.
	auto formatted = Format(code);
	m_body.push_back(formatted + ";");
	m_cur_instr->body.push_back(std::move(formatted));
#else
	m_body.push_back(Format(code) + ";");
	m_cur_instr->body.push_back(Format(code));
#endif
}
std::string FragmentProgramDecompiler::Format(const std::string& code, bool ignore_redirects)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", [this]() -> std::string {return GetSRC<SRC0>(src0);} },
		{ "$1", [this]() -> std::string {return GetSRC<SRC1>(src1);} },
		{ "$2", [this]() -> std::string {return GetSRC<SRC2>(src2);} },
		{ "$t", [this]() -> std::string { return "tex" + std::to_string(dst.tex_num);} },
		{ "$_i", [this]() -> std::string {return std::to_string(dst.tex_num);} },
		{ "$m", [this]() { return GetMask(); } },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", [this]() { return GetCond(); } },
		{ "$_c", [this]() { return AddConst(); } },
		{ "$float4", [this]() -> std::string { return getFloatTypeName(4); } },
		{ "$float3", [this]() -> std::string { return getFloatTypeName(3); } },
		{ "$float2", [this]() -> std::string { return getFloatTypeName(2); } },
		{ "$float_t", [this]() -> std::string { return getFloatTypeName(1); } },
		{ "$half4", [this]() -> std::string { return getHalfTypeName(4); } },
		{ "$half3", [this]() -> std::string { return getHalfTypeName(3); } },
		{ "$half2", [this]() -> std::string { return getHalfTypeName(2); } },
		{ "$half_t", [this]() -> std::string { return getHalfTypeName(1); } },
		{ "$Ty", [this]() -> std::string { return (!device_props.has_native_half_support || !dst.fp16)? getFloatTypeName(4) : getHalfTypeName(4); } }
	};

	if (!ignore_redirects)
	{
		//Special processing redirects
		switch (dst.opcode)
		{
		case RSX_FP_OPCODE_TEXBEM:
		case RSX_FP_OPCODE_TXPBEM:
		{
			//Redirect parameter 0 to the x2d temp register for TEXBEM
			//TODO: Organize this a little better
			std::pair<std::string_view, std::string> repl[] = { { "$0", "x2d" } };
			std::string result = fmt::replace_all(code, repl);

			#ifdef RPCS3_IOS
			return replace_shader_tokens(result, repl_list);
#else
			return fmt::replace_all(result, repl_list);
#endif
		}
		}
	}

	#ifdef RPCS3_IOS
	return replace_shader_tokens(code, repl_list);
#else
	return fmt::replace_all(code, repl_list);
#endif
}
}
#undef RPCS3_IOS
namespace desktop {
// BEGIN BOUNDARY
struct VertexProgramDecompiler:Boundary{
    std::string GetSRC(u32 n){return invoke(static_cast<int>(n));}
    struct Instr{std::vector<std::string>body;}instruction;
    Instr* m_cur_instr=&instruction;std::vector<std::string>m_body;
    std::string Format(const std::string& code);void AddCode(const std::string& code);
};
struct FragmentProgramDecompiler:Boundary{
    SRC0 src0;SRC1 src1;SRC2 src2;
    template<typename T>std::string GetSRC(T){return invoke(T::index);}
    std::string Format(const std::string& code,bool ignore_redirects=false);
};

std::string VertexProgramDecompiler::Format(const std::string& code)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", [this]() { return GetSRC(0); } },
		{ "$1", [this]() { return GetSRC(1); } },
		{ "$2", [this]() { return GetSRC(2); } },
		{ "$s", [this]() { return GetSRC(2); } },
		{ "$a", [this]() { return AddAddrReg(); } },
		{ "$t", [this]() -> std::string { return "vtex" + std::to_string(d2.tex_num); } },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", [this]() { return GetCond(); } },
		{ "$ifbcond", [this]() { return GetOptionalBranchCond(); } },
		{ "$Ty", [this](){ return getFloatTypeName(4); } }
	};

	#ifdef RPCS3_IOS
	return replace_shader_tokens(code, repl_list);
#else
	return fmt::replace_all(code, repl_list);
#endif
}
void VertexProgramDecompiler::AddCode(const std::string& code)
{
#ifdef RPCS3_IOS
	// Format only once: its declaration/constant registration is idempotent.
	// Keep the two original text forms used by the full body and CFG builder.
	auto formatted = Format(code);
	m_body.push_back(formatted + ";");
	m_cur_instr->body.push_back(std::move(formatted));
#else
	m_body.push_back(Format(code) + ";");
	m_cur_instr->body.push_back(Format(code));
#endif
}
std::string FragmentProgramDecompiler::Format(const std::string& code, bool ignore_redirects)
{
	const std::pair<std::string_view, std::function<std::string()>> repl_list[] =
	{
		{ "$$", []() -> std::string { return "$"; } },
		{ "$0", [this]() -> std::string {return GetSRC<SRC0>(src0);} },
		{ "$1", [this]() -> std::string {return GetSRC<SRC1>(src1);} },
		{ "$2", [this]() -> std::string {return GetSRC<SRC2>(src2);} },
		{ "$t", [this]() -> std::string { return "tex" + std::to_string(dst.tex_num);} },
		{ "$_i", [this]() -> std::string {return std::to_string(dst.tex_num);} },
		{ "$m", [this]() { return GetMask(); } },
		{ "$ifcond ", [this]() -> std::string
			{
				const std::string& cond = GetCond();
				if (cond == "true") return "";
				return "if(" + cond + ") ";
			}
		},
		{ "$cond", [this]() { return GetCond(); } },
		{ "$_c", [this]() { return AddConst(); } },
		{ "$float4", [this]() -> std::string { return getFloatTypeName(4); } },
		{ "$float3", [this]() -> std::string { return getFloatTypeName(3); } },
		{ "$float2", [this]() -> std::string { return getFloatTypeName(2); } },
		{ "$float_t", [this]() -> std::string { return getFloatTypeName(1); } },
		{ "$half4", [this]() -> std::string { return getHalfTypeName(4); } },
		{ "$half3", [this]() -> std::string { return getHalfTypeName(3); } },
		{ "$half2", [this]() -> std::string { return getHalfTypeName(2); } },
		{ "$half_t", [this]() -> std::string { return getHalfTypeName(1); } },
		{ "$Ty", [this]() -> std::string { return (!device_props.has_native_half_support || !dst.fp16)? getFloatTypeName(4) : getHalfTypeName(4); } }
	};

	if (!ignore_redirects)
	{
		//Special processing redirects
		switch (dst.opcode)
		{
		case RSX_FP_OPCODE_TEXBEM:
		case RSX_FP_OPCODE_TXPBEM:
		{
			//Redirect parameter 0 to the x2d temp register for TEXBEM
			//TODO: Organize this a little better
			std::pair<std::string_view, std::string> repl[] = { { "$0", "x2d" } };
			std::string result = fmt::replace_all(code, repl);

			#ifdef RPCS3_IOS
			return replace_shader_tokens(result, repl_list);
#else
			return fmt::replace_all(result, repl_list);
#endif
		}
		}
	}

	#ifdef RPCS3_IOS
	return replace_shader_tokens(code, repl_list);
#else
	return fmt::replace_all(code, repl_list);
#endif
}
}

static const std::vector<std::string> corpus={"\t$float4 choice = abs(a);\n",
"\t$float4 tmp = a / _builtin_sqrt(b);\n",
"\treturn clamp(x, $half_t(_min), $half_t(_max));\n",
"\tx = _select(x, $float4(0.), nans);\n",
"\tx = _select(x, $half4(0.), nans);\n",
"$",
"$$",
"$0",
"$0.xyxy + $1.xxxx * $2.xzxz + $1.yyyy * $2.ywyw",
"$1",
"$2",
"$Ty",
"$Ty(",
"$Ty(1.0, $0.y * $1.y, $0.z, $1.w)",
"$_c",
"$_i",
"$a",
"$cond",
"$float2",
"$float3",
"$float4",
"$float4 _builtin_divsq($float4 a, float b)\n",
"$float4 clamp16($float4 x)\n",
"$float4 precision_clamp($float4 x, float _min, float _max)\n",
"$float4(uintBitsToFloat((floatBitsToUint($0.x) & 0x0000ffff) | (packHalf2x16($1.xx) & 0xffff0000)))",
"$float4(uintBitsToFloat((floatBitsToUint($0.x) & 0xffff0000) | (packHalf2x16($1.xx) & 0x0000ffff)))",
"$float_t",
"$half2",
"$half3",
"$half4",
"$half4 precision_clamp($half4 x, float _min, float _max)\n",
"$half_t",
"$ifbcond",
"$ifbcond //BRB",
"$ifcond",
"$ifcond ",
"$ifcond //BRA",
"$ifcond //BRI",
"$ifcond for(int i%u = 0; i%u < %u; i%u++) // %s { %u, %d }",
"$ifcond return",
"$m",
"$m = ",
"$m;",
"$s",
"$s.x",
"$t",
"($0 * $1)",
"($0 + $1)",
"($0 + $2)",
"($0)",
"(1.0 / $s)",
"(uintBitsToFloat(packHalf2x16($0.xy)))",
"(uintBitsToFloat(packSnorm4x8($0)))",
"(uintBitsToFloat(packUnorm2x16($0.xy)))",
"(uintBitsToFloat(packUnorm4x8($0)))",
"(unpackUnorm4x8(floatBitsToUint($0.x)))",
"_builtin_div($0, $1.x)",
"_builtin_divsq($0, $1.x)",
"_builtin_floor($0)",
"_builtin_lerp($2, $1, $0)",
"_builtin_lif($0)",
"_builtin_lit($0)",
"_builtin_lit($s)",
"_builtin_log2($0.x).xxxx",
"_builtin_normalize($0.xyz).xyzz",
"_builtin_pkg($0)",
"_builtin_rcp($0.x).xxxx",
"_builtin_rsq($0.x).xxxx",
"_builtin_upg($0.x)",
"_enable_texture_expand($_i);",
"clamp(1.0 / $s, 5.42101e-20, 1.884467e19)",
"cos($0.xxxx)",
"cos($s)",
"exp($s)",
"exp2($0.xxxx)",
"exp2($s)",
"floor($0)",
"fma($0, $1, $2)",
"if($cond)",
"jump_position = $a;",
"log($s)",
"max($0, $1)",
"min($0, $1)",
"sign($0)",
"sin($0.xxxx)",
"sin($s)",
"unpackHalf2x16(floatBitsToUint($0.x)).xyxy",
"unpackSnorm4x8(floatBitsToUint($0.x))",
"unpackUnorm2x16(floatBitsToUint($0.x)).xyxy",
"vec4(1.0, $0.y * $1.y, $0.z, $1.w)",
"x2d = $0.xyxy + $1.xxxx * $2.xzxz + $1.yyyy * $2.ywyw;"};
static std::uint64_t random_state=0x14067a9d65dull;
static u32 random_value(){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return static_cast<u32>(random_state);}
static usz checks=0,addcode_checks=0;
static void check(const std::string& input,int mode){
    before::VertexProgramDecompiler a;after::VertexProgramDecompiler b;desktop::VertexProgramDecompiler d;
    a.reset(mode);b.reset(mode);d.reset(mode);
    const auto old=a.Format(input),cur=b.Format(input),desk=d.Format(input);
    assert(old==cur&&old==desk&&a.events==b.events&&a.events==d.events);
    assert(a.declarations()==b.declarations()&&a.declarations()==d.declarations());++checks;
    a.reset(mode);b.reset(mode);d.reset(mode);a.AddCode(input);b.AddCode(input);d.AddCode(input);
    assert(a.m_body==b.m_body&&a.m_body==d.m_body&&a.instruction.body==b.instruction.body&&a.instruction.body==d.instruction.body);
    assert(a.declarations()==b.declarations()&&a.declarations()==d.declarations());
    assert(a.events.size()==2*b.events.size());
    assert(std::equal(b.events.begin(),b.events.end(),a.events.begin()));++addcode_checks;
    for(int opcode=0;opcode<3;++opcode)for(bool ignore:{false,true}){
        before::FragmentProgramDecompiler fa;after::FragmentProgramDecompiler fb;desktop::FragmentProgramDecompiler fd;
        for(auto* ptr:std::vector<Boundary*>{&fa,&fb,&fd}){ptr->reset(mode);ptr->dst.opcode=opcode;ptr->dst.fp16=(mode&1);ptr->device_props.has_native_half_support=(mode&2);}
        const auto x=fa.Format(input,ignore),y=fb.Format(input,ignore),z=fd.Format(input,ignore);
        assert(x==y&&x==z&&fa.events==fb.events&&fa.events==fd.events);
        assert(fa.declarations()==fb.declarations()&&fa.declarations()==fd.declarations());++checks;
    }
}
static volatile usz sink=0;
template<class T>static std::pair<double,usz> benchmark(const std::string& input,int mode,int loops){
    T instance;instance.reset(mode);instance.events.reserve(1000000);
    for(int i=0;i<4;++i){const auto value=instance.Format(input);sink=value.size();}
    allocations=0;count_allocations=true;const auto started=std::chrono::steady_clock::now();
    for(int i=0;i<loops;++i){instance.events.clear();const auto result=instance.Format(input);sink=result.size();}
    const auto stopped=std::chrono::steady_clock::now();count_allocations=false;
    return {std::chrono::duration<double,std::nano>(stopped-started).count()/loops,allocations};
}
int main(int argc,char**){
    for(const auto& input:corpus)for(int mode=0;mode<10;++mode)check(input,mode);
    const std::vector<std::string>parts={"abc"," ","$","$$","$0","$1","$2","$s","$t","$a","$m","$_c","$_i","$Ty","$cond","$ifcond ","$ifbcond","$float4","$float_t","$half2","$half_t","$unknown","\n",std::string("\0",1)};
    check({},0);check("$",0);check(std::string(4096,'z'),0);
    for(int i=0;i<10000;++i){std::string input;for(u32 j=random_value()%20;j;--j)input+=parts[random_value()%parts.size()];check(input,static_cast<int>(random_value()%10));}
    std::cout<<"{\"formatChecks\":"<<checks<<",\"addCodeChecks\":"<<addcode_checks<<",\"productionTokenLiterals\":"<<corpus.size()<<",\"identicalTextAndCallbackOrder\":true,\"sameDeclarations\":true,\"benchmarks\":[";
    if(argc>1){
        const std::vector<std::pair<std::string,std::string>> cases={{"literal",std::string(160,'x')},{"typical","$ifcond r0$m = clamp($0 * $1 + $2, 0.0, 1.0)$m;"},{"tokens",std::string(20,'$')+"$0$1$2$cond$Ty$float4$half4$_c"}};
        bool first=true;for(const auto& [name,input]:cases)for(int mode:{0,1,3}){
            const auto a=benchmark<before::FragmentProgramDecompiler>(input,mode,3000);const auto b=benchmark<after::FragmentProgramDecompiler>(input,mode,3000);
            const auto va=benchmark<before::VertexProgramDecompiler>(input,mode,3000);const auto vb=benchmark<after::VertexProgramDecompiler>(input,mode,3000);
            if(!first)std::cout<<",";
            first=false;
            std::cout<<"{\"case\":\""<<name<<"\",\"mode\":"<<mode<<",\"fragmentBeforeNs\":"<<a.first<<",\"fragmentAfterNs\":"<<b.first<<",\"fragmentBeforeAllocations\":"<<a.second<<",\"fragmentAfterAllocations\":"<<b.second<<",\"vertexBeforeNs\":"<<va.first<<",\"vertexAfterNs\":"<<vb.first<<",\"vertexBeforeAllocations\":"<<va.second<<",\"vertexAfterAllocations\":"<<vb.second<<",\"iterations\":3000}";
        }
    }
    std::cout<<"]}\n";
}
