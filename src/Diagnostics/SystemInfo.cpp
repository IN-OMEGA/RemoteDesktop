#include "SystemInfo.h"
#include <windows.h>
#include <dxgi.h>
#include <wrl/client.h>
#include <sstream>
#include <vector>
#pragma comment(lib, "dxgi.lib")
namespace remotecore {
SystemInfo collect_system_info() {
 SystemInfo s{}; OSVERSIONINFOEXW v{}; v.dwOSVersionInfoSize=sizeof(v);
 using RtlGetVersionFn=LONG(WINAPI*)(PRTL_OSVERSIONINFOW);
 auto n=GetModuleHandleW(L"ntdll.dll"); auto f=reinterpret_cast<RtlGetVersionFn>(GetProcAddress(n,"RtlGetVersion"));
 if(f && f(reinterpret_cast<PRTL_OSVERSIONINFOW>(&v))==0){std::wstringstream x;x<<L"Windows "<<v.dwMajorVersion<<L'.'<<v.dwMinorVersion<<L" (build "<<v.dwBuildNumber<<L')';s.windows=x.str();} else s.errors+=L"Windows version detection failed. ";
 Microsoft::WRL::ComPtr<IDXGIFactory1> factory; HRESULT hr=CreateDXGIFactory1(IID_PPV_ARGS(&factory));
 if(SUCCEEDED(hr)){ std::wstringstream ds,gs; UINT i=0; bool first=true; Microsoft::WRL::ComPtr<IDXGIAdapter1> a;
 while(factory->EnumAdapters1(i++, &a)!=DXGI_ERROR_NOT_FOUND){DXGI_ADAPTER_DESC1 d{}; a->GetDesc1(&d); if(d.Flags&DXGI_ADAPTER_FLAG_SOFTWARE){a.Reset();continue;} if(!first){ds<<L"; ";gs<<L"; ";} first=false; gs<<d.Description; UINT j=0; Microsoft::WRL::ComPtr<IDXGIOutput> o; bool found=false; while(a->EnumOutputs(j++,&o)!=DXGI_ERROR_NOT_FOUND){DXGI_OUTPUT_DESC od{};o->GetDesc(&od);if(!found){if(ds.tellp()>0)ds<<L" | ";ds<<d.Description<<L": ";} if(found)ds<<L", ";ds<<od.DeviceName;found=true;o.Reset();} if(!found)ds<<d.Description<<L": aucun écran associé"; a.Reset(); }
 s.gpu=gs.str().empty()?L"Aucun adaptateur graphique matériel détecté":gs.str();s.displays=ds.str().empty()?L"Aucun écran détecté":ds.str();
 } else {s.errors+=L"Énumération DXGI échouée ("+std::to_wstring(hr)+L"). ";}
 s.nvenc=L"Non vérifié : le SDK NVENC NVIDIA n’est pas intégré à cette étape.";
 return s;
}}
