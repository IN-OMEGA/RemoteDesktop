#include "DesktopDuplication.h"
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <chrono>
#include <thread>
#include <sstream>
#include <iomanip>
#pragma comment(lib,"d3d11.lib")
#pragma comment(lib,"dxgi.lib")
using Microsoft::WRL::ComPtr;
namespace remotecore {
CaptureReport run_capture_diagnostic(unsigned target_fps,unsigned seconds){
 CaptureReport r{}; if(target_fps!=30&&target_fps!=60&&target_fps!=120){r.error=L"Cible FPS invalide (30, 60 ou 120).";return r;}
 ComPtr<IDXGIFactory1> factory; HRESULT hr=CreateDXGIFactory1(IID_PPV_ARGS(&factory)); if(FAILED(hr)){r.error=L"CreateDXGIFactory1 a échoué.";return r;}
 ComPtr<IDXGIAdapter1> adapter; ComPtr<IDXGIOutput> output; ComPtr<IDXGIOutput1> output1;
 for(UINT a=0;factory->EnumAdapters1(a,&adapter)!=DXGI_ERROR_NOT_FOUND&&!output1;++a){for(UINT o=0;adapter->EnumOutputs(o,&output)!=DXGI_ERROR_NOT_FOUND;++o){DXGI_OUTPUT_DESC desc{};output->GetDesc(&desc);if(desc.AttachedToDesktop&&desc.Monitor==MonitorFromPoint({0,0},MONITOR_DEFAULTTOPRIMARY)){hr=output.As(&output1);break;} output.Reset();} if(!output1)adapter.Reset();}
 if(!output1){r.error=L"Aucun écran principal DXGI trouvé.";return r;}
 ComPtr<ID3D11Device> dev;ComPtr<ID3D11DeviceContext> ctx;D3D_FEATURE_LEVEL level{};hr=D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr, D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,D3D11_SDK_VERSION,&dev,&level,&ctx);if(FAILED(hr)){r.error=L"Création du périphérique D3D11 échouée.";return r;}
 ComPtr<IDXGIOutputDuplication> duplication;hr=output1->DuplicateOutput(dev.Get(),&duplication);if(FAILED(hr)){r.error=L"Desktop Duplication indisponible (session verrouillée, accès refusé ou mode non pris en charge). HRESULT="+std::to_wstring((unsigned)hr);return r;}
 DXGI_OUTDUPL_DESC dd{};duplication->GetDesc(&dd);r.width=dd.ModeDesc.Width;r.height=dd.ModeDesc.Height;
 auto begin=std::chrono::steady_clock::now(),end=begin+std::chrono::seconds(seconds);auto period=std::chrono::microseconds(1000000/target_fps);double total_ms=0;unsigned acquired=0;
 while(std::chrono::steady_clock::now()<end){auto tick=std::chrono::steady_clock::now();DXGI_OUTDUPL_FRAME_INFO fi{};ComPtr<IDXGIResource> resource;auto t0=std::chrono::steady_clock::now();hr=duplication->AcquireNextFrame(100,&fi,&resource);auto t1=std::chrono::steady_clock::now();if(hr==DXGI_ERROR_WAIT_TIMEOUT)continue;if(hr==DXGI_ERROR_ACCESS_LOST){r.error=L"Accès perdu après changement d’écran; relancez le diagnostic.";break;}if(FAILED(hr)){r.error=L"AcquireNextFrame échoué. HRESULT="+std::to_wstring((unsigned)hr);break;}++acquired;total_ms+=std::chrono::duration<double,std::milli>(t1-t0).count();ComPtr<ID3D11Texture2D> frame;hr=resource.As(&frame);if(SUCCEEDED(hr)){D3D11_TEXTURE2D_DESC fd{};frame->GetDesc(&fd);if(fd.Width!=r.width||fd.Height!=r.height){r.width=fd.Width;r.height=fd.Height;}}else r.error=L"Récupération de la texture GPU échouée.";duplication->ReleaseFrame();auto spent=std::chrono::steady_clock::now()-tick;if(spent<period)std::this_thread::sleep_for(period-spent);}
 auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();r.frames=acquired;r.fps=elapsed?acquired/elapsed:0;r.acquisition_ms=acquired?total_ms/acquired:0;unsigned expected=(unsigned)(elapsed*target_fps);r.dropped=expected>acquired?expected-acquired:0;return r;
}}


