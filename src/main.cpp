#include "Diagnostics/SystemInfo.h"
#include "ScreenCapture/DesktopDuplication.h"
#include <windows.h>
#include <string>
int WINAPI wWinMain(HINSTANCE,HINSTANCE,PWSTR,int){
 auto s=remotecore::collect_system_info();
 auto c=remotecore::run_capture_diagnostic(60,5);
 std::wstring m=L"RemoteCore — diagnostics\n\nSystème : "+s.windows+L"\n\nGPU : "+s.gpu+L"\n\nÉcrans : "+s.displays+L"\n\nCapture : "+std::to_wstring(c.width)+L" x "+std::to_wstring(c.height)+L"\nImages : "+std::to_wstring(c.frames)+L" ("+std::to_wstring(c.fps)+L" FPS)\nAcquisition moyenne : "+std::to_wstring(c.acquisition_ms)+L" ms\nImages manquées estimées : "+std::to_wstring(c.dropped)+L"\nErreur : "+(c.error.empty()?L"Aucune":c.error)+L"\n\nNVENC : "+s.nvenc;
 MessageBoxW(nullptr,m.c_str(),L"RemoteCore",MB_OK|MB_ICONINFORMATION);return 0;
}
