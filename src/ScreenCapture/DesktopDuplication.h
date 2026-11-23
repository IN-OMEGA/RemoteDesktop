#pragma once
#include <string>
namespace remotecore { struct CaptureReport { unsigned width=0,height=0,frames=0,dropped=0; double fps=0, acquisition_ms=0; std::wstring error; }; CaptureReport run_capture_diagnostic(unsigned target_fps=60, unsigned seconds=5); }
