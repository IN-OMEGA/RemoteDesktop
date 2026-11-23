#pragma once
#include <string>
namespace remotecore { struct SystemInfo { std::wstring windows; std::wstring gpu; std::wstring displays; std::wstring nvenc; std::wstring errors; }; SystemInfo collect_system_info(); }
