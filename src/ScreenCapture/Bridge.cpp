// Stable C ABI consumed by the WebRTC host. No encoding or network code here.
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <cstring>
#include <memory>
#include <string>
#include <vector>
using Microsoft::WRL::ComPtr;
struct Capture {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGIOutputDuplication> duplication;
    ComPtr<ID3D11Texture2D> staging;
    ComPtr<ID3D11Texture2D> source, scaled;
    ComPtr<ID3D11ShaderResourceView> srv;
    ComPtr<ID3D11RenderTargetView> rtv;
    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11SamplerState> sampler;
    ComPtr<ID3D11VideoDevice> video_device;
    ComPtr<ID3D11VideoContext> video_context;
    ComPtr<ID3D11VideoProcessorEnumerator> video_enum;
    ComPtr<ID3D11VideoProcessor> video_processor;
    ComPtr<ID3D11VideoProcessorInputView> video_input;
    ComPtr<ID3D11VideoProcessorOutputView> video_output;
    bool nv12=false, prefer_nv12=true;
    unsigned width=0, height=0, target_width=1920, target_height=1080;
    unsigned desktop_width=0, desktop_height=0;
    DXGI_MODE_ROTATION rotation=DXGI_MODE_ROTATION_IDENTITY;
    std::string error;
    std::string stage;
    HRESULT initialize() {
        staging.Reset();source.Reset();scaled.Reset();srv.Reset();rtv.Reset();vs.Reset();ps.Reset();sampler.Reset();
        video_input.Reset();video_output.Reset();video_processor.Reset();video_enum.Reset();video_context.Reset();video_device.Reset();nv12=false;
        duplication.Reset(); context.Reset(); device.Reset();
        ComPtr<IDXGIFactory1> factory;
        stage="CreateDXGIFactory1";
        HRESULT hr=CreateDXGIFactory1(IID_PPV_ARGS(&factory));
        if(FAILED(hr)) return hr;
        for(UINT i=0;;++i) {
            ComPtr<IDXGIAdapter1> adapter;
            hr=factory->EnumAdapters1(i,&adapter);
            if(hr==DXGI_ERROR_NOT_FOUND) return DXGI_ERROR_NOT_FOUND;
            if(FAILED(hr)) return hr;
            for(UINT j=0;;++j) {
                ComPtr<IDXGIOutput> output;
                hr=adapter->EnumOutputs(j,&output);
                if(hr==DXGI_ERROR_NOT_FOUND) break;
                if(FAILED(hr)) return hr;
                DXGI_OUTPUT_DESC desc{};
                if(FAILED(output->GetDesc(&desc))) continue;
                if(!desc.AttachedToDesktop || desc.DesktopCoordinates.left!=0 || desc.DesktopCoordinates.top!=0) continue;
                rotation=desc.Rotation;
                desktop_width=desc.DesktopCoordinates.right-desc.DesktopCoordinates.left;
                desktop_height=desc.DesktopCoordinates.bottom-desc.DesktopCoordinates.top;
                stage="D3D11CreateDevice";
                hr=D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,
                    D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&context);
                if(FAILED(hr)) return hr;
                ComPtr<IDXGIOutput1> out;
                hr=output.As(&out); if(FAILED(hr)) return hr;
                stage="DuplicateOutput";
                hr=out->DuplicateOutput(device.Get(),&duplication); if(FAILED(hr)) return hr;
                DXGI_OUTDUPL_DESC d{}; duplication->GetDesc(&d);
                width=d.ModeDesc.Width; height=d.ModeDesc.Height;
                return S_OK;
            }
        }
    }
    HRESULT prepare_video(const D3D11_TEXTURE2D_DESC& original) {
        HRESULT hr=device.As(&video_device);if(FAILED(hr))return hr;
        hr=context.As(&video_context);if(FAILED(hr))return hr;
        D3D11_VIDEO_PROCESSOR_CONTENT_DESC content{};
        content.InputFrameFormat=D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE;
        content.InputFrameRate={60,1};content.OutputFrameRate={60,1};
        content.InputWidth=original.Width;content.InputHeight=original.Height;
        content.OutputWidth=width;content.OutputHeight=height;content.Usage=D3D11_VIDEO_USAGE_OPTIMAL_SPEED;
        hr=video_device->CreateVideoProcessorEnumerator(&content,&video_enum);if(FAILED(hr))return hr;
        UINT support=0;video_enum->CheckVideoProcessorFormat(DXGI_FORMAT_NV12,&support);
        if(!(support&D3D11_VIDEO_PROCESSOR_FORMAT_SUPPORT_OUTPUT))return DXGI_ERROR_UNSUPPORTED;
        hr=video_device->CreateVideoProcessor(video_enum.Get(),0,&video_processor);if(FAILED(hr))return hr;
        D3D11_TEXTURE2D_DESC desc=original;
        desc.BindFlags=D3D11_BIND_RENDER_TARGET;desc.CPUAccessFlags=0;desc.MiscFlags=0;desc.Usage=D3D11_USAGE_DEFAULT;
        hr=device->CreateTexture2D(&desc,nullptr,&source);if(FAILED(hr))return hr;
        D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC iv{};iv.ViewDimension=D3D11_VPIV_DIMENSION_TEXTURE2D;
        hr=video_device->CreateVideoProcessorInputView(source.Get(),video_enum.Get(),&iv,&video_input);if(FAILED(hr))return hr;
        desc.Width=width;desc.Height=height;desc.Format=DXGI_FORMAT_NV12;
        hr=device->CreateTexture2D(&desc,nullptr,&scaled);if(FAILED(hr))return hr;
        D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC ov{};ov.ViewDimension=D3D11_VPOV_DIMENSION_TEXTURE2D;
        hr=video_device->CreateVideoProcessorOutputView(scaled.Get(),video_enum.Get(),&ov,&video_output);if(FAILED(hr))return hr;
        desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.Usage=D3D11_USAGE_STAGING;
        hr=device->CreateTexture2D(&desc,nullptr,&staging);if(FAILED(hr))return hr;
        RECT src{0,0,LONG(original.Width),LONG(original.Height)},dst{0,0,LONG(width),LONG(height)};
        video_context->VideoProcessorSetStreamFrameFormat(video_processor.Get(),0,D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE);
        video_context->VideoProcessorSetStreamSourceRect(video_processor.Get(),0,TRUE,&src);
        video_context->VideoProcessorSetStreamDestRect(video_processor.Get(),0,TRUE,&dst);
        video_context->VideoProcessorSetOutputTargetRect(video_processor.Get(),TRUE,&dst);
        video_context->VideoProcessorSetStreamAutoProcessingMode(video_processor.Get(),0,FALSE);
        D3D11_VIDEO_PROCESSOR_COLOR_SPACE rgb{},yuv{};
        rgb.RGB_Range=0;rgb.YCbCr_Matrix=1;
        yuv.YCbCr_Matrix=1;yuv.Nominal_Range=D3D11_VIDEO_PROCESSOR_NOMINAL_RANGE_16_235;
        video_context->VideoProcessorSetStreamColorSpace(video_processor.Get(),0,&rgb);
        video_context->VideoProcessorSetOutputColorSpace(video_processor.Get(),&yuv);
        nv12=true;return S_OK;
    }
    HRESULT prepare(const D3D11_TEXTURE2D_DESC& original) {
        bool portrait=rotation==DXGI_MODE_ROTATION_ROTATE90 || rotation==DXGI_MODE_ROTATION_ROTATE270;
        unsigned ow=portrait?original.Height:original.Width,oh=portrait?original.Width:original.Height;
        double scale=(std::min)(1.0,(std::min)(double(target_width)/ow,double(target_height)/oh));
        width=(std::max)(2u,unsigned(ow*scale)/2*2);height=(std::max)(2u,unsigned(oh*scale)/2*2);
        if(prefer_nv12 && (rotation==DXGI_MODE_ROTATION_IDENTITY || rotation==DXGI_MODE_ROTATION_UNSPECIFIED)) {
            if(SUCCEEDED(prepare_video(original)))return S_OK;
            // Keep the existing shader path on devices without NV12 video processing.
            source.Reset();scaled.Reset();staging.Reset();video_input.Reset();video_output.Reset();
            video_processor.Reset();video_enum.Reset();video_context.Reset();video_device.Reset();nv12=false;
        }
        D3D11_TEXTURE2D_DESC desc=original;
        desc.Usage=D3D11_USAGE_DEFAULT;desc.CPUAccessFlags=0;desc.MiscFlags=0;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        HRESULT hr=device->CreateTexture2D(&desc,nullptr,&source);if(FAILED(hr))return hr;
        hr=device->CreateShaderResourceView(source.Get(),nullptr,&srv);if(FAILED(hr))return hr;
        desc.Width=width;desc.Height=height;desc.BindFlags=D3D11_BIND_RENDER_TARGET;
        hr=device->CreateTexture2D(&desc,nullptr,&scaled);if(FAILED(hr))return hr;
        hr=device->CreateRenderTargetView(scaled.Get(),nullptr,&rtv);if(FAILED(hr))return hr;
        desc.BindFlags=0;desc.Usage=D3D11_USAGE_STAGING;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        hr=device->CreateTexture2D(&desc,nullptr,&staging);if(FAILED(hr))return hr;
        const char* vsrc="struct V{float4 p:SV_POSITION;float2 uv:TEXCOORD0;};V main(uint i:SV_VertexID){V v;v.uv=float2((i<<1)&2,i&2);v.p=float4(v.uv*float2(2,-2)+float2(-1,1),0,1);return v;}";
        std::string uv="v.uv";
        if(rotation==DXGI_MODE_ROTATION_ROTATE90)uv="float2(v.uv.y,1-v.uv.x)";
        if(rotation==DXGI_MODE_ROTATION_ROTATE180)uv="1-v.uv";
        if(rotation==DXGI_MODE_ROTATION_ROTATE270)uv="float2(1-v.uv.y,v.uv.x)";
        std::string psrc="Texture2D tex:register(t0);SamplerState smp:register(s0);struct V{float4 p:SV_POSITION;float2 uv:TEXCOORD0;};float4 main(V v):SV_TARGET{return tex.Sample(smp,"+uv+");}";
        ComPtr<ID3DBlob> blob,errors;
        hr=D3DCompile(vsrc,std::strlen(vsrc),nullptr,nullptr,nullptr,"main","vs_4_0",0,0,&blob,&errors);if(FAILED(hr))return hr;
        hr=device->CreateVertexShader(blob->GetBufferPointer(),blob->GetBufferSize(),nullptr,&vs);if(FAILED(hr))return hr;
        blob.Reset();errors.Reset();
        hr=D3DCompile(psrc.data(),psrc.size(),nullptr,nullptr,nullptr,"main","ps_4_0",0,0,&blob,&errors);if(FAILED(hr))return hr;
        hr=device->CreatePixelShader(blob->GetBufferPointer(),blob->GetBufferSize(),nullptr,&ps);if(FAILED(hr))return hr;
        D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;sd.MaxLOD=D3D11_FLOAT32_MAX;
        return device->CreateSamplerState(&sd,&sampler);
    }
};
extern "C" {
// Windows Settings' per-source DPI packets. These private packet IDs are checked
// at runtime; never fall back to registry writes that would require signing out.
struct ScaleSnapshot {LUID adapter;UINT source;int relative;};
static unsigned scale_operation(bool apply125,ScaleSnapshot* saved) {
    struct GetScale {DISPLAYCONFIG_DEVICE_INFO_HEADER header;int minimum,current,maximum;};
    struct SetScale {DISPLAYCONFIG_DEVICE_INFO_HEADER header;int relative;};
    static_assert(sizeof(GetScale)==32 && sizeof(SetScale)==24,"DPI packet layout");
    DISPLAY_DEVICEW primary{};primary.cb=sizeof(primary);
    for(DWORD index=0;EnumDisplayDevicesW(nullptr,index,&primary,0);++index){
        if(primary.StateFlags&DISPLAY_DEVICE_PRIMARY_DEVICE)break;
        primary={};primary.cb=sizeof(primary);
    }
    if(!(primary.StateFlags&DISPLAY_DEVICE_PRIMARY_DEVICE))return ERROR_NOT_FOUND;
    for(int attempt=0;attempt<3;++attempt){
        UINT paths=0,modes=0;
        LONG result=GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS,&paths,&modes);
        if(result!=ERROR_SUCCESS)return result;
        std::vector<DISPLAYCONFIG_PATH_INFO> path(paths);std::vector<DISPLAYCONFIG_MODE_INFO> mode(modes);
        result=QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS,&paths,path.data(),&modes,mode.data(),nullptr);
        if(result==ERROR_INSUFFICIENT_BUFFER)continue;
        if(result!=ERROR_SUCCESS)return result;
        for(UINT i=0;i<paths;++i){
            auto source=path[i].sourceInfo;
            DISPLAYCONFIG_SOURCE_DEVICE_NAME name{};
            name.header={DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME,sizeof(name),source.adapterId,source.id};
            if(DisplayConfigGetDeviceInfo(&name.header)!=ERROR_SUCCESS || wcscmp(name.viewGdiDeviceName,primary.DeviceName)!=0)continue;
            GetScale get{};get.header={static_cast<DISPLAYCONFIG_DEVICE_INFO_TYPE>(-3),sizeof(get),source.adapterId,source.id};
            result=DisplayConfigGetDeviceInfo(&get.header);if(result!=ERROR_SUCCESS)return result;
            if(saved)*saved={source.adapterId,source.id,get.current};
            if(!apply125)return ERROR_SUCCESS;
            // 100%,125%,150%,... are consecutive steps; minimum is 100% relative to recommended.
            int requested=get.minimum+1;
            if(requested<get.minimum || requested>get.maximum)return ERROR_NOT_SUPPORTED;
            if(get.current==requested)return ERROR_SUCCESS;
            SetScale set{};set.header={static_cast<DISPLAYCONFIG_DEVICE_INFO_TYPE>(-4),sizeof(set),source.adapterId,source.id};set.relative=requested;
            result=DisplayConfigSetDeviceInfo(&set.header);if(result!=ERROR_SUCCESS)return result;
            result=DisplayConfigGetDeviceInfo(&get.header);
            return result==ERROR_SUCCESS && get.current!=requested ? ERROR_INVALID_STATE : result;
        }
    }
    return ERROR_NOT_FOUND;
}
__declspec(dllexport) unsigned rc_set_scale125(){return scale_operation(true,nullptr);}
__declspec(dllexport) unsigned rc_save_scale(ScaleSnapshot* saved){return saved?scale_operation(false,saved):ERROR_INVALID_PARAMETER;}
__declspec(dllexport) unsigned rc_restore_scale(const ScaleSnapshot* saved){
    if(!saved)return ERROR_INVALID_PARAMETER;
    struct SetScale {DISPLAYCONFIG_DEVICE_INFO_HEADER header;int relative;};
    SetScale request{};
    request.header={static_cast<DISPLAYCONFIG_DEVICE_INFO_TYPE>(-4),sizeof(request),saved->adapter,saved->source};
    request.relative=saved->relative;
    return DisplayConfigSetDeviceInfo(&request.header);
}
__declspec(dllexport) void* rc_create(){return new(std::nothrow) Capture();}
__declspec(dllexport) void rc_destroy(void* p){delete static_cast<Capture*>(p);}
__declspec(dllexport) const char* rc_error(void* p){return static_cast<Capture*>(p)->error.c_str();}
__declspec(dllexport) void rc_size(void* p,unsigned w,unsigned h){auto& c=*static_cast<Capture*>(p);c.target_width=w;c.target_height=h;}
__declspec(dllexport) unsigned rc_source_width(void* p){return static_cast<Capture*>(p)->desktop_width;}
__declspec(dllexport) unsigned rc_source_height(void* p){return static_cast<Capture*>(p)->desktop_height;}
__declspec(dllexport) unsigned rc_format(void* p){return static_cast<Capture*>(p)->nv12?1:0;}
__declspec(dllexport) void rc_prefer_nv12(void* p,unsigned enabled){static_cast<Capture*>(p)->prefer_nv12=enabled!=0;}
// 1: new image, 0: unchanged/timeout, -1: recoverable error, -2: output buffer too small.
__declspec(dllexport) int rc_frame(void* p, unsigned char* buffer, unsigned capacity,
                                  unsigned* w, unsigned* h, unsigned* accumulated) {
    auto& c=*static_cast<Capture*>(p);
    auto fail=[&](HRESULT hr){c.error=c.stage+" HRESULT="+std::to_string(static_cast<unsigned>(hr));return -1;};
    if(!c.duplication){HRESULT hr=c.initialize();if(FAILED(hr))return fail(hr);}
    *w=c.width; *h=c.height; *accumulated=0;
    // Acquire first: initial output dimensions depend on the GPU scaling envelope.
    DXGI_OUTDUPL_FRAME_INFO info{}; ComPtr<IDXGIResource> resource;
    c.stage="AcquireNextFrame";
    HRESULT hr=c.duplication->AcquireNextFrame(10,&info,&resource);
    if(hr==DXGI_ERROR_WAIT_TIMEOUT)return 0;
    if(FAILED(hr)){c.duplication.Reset();return fail(hr);}
    struct Release {ComPtr<IDXGIOutputDuplication> d;~Release(){d->ReleaseFrame();}} release{c.duplication};
    ComPtr<ID3D11Texture2D> texture;
    hr=resource.As(&texture);if(FAILED(hr))return fail(hr);
    D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
    c.stage="GPU scaling initialization";
    if(!c.staging){hr=c.prepare(desc);if(FAILED(hr)){c.duplication.Reset();return fail(hr);}}
    *w=c.width;*h=c.height;
    if(static_cast<unsigned long long>(c.width)*c.height*4>capacity)return -2;
    c.context->CopyResource(c.source.Get(),texture.Get());
    if(c.nv12) {
        D3D11_VIDEO_PROCESSOR_STREAM stream{};stream.Enable=TRUE;stream.pInputSurface=c.video_input.Get();
        c.stage="VideoProcessorBlt";
        hr=c.video_context->VideoProcessorBlt(c.video_processor.Get(),c.video_output.Get(),0,1,&stream);
        if(FAILED(hr)){c.duplication.Reset();return fail(hr);}
    } else {
    c.context->IASetInputLayout(nullptr);c.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    c.context->VSSetShader(c.vs.Get(),nullptr,0);c.context->PSSetShader(c.ps.Get(),nullptr,0);
    ID3D11ShaderResourceView* view=c.srv.Get();c.context->PSSetShaderResources(0,1,&view);
    ID3D11SamplerState* smp=c.sampler.Get();c.context->PSSetSamplers(0,1,&smp);
    ID3D11RenderTargetView* target=c.rtv.Get();c.context->OMSetRenderTargets(1,&target,nullptr);
    D3D11_VIEWPORT viewport{0,0,float(c.width),float(c.height),0,1};c.context->RSSetViewports(1,&viewport);
    c.context->Draw(3,0);
    view=nullptr;c.context->PSSetShaderResources(0,1,&view);
    }
    c.context->CopyResource(c.staging.Get(),c.scaled.Get());
    c.stage="Map readback";
    D3D11_MAPPED_SUBRESOURCE map{};hr=c.context->Map(c.staging.Get(),0,D3D11_MAP_READ,0,&map);if(FAILED(hr))return fail(hr);
    unsigned row_bytes=c.width*(c.nv12?1:4),rows=c.nv12?c.height*3/2:c.height;
    for(unsigned y=0;y<rows;++y)std::memcpy(buffer+y*row_bytes,static_cast<unsigned char*>(map.pData)+y*map.RowPitch,row_bytes);
    c.context->Unmap(c.staging.Get(),0);*accumulated=info.AccumulatedFrames;c.error.clear();return 1;
}
}
