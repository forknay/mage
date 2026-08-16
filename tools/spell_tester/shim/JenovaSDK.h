// JenovaSDK.h -- stand-in for the real Jenova SDK header.
// =============================================================================
// recognizer.cpp and spell_engine.cpp log through jenova::sdk::Output, which
// only exists inside Godot's Jenova runtime. The tester compiles those exact
// files unmodified, so it needs *something* by that name: this header is put
// first on the include path when building the tester, so `#include
// <JenovaSDK.h>` resolves here instead, and the log lines land on the console.
//
// Nothing else from the SDK is referenced by the shared engine sources -- the
// one file that really needs Jenova (godot_spell_engine.cpp, the GDScript
// binding) is not part of the tester build.
#pragma once

#include <cstdarg>
#include <cstdio>

namespace jenova {
namespace sdk {

inline void Output(const char* format, ...) {
	va_list args;
	va_start(args, format);
	std::vfprintf(stdout, format, args);
	va_end(args);
	std::fputc('\n', stdout);
	std::fflush(stdout);
}

}  // namespace sdk
}  // namespace jenova
